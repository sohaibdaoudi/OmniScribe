from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from app.database import Database
from app.services.groq_client import GroqClient


class TranscriptionService:
    def __init__(self, database: Database, groq_client: GroqClient, audio_storage_dir: Path) -> None:
        self.database = database
        self.groq_client = groq_client
        self.audio_storage_dir = audio_storage_dir

    def _copy_audio_file(self, source_audio_path: Path) -> Path:
        self.audio_storage_dir.mkdir(parents=True, exist_ok=True)
        extension = source_audio_path.suffix or ".audio"
        safe_name = f"{uuid.uuid4().hex}{extension.lower()}"
        destination = self.audio_storage_dir / safe_name
        shutil.copy2(source_audio_path, destination)
        return destination

    def process_audio(self, source_audio_path: str, title: str | None = None) -> int:
        source_path = Path(source_audio_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {source_path}")

        stored_path = self._copy_audio_file(source_path)
        audio_title = title.strip() if title and title.strip() else source_path.stem

        audio_id = self.database.add_audio(
            title=audio_title,
            original_filename=source_path.name,
            stored_path=str(stored_path),
        )

        raw_transcript = self.groq_client.transcribe_audio(stored_path)
        corrected_transcript = self.correct_transcript(raw_transcript)
        self.database.save_transcript(audio_id, raw_transcript, corrected_transcript)

        return audio_id

    def correct_transcript(self, raw_transcript: str) -> str:
        system_prompt = (
            "You are an academic transcription correction assistant. "
            "Fix grammar, punctuation, and obvious speech-to-text mistakes while preserving meaning."
        )
        user_prompt = (
            "Correct the following transcript. Return only the corrected transcript text.\n\n"
            f"{raw_transcript}"
        )

        corrected_transcript = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )
        return corrected_transcript
