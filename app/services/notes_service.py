from __future__ import annotations

from app.database import Database
from app.services.groq_client import GroqClient


NOTE_MODE_EXACT = "exact"
NOTE_MODE_REFORMULATED = "reformulated"


class NotesService:
    def __init__(self, database: Database, groq_client: GroqClient) -> None:
        self.database = database
        self.groq_client = groq_client

    def generate_notes(self, audio_id: int, mode: str) -> str:
        transcript = self.database.get_transcript_by_audio(audio_id)
        if transcript is None:
            raise RuntimeError("No transcript available for this audio.")

        corrected_text = str(transcript.get("corrected_text", "")).strip()
        if not corrected_text:
            raise RuntimeError("Corrected transcript is empty.")

        if mode == NOTE_MODE_EXACT:
            style_instruction = (
                "Create structured study notes using wording as close as possible to the teacher's original phrasing. "
                "Use headings and bullet points."
            )
        else:
            style_instruction = (
                "Create structured study notes by reformulating concepts in clear student-friendly language. "
                "Keep key meaning accurate and use headings and bullet points."
            )

        system_prompt = "You create concise, well-structured lecture notes."
        user_prompt = (
            f"{style_instruction}\n\n"
            "Transcript:\n"
            f"{corrected_text}"
        )

        notes_text = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        self.database.add_note(audio_id=audio_id, mode=mode, content=notes_text)
        return notes_text
