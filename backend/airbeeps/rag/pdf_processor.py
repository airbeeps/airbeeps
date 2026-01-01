"""
PDF processing utilities for RAG system.
Extracts text per page and generates page thumbnails for preview.
"""

import logging
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PDFPage:
    """Represents a single PDF page with its content and metadata."""

    page_number: int  # 1-indexed
    text: str
    image_data: bytes | None = None  # PNG thumbnail
    width: int = 0
    height: int = 0


@dataclass
class PDFDocument:
    """Represents a processed PDF document."""

    pages: list[PDFPage]
    total_pages: int
    title: str | None = None


class PDFProcessor:
    """
    Processes PDF files to extract per-page text and generate thumbnails.
    Uses PyMuPDF (fitz) for both text extraction and rendering.
    """

    def __init__(
        self,
        thumbnail_dpi: int = 72,  # Lower DPI for thumbnails (72-150)
        max_thumbnail_width: int = 800,
    ):
        self.thumbnail_dpi = thumbnail_dpi
        self.max_thumbnail_width = max_thumbnail_width

    async def process_pdf(
        self,
        file_data: BytesIO,
        generate_thumbnails: bool = True,
        max_pages: int | None = None,
    ) -> PDFDocument:
        """
        Process a PDF file and extract pages with text and optional thumbnails.

        Args:
            file_data: PDF file data
            generate_thumbnails: Whether to generate page thumbnails
            max_pages: Maximum number of pages to process

        Returns:
            PDFDocument with pages containing text and thumbnails
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning(
                "PyMuPDF not available, falling back to text-only extraction"
            )
            return await self._fallback_extract(file_data, max_pages)

        pages: list[PDFPage] = []

        # Save to temp file for PyMuPDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            file_data.seek(0)
            temp_file.write(file_data.read())
            temp_file_path = temp_file.name

        try:
            doc = fitz.open(temp_file_path)
            total_pages = len(doc)
            pages_to_process = min(total_pages, max_pages) if max_pages else total_pages

            logger.info(
                f"Processing PDF with {total_pages} pages (extracting {pages_to_process})"
            )

            for page_num in range(pages_to_process):
                page = doc[page_num]

                # Extract text
                text = page.get_text("text").strip()

                # Generate thumbnail if requested
                image_data = None
                width, height = 0, 0

                if generate_thumbnails:
                    try:
                        # Render page to image
                        zoom = self.thumbnail_dpi / 72  # 72 is default DPI
                        matrix = fitz.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=matrix)

                        # Scale down if too wide
                        if pix.width > self.max_thumbnail_width:
                            scale = self.max_thumbnail_width / pix.width
                            matrix = fitz.Matrix(zoom * scale, zoom * scale)
                            pix = page.get_pixmap(matrix=matrix)

                        width, height = pix.width, pix.height
                        image_data = pix.tobytes("png")
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate thumbnail for page {page_num + 1}: {e}"
                        )

                pages.append(
                    PDFPage(
                        page_number=page_num + 1,  # 1-indexed
                        text=text,
                        image_data=image_data,
                        width=width,
                        height=height,
                    )
                )

            doc.close()

            # Try to get title from metadata
            title = None
            try:
                doc = fitz.open(temp_file_path)
                metadata = doc.metadata
                if metadata:
                    title = metadata.get("title")
                doc.close()
            except Exception:
                pass

            return PDFDocument(pages=pages, total_pages=total_pages, title=title)

        finally:
            # Clean up temp file
            Path(temp_file_path).unlink(missing_ok=True)

    async def _fallback_extract(
        self, file_data: BytesIO, max_pages: int | None = None
    ) -> PDFDocument:
        """Fallback extraction using pypdf when PyMuPDF is not available."""
        try:
            from pypdf import PdfReader

            file_data.seek(0)
            reader = PdfReader(file_data)
            total_pages = len(reader.pages)
            pages_to_process = min(total_pages, max_pages) if max_pages else total_pages

            pages: list[PDFPage] = []
            for i in range(pages_to_process):
                text = reader.pages[i].extract_text() or ""
                pages.append(
                    PDFPage(
                        page_number=i + 1,
                        text=text.strip(),
                        image_data=None,
                    )
                )

            return PDFDocument(pages=pages, total_pages=total_pages)

        except Exception as e:
            logger.error(f"Fallback PDF extraction failed: {e}")
            # Return empty document
            return PDFDocument(pages=[], total_pages=0)

    def get_page_thumbnail(
        self, file_data: BytesIO, page_number: int, dpi: int = 150
    ) -> bytes | None:
        """
        Generate a thumbnail for a specific page on-demand.

        Args:
            file_data: PDF file data
            page_number: Page number (1-indexed)
            dpi: Resolution for the thumbnail

        Returns:
            PNG image data or None if failed
        """
        try:
            import fitz

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                file_data.seek(0)
                temp_file.write(file_data.read())
                temp_file_path = temp_file.name

            try:
                doc = fitz.open(temp_file_path)
                if page_number < 1 or page_number > len(doc):
                    logger.warning(f"Invalid page number {page_number}")
                    return None

                page = doc[page_number - 1]  # 0-indexed
                zoom = dpi / 72
                matrix = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix)

                # Scale if too wide
                if pix.width > self.max_thumbnail_width:
                    scale = self.max_thumbnail_width / pix.width
                    matrix = fitz.Matrix(zoom * scale, zoom * scale)
                    pix = page.get_pixmap(matrix=matrix)

                image_data = pix.tobytes("png")
                doc.close()
                return image_data

            finally:
                Path(temp_file_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to generate page thumbnail: {e}")
            return None


# Singleton instance
pdf_processor = PDFProcessor()
