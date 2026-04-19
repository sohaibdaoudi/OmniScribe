from __future__ import annotations

from dataclasses import dataclass
import math
import re

from app.database import Database
from app.services.groq_client import GroqClient


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    source_label: str
    text: str
    source_kind: str


class RagService:
    def __init__(self, database: Database, groq_client: GroqClient) -> None:
        self.database = database
        self.groq_client = groq_client

    def _tokenize(self, text: str) -> set[str]:
        tokens = {token.lower() for token in TOKEN_PATTERN.findall(text)}
        return {token for token in tokens if len(token) > 2}

    def _split_long_text(self, text: str, max_chars: int) -> list[str]:
        content = text.strip()
        if not content:
            return []
        if len(content) <= max_chars:
            return [content]

        # Prefer sentence boundaries so retrieval chunks stay semantically coherent.
        units = [part.strip() for part in SENTENCE_SPLIT_PATTERN.split(content) if part.strip()]
        if len(units) <= 1:
            units = [part.strip() for part in re.split(r"\n+", content) if part.strip()]

        if len(units) <= 1:
            return [
                content[i:i + max_chars].strip()
                for i in range(0, len(content), max_chars)
                if content[i:i + max_chars].strip()
            ]

        pieces: list[str] = []
        current = ""
        for unit in units:
            if len(unit) > max_chars:
                if current:
                    pieces.append(current)
                    current = ""

                words = unit.split()
                hard_chunk = ""
                for word in words:
                    candidate = f"{hard_chunk} {word}".strip()
                    if len(candidate) <= max_chars:
                        hard_chunk = candidate
                    else:
                        if hard_chunk:
                            pieces.append(hard_chunk)
                        hard_chunk = word

                if hard_chunk:
                    pieces.append(hard_chunk)
                continue

            candidate = f"{current} {unit}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = unit

        if current:
            pieces.append(current)

        return pieces

    def _chunk_text(self, text: str, max_chars: int = 900) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
        if not paragraphs:
            plain = text.strip()
            return [plain] if plain else []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            paragraph_pieces = self._split_long_text(paragraph, max_chars=max_chars)
            for piece in paragraph_pieces:
                if len(current) + len(piece) + 2 <= max_chars:
                    current = f"{current}\n\n{piece}".strip()
                    continue

                if current:
                    chunks.append(current)
                current = piece

        if current:
            chunks.append(current)

        return chunks

    def _select_diverse_chunks(self, ranked_chunks: list[tuple[float, Chunk]], top_k: int) -> list[Chunk]:
        if top_k <= 0:
            return []

        selected: list[Chunk] = []
        per_source_count: dict[str, int] = {}

        for _, chunk in ranked_chunks:
            if len(selected) >= top_k:
                break
            if per_source_count.get(chunk.source_label, 0) >= 2:
                continue

            selected.append(chunk)
            per_source_count[chunk.source_label] = per_source_count.get(chunk.source_label, 0) + 1

        has_document = any(chunk.source_kind == "document" for chunk in selected)
        first_document = next((chunk for _, chunk in ranked_chunks if chunk.source_kind == "document"), None)
        if first_document is not None and not has_document:
            if len(selected) < top_k:
                selected.append(first_document)
            elif selected:
                replace_idx = len(selected) - 1
                for idx in range(len(selected) - 1, -1, -1):
                    if selected[idx].source_kind != "document":
                        replace_idx = idx
                        break
                selected[replace_idx] = first_document

        return selected[:top_k]

    def _collect_chunks(self, audio_id: int | None) -> list[Chunk]:
        chunks: list[Chunk] = []

        transcripts = self.database.get_corrected_transcripts(audio_id=audio_id)
        for transcript in transcripts:
            title = transcript.get("audio_title") or f"Audio {transcript.get('audio_id')}"
            source_label = f"Transcript - {title}"
            for piece in self._chunk_text(str(transcript.get("corrected_text", ""))):
                chunks.append(Chunk(source_label=source_label, text=piece, source_kind="transcript"))

        documents = self.database.list_documents(audio_id=audio_id)
        for document in documents:
            source_label = f"Document - {document.get('original_filename', 'Unknown')}"
            for piece in self._chunk_text(str(document.get("extracted_text", ""))):
                chunks.append(Chunk(source_label=source_label, text=piece, source_kind="document"))

        return chunks

    def retrieve_context(self, question: str, audio_id: int | None = None, top_k: int = 6) -> list[Chunk]:
        chunks = self._collect_chunks(audio_id=audio_id)
        if not chunks:
            return []

        query_tokens = self._tokenize(question)
        if not query_tokens:
            return self._select_diverse_chunks([(0.0, chunk) for chunk in chunks], top_k=top_k)

        scored: list[tuple[float, Chunk]] = []
        for chunk in chunks:
            chunk_tokens = self._tokenize(chunk.text)
            if not chunk_tokens:
                continue

            overlap = len(query_tokens.intersection(chunk_tokens))
            if overlap == 0:
                continue

            score = overlap / math.sqrt(len(chunk_tokens))
            if chunk.source_kind == "document":
                score *= 1.1
            scored.append((score, chunk))

        if not scored:
            return self._select_diverse_chunks([(0.0, chunk) for chunk in chunks], top_k=top_k)

        scored.sort(key=lambda item: item[0], reverse=True)
        return self._select_diverse_chunks(scored, top_k=top_k)

    def answer_question(self, question: str, audio_id: int | None = None) -> dict[str, object]:
        question_text = question.strip()
        if not question_text:
            raise RuntimeError("Question is empty.")

        context_chunks = self.retrieve_context(question_text, audio_id=audio_id, top_k=6)
        if not context_chunks:
            raise RuntimeError("No corrected transcript or document content is available yet.")

        context_sections = []
        for index, chunk in enumerate(context_chunks, start=1):
            context_sections.append(f"[Source {index}] {chunk.source_label}\n{chunk.text}")

        context_block = "\n\n".join(context_sections)

        system_prompt = (
            "You are OmniScribe's study assistant. "
            "Answer strictly from the provided context. "
            "If context is insufficient, clearly say what is missing."
        )
        user_prompt = (
            "Use the following context to answer the question. Include source numbers when relevant.\n\n"
            f"{context_block}\n\n"
            f"Question: {question_text}"
        )

        answer = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        unique_sources: list[str] = []
        seen_sources: set[str] = set()
        for chunk in context_chunks:
            if chunk.source_label in seen_sources:
                continue
            seen_sources.add(chunk.source_label)
            unique_sources.append(chunk.source_label)

        return {
            "answer": answer,
            "sources": unique_sources,
        }
