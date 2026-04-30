from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from app.services.transcription_service import TranscriptionService


class FunctionWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, callback: Callable[[], Any]) -> None:
        super().__init__()
        self.callback = callback

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.callback()
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TranscriptionWorker(QObject):
    stage_changed = pyqtSignal(str)  # "uploading", "transcribing", "correcting"
    finished = pyqtSignal(int)  # audio_id
    failed = pyqtSignal(str)

    def __init__(
        self,
        transcription_service: TranscriptionService,
        audio_path: str,
        title: Optional[str] = None,
        document_paths: Optional[list[str]] = None,
        document_service=None,
    ) -> None:
        super().__init__()
        self.transcription_service = transcription_service
        self.audio_path = audio_path
        self.title = title
        self.document_paths = document_paths or []
        self.document_service = document_service

    @pyqtSlot()
    def run(self) -> None:
        try:
            # Progress callback emits stage signals
            def emit_stage(stage: str) -> None:
                self.stage_changed.emit(stage)

            audio_id = self.transcription_service.process_audio(
                self.audio_path,
                title=self.title,
                progress_callback=emit_stage,
            )

            # Upload any linked documents
            for doc_path in self.document_paths:
                if self.document_service:
                    self.document_service.store_document(doc_path, audio_id=audio_id)

            self.finished.emit(audio_id)
        except Exception as exc:
            self.failed.emit(str(exc))
