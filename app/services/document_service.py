from __future__ import annotations

from pathlib import Path
import shutil
import uuid
import logging

from docx import Document
from pypdf import PdfReader

import easyocr
import fitz  # PyMuPDF
from PIL import Image

from app.database import Database
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)

# Global EasyOCR reader (singleton to avoid reloading model)
_OCR_READER = None


def get_ocr_reader():
    global _OCR_READER
    if _OCR_READER is None:
        # Initialize with English language; auto-downloads model on first use
        _OCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _OCR_READER


class DocumentService:
    def __init__(
        self,
        database: Database,
        document_storage_dir: Path,
        rag_service: RagService,
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
        """Extract text from a text-based PDF using PyPDF."""
        try:
            reader = PdfReader(str(pdf_path))
            parts: list[str] = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts).strip()
        except Exception as e:
            logger.warning(f"PyPDF extraction failed for {pdf_path}: {e}")
            return ""

    def _extract_docx_text(self, docx_path: Path) -> str:
        document = Document(str(docx_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

    def _ocr_image(self, image_path: Path) -> str:
        """Run EasyOCR on a single image file."""
        reader = get_ocr_reader()
        try:
            # EasyOCR accepts file path directly
            result = reader.readtext(str(image_path), detail=0, paragraph=True)
            return "\n".join(result).strip()
        except Exception as e:
            logger.exception(f"OCR failed for image {image_path}")
            raise RuntimeError(f"OCR failed: {e}")

    def _ocr_pdf(self, pdf_path: Path, dpi: int = 150) -> str:
        """
        Convert each PDF page to an image using PyMuPDF (no poppler),
        then run OCR on each image.
        """
        reader = get_ocr_reader()
        all_text = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                try:
                    # Render page to an image (pixmap)
                    pix = doc[page_num].get_pixmap(dpi=dpi)
                    img_data = pix.tobytes("png")
                    # EasyOCR can accept image bytes as a numpy array or file path
                    # We'll save temporarily or use in-memory PIL Image
                    # Simpler: write to a temporary file, then read.
                    # For performance, we can load from bytes using PIL.
                    import io
                    from PIL import Image

                    img = Image.open(io.BytesIO(img_data))
                    # Convert PIL image to numpy array for EasyOCR
                    import numpy as np

                    img_np = np.array(img)
                    result = reader.readtext(img_np, detail=0, paragraph=True)
                    page_text = "\n".join(result)
                    all_text.append(f"--- Page {page_num+1} ---\n{page_text}")
                except Exception as e:
                    logger.warning(
                        f"OCR failed for page {page_num+1} of {pdf_path}: {e}"
                    )
                    all_text.append(f"--- Page {page_num+1} ---\n[OCR error]")
            doc.close()
        except Exception as e:
            logger.exception(f"PDF processing failed for {pdf_path}")
            raise RuntimeError(f"PDF to image conversion failed: {e}")
        return "\n\n".join(all_text).strip()

    def _extract_text(self, source_document_path: Path) -> str:
        extension = source_document_path.suffix.lower()

        try:
            if extension == ".pdf":
                # First try normal text extraction
                text = self._extract_pdf_text(source_document_path)
                # If insufficient text (likely scanned), fall back to OCR
                if len(text) < 50:
                    logger.info(
                        f"PDF seems scanned, falling back to OCR: {source_document_path}"
                    )
                    text = self._ocr_pdf(source_document_path)

            elif extension in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
                text = self._ocr_image(source_document_path)

            elif extension == ".docx":
                text = self._extract_docx_text(source_document_path)

            else:
                # Assume plain text file
                text = source_document_path.read_text(
                    encoding="utf-8", errors="ignore"
                ).strip()

        except Exception as exc:
            logger.exception(f"Text extraction failed for {source_document_path}")
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
