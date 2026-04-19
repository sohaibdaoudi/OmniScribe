from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    storage_dir: Path
    audio_dir: Path
    documents_dir: Path
    db_path: Path
    groq_api_key: str
    whisper_model: str
    chat_model: str

    def ensure_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    storage_dir = _resolve_path(os.getenv("OMNISCRIBE_STORAGE_DIR", "storage"), base_dir)
    audio_dir = _resolve_path(os.getenv("OMNISCRIBE_AUDIO_DIR", str(storage_dir / "audio")), base_dir)
    documents_dir = _resolve_path(os.getenv("OMNISCRIBE_DOCUMENT_DIR", str(storage_dir / "documents")), base_dir)
    db_path = _resolve_path(os.getenv("OMNISCRIBE_DB_PATH", "omniscribe.db"), base_dir)

    return Settings(
        base_dir=base_dir,
        storage_dir=storage_dir,
        audio_dir=audio_dir,
        documents_dir=documents_dir,
        db_path=db_path,
        groq_api_key=os.getenv("GROQ_API_KEY", os.getenv("QROP_API_KEY", "")).strip(),
        whisper_model=os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3").strip(),
        chat_model=os.getenv("GROQ_CHAT_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip(),
    )


settings = load_settings()
