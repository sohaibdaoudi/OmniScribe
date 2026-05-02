from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from docx import Document
from pypdf import PdfReader

from app.database import Database
from app.services.rag_service import RagService


class DocumentService:
    def __init__(
        self,
        database: Database,
        document_storage_dir: Path,
        rag_service: RagService,  # new
    ) -> None:
        self.database = database
        self.document_storage_dir = document_storage_dir
        self.rag_service = rag_service

    def _copy_document(self, source_document_path: Path) -> Path:
        self.document_storage_dir.mkdir(parents=True, exist_ok=True)
        extension = source_document_path.suffix or ".bin"
        destination = (
            self.document_storage_dir / f"{uuid.uuid4().hex}{extension.lower()}"
        )
        shutil.copy2(source_document_path, destination)
        return destination

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()

    def _extract_docx_text(self, docx_path: Path) -> str:
        document = Document(str(docx_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

    def _extract_text(self, source_document_path: Path) -> str:
        extension = source_document_path.suffix.lower()

        try:
            if extension == ".pdf":
                text = self._extract_pdf_text(source_document_path)
            elif extension == ".docx":
                text = self._extract_docx_text(source_document_path)
            else:
                text = source_document_path.read_text(
                    encoding="utf-8", errors="ignore"
                ).strip()
        except Exception as exc:
            return f"Document uploaded but text extraction failed: {exc}"

        if not text:
            return "Document uploaded, but no readable text was extracted."
        return text

    def store_document(
        self, source_document_path: str, audio_id: int | None = None
    ) -> int:
        source_path = Path(source_document_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Document file does not exist: {source_path}")

        stored_path = self._copy_document(source_path)
        extracted_text = self._extract_text(source_path)

        document_id = self.database.add_document(
            audio_id=audio_id,
            original_filename=source_path.name,
            stored_path=str(stored_path),
            extracted_text=extracted_text,
        )
        self.rag_service.index_document(document_id)
        return document_id
