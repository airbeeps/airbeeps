"""
Document content extraction service for RAG system.
"""

import logging
import mimetypes
import os
import re
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException

from airbeeps.files.service import FileService

logger = logging.getLogger(__name__)


def parse_page_range(page_range: str, total_pages: int) -> list[int]:
    """
    Parse a page range string into a list of 0-indexed page numbers.

    Args:
        page_range: Page range string, e.g., '1-5,8,10-12'
        total_pages: Total number of pages in the document

    Returns:
        List of 0-indexed page numbers, e.g., [0,1,2,3,4,7,9,10,11]

    Examples:
        >>> parse_page_range("1-5", 10)
        [0, 1, 2, 3, 4]
        >>> parse_page_range("1,3,5-7", 10)
        [0, 2, 4, 5, 6]
        >>> parse_page_range("1-100", 10)  # Clamps to available pages
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    """
    if not page_range or not page_range.strip():
        return list(range(total_pages))

    pages = set()
    parts = page_range.replace(" ", "").split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            # Range like "1-5"
            match = re.match(r"^(\d+)-(\d+)$", part)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                # Convert to 0-indexed and clamp
                start = max(0, start - 1)
                end = min(total_pages - 1, end - 1)
                for i in range(start, end + 1):
                    pages.add(i)
        # Single page like "8"
        elif part.isdigit():
            page_num = int(part) - 1  # Convert to 0-indexed
            if 0 <= page_num < total_pages:
                pages.add(page_num)

    return sorted(pages)


