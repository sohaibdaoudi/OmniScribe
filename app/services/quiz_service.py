from __future__ import annotations

from dataclasses import dataclass

from app.database import Database
from app.services.groq_client import GroqClient


@dataclass(frozen=True)
class _DocExcerpt:
    filename: str
    text: str


class QuizService:
    def __init__(self, database: Database, groq_client: GroqClient) -> None:
        self.database = database
        self.groq_client = groq_client

    def _build_documents_context(
        self,
        *,
        audio_id: int,
        max_total_chars: int = 9000,
        max_per_doc_chars: int = 2500,
    ) -> str:
        documents = self.database.list_documents(audio_id=audio_id)
        if not documents:
            return ""

        excerpts: list[_DocExcerpt] = []
        remaining = max_total_chars
        for doc in documents:
            if remaining <= 0:
                break

            filename = str(doc.get("original_filename") or "Unknown")
            extracted = str(doc.get("extracted_text") or "").strip()
            if not extracted:
                continue

            take = min(max_per_doc_chars, remaining)
            snippet = extracted[:take].strip()
            if len(extracted) > take:
                snippet = f"{snippet}\n\n[...truncated...]"

            excerpts.append(_DocExcerpt(filename=filename, text=snippet))
            remaining -= len(snippet)

        if not excerpts:
            return ""

        parts: list[str] = [
            "Supporting documents (excerpts):",
        ]
        for ex in excerpts:
            parts.append(f"--- {ex.filename} ---\n{ex.text}")
        return "\n\n".join(parts).strip()

    def generate_quiz(
        self,
        *,
        audio_id: int,
        num_questions: int = 10,
        focus: str | None = None,
        difficulty: str | None = None,
    ) -> str:
        transcript = self.database.get_transcript_by_audio(audio_id)
        if transcript is None:
            raise RuntimeError("No transcript available for this audio.")

        corrected_text = str(transcript.get("corrected_text", "")).strip()
        if not corrected_text:
            raise RuntimeError("Corrected transcript is empty.")

        try:
            n = int(num_questions)
        except (TypeError, ValueError):
            n = 10
        n = max(1, min(50, n))

        focus_text = (focus or "").strip()
        focus_clause = (
            f"Focus topic (optional): {focus_text}" if focus_text else "Focus topic: none"
        )

        difficulty_text = (difficulty or "mixed").strip() or "mixed"

        system_prompt = (
            "You create high-quality study quizzes in Markdown. "
            "Do not wrap the output in code fences. "
            "Be accurate and grounded in the provided content; do not invent facts. "
            "Follow the requested format strictly."
        )

        documents_context = self._build_documents_context(audio_id=audio_id)
        user_prompt = (
            f"Create a practice quiz with {n} multiple-choice questions based on the content below.\n"
            f"Difficulty: {difficulty_text}.\n"
            f"{focus_clause}.\n\n"
            "Format (STRICT; do not deviate):\n"
            "1) Use exactly these section headers:\n"
            "   - '## Quiz'\n"
            "   - '## Answer Key'\n"
            "2) Under '## Quiz', output questions 1..N like this:\n"
            "   1. <question text>\n"
            "   A. <option text>\n"
            "   B. <option text>\n"
            "   C. <option text>\n"
            "   D. <option text>\n"
            "   (blank line)\n"
            "3) Under '## Answer Key', output lines like this (one per question):\n"
            "   1. B — <one sentence explanation>\n"
            "4) Exactly four options per question (A-D). Only ONE correct.\n"
            "5) Do not include any other sections, commentary, or extra bullets.\n"
            "6) Use only information from the transcript and supporting documents; if they conflict, prefer the transcript.\n\n"
            "Content:\n"
            f"{corrected_text}"
            + (f"\n\n{documents_context}" if documents_context else "")
        )

        quiz_markdown = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        self.database.add_quiz(
            audio_id=audio_id,
            num_questions=n,
            focus=focus_text or None,
            difficulty=difficulty_text,
            content=quiz_markdown,
        )
        return quiz_markdown
