from __future__ import annotations

from dataclasses import dataclass
import math
import re

from app.database import Database
from app.services.groq_client import GroqClient


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")


@dataclass
class Chunk:
    source_label: str
    text: str


class RagService:
    def __init__(self, database: Database, groq_client: GroqClient) -> None:
        self.database = database
        self.groq_client = groq_client

    def _tokenize(self, text: str) -> set[str]:
        tokens = {token.lower() for token in TOKEN_PATTERN.findall(text)}
        return {token for token in tokens if len(token) > 2}

    def _chunk_text(self, text: str, max_chars: int = 900) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
        if not paragraphs:
            plain = text.strip()
            return [plain] if plain else []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 2 <= max_chars:
                current = f"{current}\n\n{paragraph}".strip()
                continue

            if current:
                chunks.append(current)
            current = paragraph

        if current:
            chunks.append(current)

        return chunks

    def _collect_chunks(self, audio_id: int | None) -> list[Chunk]:
        chunks: list[Chunk] = []

        transcripts = self.database.get_corrected_transcripts(audio_id=audio_id)
        for transcript in transcripts:
            title = transcript.get("audio_title") or f"Audio {transcript.get('audio_id')}"
            source_label = f"Transcript - {title}"
            for piece in self._chunk_text(str(transcript.get("corrected_text", ""))):
                chunks.append(Chunk(source_label=source_label, text=piece))

        documents = self.database.list_documents(audio_id=audio_id)
        for document in documents:
            source_label = f"Document - {document.get('original_filename', 'Unknown')}"
            for piece in self._chunk_text(str(document.get("extracted_text", ""))):
                chunks.append(Chunk(source_label=source_label, text=piece))

        return chunks

    def retrieve_context(self, question: str, audio_id: int | None = None, top_k: int = 6) -> list[Chunk]:
        chunks = self._collect_chunks(audio_id=audio_id)
        if not chunks:
            return []

        query_tokens = self._tokenize(question)
        if not query_tokens:
            return chunks[:top_k]

        scored: list[tuple[float, Chunk]] = []
        for chunk in chunks:
            chunk_tokens = self._tokenize(chunk.text)
            if not chunk_tokens:
                continue

            overlap = len(query_tokens.intersection(chunk_tokens))
            if overlap == 0:
                continue

            score = overlap / math.sqrt(len(chunk_tokens))
            scored.append((score, chunk))

        if not scored:
            return chunks[:top_k]

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

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

        return {
            "answer": answer,
            "sources": [chunk.source_label for chunk in context_chunks],
        }