class DocumentContentExtractor:
    """Document content extractor"""

    def __init__(self, file_service: FileService, max_pdf_pages: int | None = None):
        self.file_service = file_service
        self.max_pdf_pages = max_pdf_pages

    async def extract_from_file_path(
        self,
        file_path: str,
        filename: str | None = None,
        max_pdf_pages: int | None = None,
    ) -> tuple[str, str]:
        """
        Extract document content and title from file path

        Args:
            file_path: File storage path (S3 key)
            filename: Original filename (optional, used to infer file type)

        Returns:
            Tuple[title, content]: Document title and content

        Raises:
            HTTPException: If file does not exist or extraction fails
        """
        logger.info(f"Extracting content from file: {file_path}, filename: {filename}")
        try:
            # Download file from storage service
            file_data, content_type = await self._download_file_from_storage(file_path)

            # If filename is not provided, try to infer from file_path
            if not filename:
                filename = os.path.basename(file_path)

            logger.debug(f"Content type: {content_type}, filename: {filename}")

            # Check PDF page limit
            effective_max_pages = max_pdf_pages or self.max_pdf_pages
            ext = Path(filename).suffix.lower() if filename else ""
            if ext == ".pdf" and effective_max_pages:
                page_count = await self._get_pdf_page_count(file_data)
                if page_count > effective_max_pages:
                    logger.warning(
                        f"PDF {file_path} has {page_count} pages, exceeds limit of {effective_max_pages}"
                    )
                    # Truncate by extracting only first N pages
                    file_data = await self._truncate_pdf(file_data, effective_max_pages)

            # Extract content by content type
            content = await self._extract_content_by_type(
                file_data, content_type, filename
            )

            # Extract title from filename (remove extension)
            title = self._extract_title_from_filename(filename)

            logger.info(
                f"Successfully extracted content from {file_path}: title='{title}', content_length={len(content)}"
            )
            return title, content

        except Exception as e:
            logger.error(
                f"Failed to extract content from file {file_path}: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=400, detail=f"Failed to extract content from file: {e!s}"
            )

    async def _download_file_from_storage(self, file_path: str) -> tuple[BytesIO, str]:
        """Download file from storage service"""
        logger.debug(f"Downloading file from storage: {file_path}")
        try:
            from airbeeps.files.storage import storage_service

            file_data, content_type = await storage_service.download_file(file_path)
            logger.debug(
                f"Successfully downloaded file {file_path}, content_type: {content_type}"
            )
            return file_data, content_type
        except Exception as e:
            logger.error(
                f"Failed to download file from storage {file_path}: {e}", exc_info=True
            )
            raise HTTPException(status_code=404, detail="File not found in storage")

    async def _extract_content_by_type(
        self, file_data: BytesIO, content_type: str, filename: str
    ) -> str:
        """Extract content by file type"""

        # Reset file pointer
        file_data.seek(0)

        # Prefer content_type, if undetermined infer from file extension
        if not content_type or content_type == "application/octet-stream":
            content_type, _ = mimetypes.guess_type(filename)

        if not content_type:
            # If still undetermined, try to infer from extension
            ext = Path(filename).suffix.lower()
            content_type = self._get_content_type_from_extension(ext)

        logger.info(
            f"Extracting content for file {filename} with content type: {content_type}"
        )

        # Use markitdown for unified document processing
        try:
            # Save file to temporary location
            import tempfile

            from markitdown import MarkItDown

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(filename).suffix
            ) as temp_file:
                file_data.seek(0)
                temp_file.write(file_data.read())
                temp_file_path = temp_file.name

            try:
                md = MarkItDown()
                result = md.convert(temp_file_path)
                content = result.text_content

                if not content.strip():
                    raise ValueError("No text content extracted from file")

                return content.strip()
            finally:
                # Clean up temporary file
                Path(temp_file_path).unlink()

        except ImportError:
            logger.warning("markitdown not available, falling back to basic extraction")
            # If markitdown is not available, fallback to basic text extraction
            return await self._extract_text_content(file_data)
        except Exception as e:
            logger.warning(
                f"markitdown extraction failed: {e}, falling back to basic extraction"
            )
            # If markitdown fails, fallback to basic text extraction
            return await self._extract_text_content(file_data)

    def _get_content_type_from_extension(self, ext: str) -> str:
        """Infer content type from file extension"""
        ext_mapping = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".csv": "text/csv",
            ".json": "application/json",
            ".xml": "application/xml",
            ".html": "text/html",
            ".htm": "text/html",
        }
        return ext_mapping.get(ext, "text/plain")

    async def _extract_text_content(self, file_data: BytesIO) -> str:
        """Extract plain text content"""
        try:
            # Try multiple encodings
            encodings = ["utf-8", "gbk", "gb2312", "latin-1"]

            for encoding in encodings:
                try:
                    file_data.seek(0)
                    content = file_data.read().decode(encoding)
                    logger.info(f"Successfully decoded text with encoding: {encoding}")
                    return content.strip()
                except UnicodeDecodeError:
                    continue

            # If all encodings fail, use error handling
            file_data.seek(0)
            content = file_data.read().decode("utf-8", errors="ignore")
            logger.warning("Fallback to utf-8 with error handling")
            return content.strip()

        except Exception as e:
            logger.error(f"Failed to extract text content: {e}")
            raise HTTPException(
                status_code=400, detail="Failed to extract text content"
            )

    def _extract_title_from_filename(self, filename: str) -> str:
        if not filename:
            return "Untitled Document"

        title = Path(filename).stem

        title = title.replace("_", " ").replace("-", " ")

        title = " ".join(word.capitalize() for word in title.split())

        return title or "Untitled Document"

    async def _get_pdf_page_count(self, file_data: BytesIO) -> int:
        """Get the number of pages in a PDF file."""
        file_data.seek(0)
        try:
            # Try PyPDF2 first
            from pypdf import PdfReader

            reader = PdfReader(file_data)
            count = len(reader.pages)
            file_data.seek(0)
            return count
        except ImportError:
            try:
                # Fallback to PyPDF2 (older name)
                from PyPDF2 import PdfReader

                reader = PdfReader(file_data)
                count = len(reader.pages)
                file_data.seek(0)
                return count
            except ImportError:
                logger.warning(
                    "No PDF library available for page counting, skipping limit check"
                )
                file_data.seek(0)
                return 0
        except Exception as e:
            logger.warning(f"Failed to count PDF pages: {e}")
            file_data.seek(0)
            return 0

    async def _truncate_pdf(self, file_data: BytesIO, max_pages: int) -> BytesIO:
        """Truncate a PDF to the first N pages."""
        file_data.seek(0)
        try:
            from pypdf import PdfReader, PdfWriter

            reader = PdfReader(file_data)
            writer = PdfWriter()

            for i in range(min(max_pages, len(reader.pages))):
                writer.add_page(reader.pages[i])

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            logger.info(f"Truncated PDF from {len(reader.pages)} to {max_pages} pages")
            return output
        except ImportError:
            try:
                from PyPDF2 import PdfReader, PdfWriter

                reader = PdfReader(file_data)
                writer = PdfWriter()

                for i in range(min(max_pages, len(reader.pages))):
                    writer.add_page(reader.pages[i])

                output = BytesIO()
                writer.write(output)
                output.seek(0)
                logger.info(
                    f"Truncated PDF from {len(reader.pages)} to {max_pages} pages"
                )
                return output
            except ImportError:
                logger.warning(
                    "No PDF library available for truncation, using full PDF"
                )
                file_data.seek(0)
                return file_data
        except Exception as e:
            logger.warning(f"Failed to truncate PDF: {e}, using full PDF")
            file_data.seek(0)
            return file_data

    async def extract_pdf_with_pages(
        self,
        file_path: str,
        filename: str | None = None,
        max_pages: int | None = None,
        page_range: str | None = None,
    ) -> tuple[str, str, list[dict]]:
        """
        Extract PDF content with page-level information.

        Args:
            file_path: File storage path
            filename: Original filename
            max_pages: Maximum pages to process
            page_range: Optional page range string, e.g., '1-50' or '1,3,5-10'

        Returns:
            Tuple of (title, full_content, pages_data)
            where pages_data is a list of {"page": int, "text": str}
        """
        logger.info(
            f"Extracting PDF with page tracking: {file_path}, page_range={page_range}"
        )

        file_data, _ = await self._download_file_from_storage(file_path)

        if not filename:
            filename = os.path.basename(file_path)

        title = self._extract_title_from_filename(filename)

        # Try using our PDF processor for page-level extraction
        try:
            from airbeeps.rag.pdf_processor import pdf_processor

            pdf_doc = await pdf_processor.process_pdf(
                file_data,
                generate_thumbnails=False,  # Don't generate thumbnails during extraction
                max_pages=max_pages,
            )

            # Determine which pages to include
            total_pages = len(pdf_doc.pages)
            if page_range:
                pages_to_include = set(parse_page_range(page_range, total_pages))
            else:
                pages_to_include = set(range(total_pages))

            pages_data = []
            full_content_parts = []

            for page in pdf_doc.pages:
                # page.page_number is 1-indexed, convert to 0-indexed for comparison
                if (page.page_number - 1) not in pages_to_include:
                    continue

                if page.text.strip():
                    # Add page marker to full content for reference
                    full_content_parts.append(f"[Page {page.page_number}]\n{page.text}")
                    pages_data.append(
                        {
                            "page": page.page_number,
                            "text": page.text,
                        }
                    )

            full_content = "\n\n".join(full_content_parts)

            logger.info(
                f"Extracted {len(pages_data)} pages from PDF (of {total_pages} total), "
                f"total chars: {len(full_content)}"
            )

            return title, full_content, pages_data

        except Exception as e:
            logger.warning(
                f"Page-level PDF extraction failed: {e}, falling back to standard extraction"
            )
            # Fallback to standard extraction without page info
            title, content = await self.extract_from_file_path(
                file_path, filename, max_pages
            )
            return title, content, []
