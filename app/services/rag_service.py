from __future__ import annotations

from dataclasses import dataclass
import re

from app.database import Database
from app.services.groq_client import GroqClient
from app.services.vector_store_service import VectorStoreService

# Chunking parameters
MAX_CHARS = 900
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
        self.vector_store = VectorStoreService()
        # Rebuild index on startup (or skip if you want incremental)
        self.rebuild_index()

    # ---------- Chunking (same as before, kept for compatibility) ----------
    def _split_long_text(self, text: str, max_chars: int) -> list[str]:
        content = text.strip()
        if not content:
            return []
        if len(content) <= max_chars:
            return [content]

        # Prefer sentence boundaries
        units = [
            part.strip()
            for part in SENTENCE_SPLIT_PATTERN.split(content)
            if part.strip()
        ]
        if len(units) <= 1:
            units = [part.strip() for part in re.split(r"\n+", content) if part.strip()]

        if len(units) <= 1:
            return [
                content[i : i + max_chars].strip()
                for i in range(0, len(content), max_chars)
                if content[i : i + max_chars].strip()
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

    def _chunk_text(self, text: str, max_chars: int = MAX_CHARS) -> list[str]:
        paragraphs = [
            part.strip() for part in re.split(r"\n{2,}", text) if part.strip()
        ]
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

    # ---------- Index building (used on startup and incremental updates) ----------
    def _collect_all_chunks(self) -> list[tuple[str, str, str]]:
        """Return list of (chunk_text, source_label, source_kind) for all transcripts and documents."""
        chunks: list[tuple[str, str, str]] = []

        # Transcripts
        transcripts = self.database.get_corrected_transcripts(audio_id=None)
        for transcript in transcripts:
            title = (
                transcript.get("audio_title") or f"Audio {transcript.get('audio_id')}"
            )
            source_label = f"Transcript - {title}"
            for piece in self._chunk_text(str(transcript.get("corrected_text", ""))):
                chunks.append((piece, source_label, "transcript"))

        # Documents
        documents = self.database.list_documents(audio_id=None)
        for document in documents:
            source_label = f"Document - {document.get('original_filename', 'Unknown')}"
            for piece in self._chunk_text(str(document.get("extracted_text", ""))):
                chunks.append((piece, source_label, "document"))

        return chunks

    def rebuild_index(self) -> None:
        """Clear the vector store and re‑index all transcripts and documents."""
        print("Rebuilding RAG index...")
        self.vector_store.clear_collection()
        all_chunks = self._collect_all_chunks()
        if not all_chunks:
            print("No chunks to index.")
            return

        # Convert to format expected by add_chunks
        chunks_for_store = [
            (text, source_label, kind) for text, source_label, kind in all_chunks
        ]
        self.vector_store.add_chunks(chunks_for_store)
        print(f"Indexed {len(chunks_for_store)} chunks.")

    def index_audio(self, audio_id: int) -> None:
        """Index (or re‑index) a specific audio's corrected transcript."""
        transcript = self.database.get_transcript_by_audio(audio_id)
        if not transcript:
            return
        corrected = str(transcript.get("corrected_text", "")).strip()
        if not corrected:
            return

        # Get audio title
        audio = None
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT title FROM audios WHERE id = ?", (audio_id,)
            ).fetchone()
            if row:
                audio = dict(row)
        title = (
            audio.get("title", f"Audio {audio_id}") if audio else f"Audio {audio_id}"
        )
        source_label = f"Transcript - {title}"

        # Chunk the transcript
        pieces = self._chunk_text(corrected)
        if not pieces:
            return

        # Remove old chunks for this source (simple: rebuild whole index for now, but we can be smarter)
        # For MVP, we just add and let duplicates accumulate; to avoid that we can delete old ones.
        # Since this is called only when new audio is added, we can accept rebuilding the whole index.
        # For simplicity, we call rebuild_index, which is fine for small datasets.
        self.rebuild_index()

    def index_document(self, document_id: int) -> None:
        """Index a document. Similar to index_audio."""
        docs = self.database.list_documents()
        doc = next((d for d in docs if d["id"] == document_id), None)
        if not doc:
            return
        source_label = f"Document - {doc.get('original_filename', 'Unknown')}"
        text = str(doc.get("extracted_text", "")).strip()
        if not text:
            return
        pieces = self._chunk_text(text)
        if not pieces:
            return
        # Again, rebuild whole index for simplicity
        self.rebuild_index()

    # ---------- Retrieval and Answering ----------
    def retrieve_context(
        self, question: str, audio_id: int | None = None, top_k: int = 6
    ) -> list[Chunk]:
        """
        Retrieve relevant chunks using semantic similarity.
        If audio_id is provided, we filter results to only those belonging to that audio's
        transcript and its linked documents. ChromaDB doesn't support metadata filtering
        very efficiently, so we do post‑filtering.
        """
        # Retrieve top_k * 2 candidates, then filter by audio_id if needed
        raw_chunks = self.vector_store.similarity_search(
            question, top_k=top_k * 2 if audio_id else top_k
        )

        filtered = []
        for text, meta in raw_chunks:
            source_label = meta["source_label"]
            chunk_kind = meta["kind"]

            # If audio_id is required, we need to check if this chunk belongs to that audio.
            # Our source_label contains either "Transcript - {title}" or "Document - {filename}".
            # To map to audio_id, we need to reverse‑lookup by title/filename.
            # For MVP, we implement a quick mapping.
            if audio_id is not None:
                # Determine which audio this chunk is associated with.
                # For transcripts: find audio by title match.
                # For documents: document might be linked via audio_id in DB.
                chunk_audio_id = self._guess_audio_id_from_source(source_label)
                if chunk_audio_id != audio_id:
                    continue
            filtered.append((text, meta))
            if len(filtered) >= top_k:
                break

        # If we didn't get enough, re‑run without filtering? Not needed.

        return [
            Chunk(
                source_label=meta["source_label"], text=text, source_kind=meta["kind"]
            )
            for text, meta in filtered
        ]

    def _guess_audio_id_from_source(self, source_label: str) -> int | None:
        """Helper to map a source label to an audio_id."""
        if source_label.startswith("Transcript - "):
            title = source_label[13:]  # after "Transcript - "
            with self.database._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM audios WHERE title = ? OR stored_path LIKE ? OR id = ?",
                    (title, f"%{title}%", 0),
                ).fetchone()
                if row:
                    return row["id"]
            return None
        elif source_label.startswith("Document - "):
            filename = source_label[11:]
            # Find document by filename, then get its audio_id
            docs = self.database.list_documents()
            for doc in docs:
                if doc.get("original_filename") == filename:
                    return doc.get("audio_id")
            return None
        return None

    def answer_question(
        self, question: str, audio_id: int | None = None
    ) -> dict[str, object]:
        """Answer a question using RAG (embedding retrieval + Groq)."""
        question_text = question.strip()
        if not question_text:
            raise RuntimeError("Question is empty.")

        context_chunks = self.retrieve_context(
            question_text, audio_id=audio_id, top_k=6
        )
        if not context_chunks:
            raise RuntimeError("No relevant context found in the knowledge base.")

        context_sections = []
        for idx, chunk in enumerate(context_chunks, start=1):
            context_sections.append(
                f"[Source {idx}] {chunk.source_label}\n{chunk.text}"
            )

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

        print("[debugging]: Enhanced prompt sent to Groq:")
        print(f"System: {system_prompt}")
        print(f"User:\n{user_prompt}")
        print("=" * 80 + "\n")

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
