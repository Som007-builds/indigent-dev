from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

from .chunking import source_sha256
from .models import Document


class OCRAdapter:
    """Local OCR adapter using PyMuPDF + Tesseract.

    Renders PDF pages as images via PyMuPDF, then runs Tesseract OCR on each page.
    Fails closed if Tesseract is not available or OCR fails.
    """

    def __init__(self, *, tesseract_path: Optional[str] = None, dpi: int = 300):
        self.tesseract_path = tesseract_path or shutil.which("tesseract")
        self.dpi = dpi
        self._available = self._check_tesseract()

    def _check_tesseract(self) -> bool:
        if self.tesseract_path is None:
            return False
        try:
            result = subprocess.run(
                [self.tesseract_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @property
    def available(self) -> bool:
        return self._available

    def extract_text_from_image(self, image: Image.Image) -> str:
        """Extract text from a PIL Image using Tesseract."""
        if not self._available:
            raise RuntimeError("Tesseract OCR engine not available")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            try:
                image.save(tmp.name, format="PNG")
                result = subprocess.run(
                    [self.tesseract_path, tmp.name, "stdout", "-l", "eng"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
                return result.stdout.strip()
            except (OSError, subprocess.SubprocessError) as error:
                raise RuntimeError(f"Tesseract OCR failed: {error}") from error
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    def extract_from_pdf(self, path: Path) -> Document:
        """Extract text from PDF using OCR on each page.

        Renders each page as an image and runs OCR. Preserves page boundaries.
        """
        if not self._available:
            raise RuntimeError("Tesseract OCR engine not available; install tesseract")

        try:
            import fitz
        except ImportError as error:
            raise RuntimeError("PyMuPDF is required for PDF rendering") from error

        pages_text: list[str] = []
        page_starts: list[int] = []
        parts: list[str] = []
        offset = 0

        with fitz.open(path) as pdf:
            for page_num in range(len(pdf)):
                page = pdf[page_num]
                # Render page at specified DPI
                mat = fitz.Matrix(self.dpi / 72.0, self.dpi / 72.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

                text = self.extract_text_from_image(img)
                pages_text.append(text)

                page_starts.append(offset)
                parts.append(text)
                offset += len(text) + 1

        text = "\n".join(parts)

        return Document(
            document_id=path.stem,
            source_path=str(path),
            source_hash=source_sha256(path),
            text=text,
            mime="application/pdf",
            metadata={"page_count": len(pages_text), "page_starts": page_starts},
        )

    def extract_from_image(self, path: Path) -> Document:
        """Extract text from an image file using OCR."""
        if not self._available:
            raise RuntimeError("Tesseract OCR engine not available; install tesseract")

        try:
            img = Image.open(path)
            img.load()
        except (OSError, ImportError) as error:
            raise RuntimeError(f"Failed to open image: {error}") from error

        text = self.extract_text_from_image(img)

        return Document(
            document_id=path.stem,
            source_path=str(path),
            source_hash=source_sha256(path),
            text=text,
            mime="image/" + path.suffix.lower().lstrip("."),
            metadata={"page_count": 1, "page_starts": [0]},
        )


class MockOCRAdapter:
    """Mock OCR adapter for testing without Tesseract."""

    def __init__(self, *, should_fail: bool = False, text: str = "mock ocr text"):
        self.should_fail = should_fail
        self.text = text

    @property
    def available(self) -> bool:
        return not self.should_fail

    def extract_from_pdf(self, path) -> "Document":
        if self.should_fail:
            raise RuntimeError("Mock OCR unavailable")
        return Document(
            document_id=Path(path).stem,
            source_path=str(path),
            source_hash=source_sha256(Path(path)),
            text=self.text,
            mime="application/pdf",
            metadata={"page_count": 1, "page_starts": [0]},
        )

    def extract_from_image(self, path) -> "Document":
        if self.should_fail:
            raise RuntimeError("Mock OCR unavailable")
        return Document(
            document_id=Path(path).stem,
            source_path=str(path),
            source_hash=source_sha256(Path(path)),
            text=self.text,
            mime="image/png",
            metadata={"page_count": 1, "page_starts": [0]},
        )