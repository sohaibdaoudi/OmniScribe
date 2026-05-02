from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from app.config import settings
from app.database import Database
from app.services.api_status_service import ApiStatusService
from app.services.document_service import DocumentService
from app.services.groq_client import GroqClient
from app.services.notes_service import NotesService
from app.services.rag_service import RagService
from app.services.transcription_service import TranscriptionService
from app.ui.main_window import MainWindow


def build_main_window() -> MainWindow:
    settings.ensure_directories()

    database = Database(settings.db_path)
    database.initialize()

    groq_client = GroqClient(
        api_key=settings.groq_api_key,
        whisper_model=settings.whisper_model,
        chat_model=settings.chat_model,
    )

    rag_service = RagService(database=database, groq_client=groq_client)

    transcription_service = TranscriptionService(
        database=database,
        groq_client=groq_client,
        audio_storage_dir=settings.audio_dir,
        rag_service=rag_service,
    )
    document_service = DocumentService(
        database=database,
        document_storage_dir=settings.documents_dir,
        rag_service=rag_service,
    )
    notes_service = NotesService(database=database, groq_client=groq_client)
    api_status_service = ApiStatusService(groq_client=groq_client)

    return MainWindow(
        database=database,
        transcription_service=transcription_service,
        document_service=document_service,
        notes_service=notes_service,
        rag_service=rag_service,
        api_status_service=api_status_service,
    )


def run() -> None:
    app = QApplication(sys.argv)
    window = build_main_window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
