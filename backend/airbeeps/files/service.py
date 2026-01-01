"""
File management service for handling file operations and business logic.
"""

import base64
import hashlib
import io
import logging
import re
import urllib.parse
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import filetype
from defusedxml import ElementTree as DefusedET
from fastapi import Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.database import get_async_session

from .models import FileRecord, FileStatus, FileType
from .storage import storage_service

logger = logging.getLogger(__name__)

# Chunk size for streaming file reads (64KB)
STREAMING_CHUNK_SIZE = 64 * 1024

# SVG elements and attributes that could be dangerous (XSS vectors)
# Based on OWASP recommendations
SVG_DANGEROUS_TAGS = {
    "script",
    "foreignobject",
    "set",
    "animate",
    "animatemotion",
    "animatetransform",
    "handler",
    "listener",
}

SVG_DANGEROUS_ATTRS = {
    "onload",
    "onclick",
    "onerror",
    "onmouseover",
    "onmouseout",
    "onmousedown",
    "onmouseup",
    "onfocus",
    "onblur",
    "onchange",
    "onsubmit",
    "onreset",
    "onselect",
    "onkeydown",
    "onkeypress",
    "onkeyup",
    "onabort",
    "ondblclick",
    "onresize",
    "onscroll",
    "onunload",
    "href",  # Can be javascript:
}


def sanitize_svg(svg_content: bytes) -> bytes:
    """
    Sanitize SVG content by removing potentially dangerous elements and attributes.

    Args:
        svg_content: Raw SVG file content

    Returns:
        Sanitized SVG content as bytes

    Raises:
        HTTPException: If SVG is malformed or contains severe security issues
    """
    try:
        # Parse SVG using defusedxml to prevent XXE attacks
        # defusedxml automatically blocks entity expansion, external entities, etc.
        tree = DefusedET.fromstring(svg_content)
    except Exception as e:
        logger.warning(f"Failed to parse SVG: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid SVG file: could not parse XML content",
        )

    # Track if we removed anything for logging
    removed_elements = []
    removed_attrs = []

    def clean_element(element):
        """Recursively clean an element and its children."""
        # Remove dangerous child elements
        for child in list(element):
            # Get local tag name (strip namespace)
            tag_name = (
                child.tag.split("}")[-1].lower()
                if "}" in child.tag
                else child.tag.lower()
            )

            if tag_name in SVG_DANGEROUS_TAGS:
                removed_elements.append(tag_name)
                element.remove(child)
            else:
                clean_element(child)

        # Remove dangerous attributes
        attrs_to_remove = []
        for attr in element.attrib:
            # Get local attribute name (strip namespace)
            attr_name = attr.split("}")[-1].lower() if "}" in attr else attr.lower()

            # Check for dangerous event handlers
            if attr_name.startswith("on") or attr_name in SVG_DANGEROUS_ATTRS:
                attrs_to_remove.append(attr)

            # Check for javascript: URLs in href/xlink:href
            elif "href" in attr_name.lower():
                value = element.attrib[attr].strip().lower()
                if value.startswith("javascript:") or value.startswith(
                    "data:text/html"
                ):
                    attrs_to_remove.append(attr)

        for attr in attrs_to_remove:
            removed_attrs.append(attr)
            del element.attrib[attr]

    clean_element(tree)

    if removed_elements or removed_attrs:
        logger.warning(
            f"SVG sanitized: removed elements={removed_elements}, removed attrs={removed_attrs}"
        )

    # Convert back to bytes
    # Use xml declaration and proper encoding
    from xml.etree import ElementTree as ET

    return ET.tostring(tree, encoding="unicode").encode("utf-8")


# File size limits (in bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB
MAX_DOCUMENT_SIZE = 100 * 1024 * 1024  # 100MB

# Allowed file types
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}

ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

ALLOWED_TYPES_BY_FILE_TYPE = {
    FileType.AVATAR: ALLOWED_IMAGE_TYPES,
    FileType.DOCUMENT: ALLOWED_DOCUMENT_TYPES | ALLOWED_IMAGE_TYPES,
    FileType.IMAGE: ALLOWED_IMAGE_TYPES,  # Chat image attachments
}

SIZE_LIMITS_BY_FILE_TYPE = {
    FileType.AVATAR: MAX_AVATAR_SIZE,
    FileType.DOCUMENT: MAX_DOCUMENT_SIZE,
    FileType.IMAGE: MAX_AVATAR_SIZE,  # Same as avatar (5MB)
}


class FileService:
    """
    Service class for file management operations.

    Handles file validation, upload, download, and database operations.
    Integrates with S3 storage and maintains file metadata in database.
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    def _encode_filename_for_s3(self, filename: str) -> str:
        """
        Encode filename for S3 metadata to ensure ASCII compatibility.

        Args:
            filename: Original filename that may contain non-ASCII characters

        Returns:
            ASCII-safe encoded filename
        """
        try:
            # First try URL encoding
            encoded = urllib.parse.quote(filename, safe=".-_")
            # If still contains non-ASCII after URL encoding, use base64
            if not encoded.isascii():
                encoded = base64.b64encode(filename.encode("utf-8")).decode("ascii")
                encoded = f"b64_{encoded}"
            return encoded
        except Exception:
            # Fallback: use base64 encoding
            return f"b64_{base64.b64encode(filename.encode('utf-8')).decode('ascii')}"

    def _decode_filename_from_s3(self, encoded_filename: str) -> str:
        """
        Decode filename from S3 metadata.

        Args:
            encoded_filename: Encoded filename from S3 metadata

        Returns:
            Original filename
        """
        try:
            if encoded_filename.startswith("b64_"):
                # Base64 encoded
                encoded_data = encoded_filename[4:]  # Remove 'b64_' prefix
                return base64.b64decode(encoded_data).decode("utf-8")
            # URL encoded
            return urllib.parse.unquote(encoded_filename)
        except Exception:
            # If decoding fails, return as is
            return encoded_filename

    async def validate_file(
        self, file: UploadFile, file_type: FileType, max_size: int | None = None
    ) -> bytes:
        """
        Validate uploaded file against type and size constraints.

        Uses streaming reads to validate file size and magic bytes to validate
        actual content type (not just the declared Content-Type header).

        Args:
            file: Uploaded file to validate
            file_type: Expected file type category
            max_size: Maximum file size in bytes (optional override)

        Returns:
            The file content as bytes (already read for validation)

        Raises:
            HTTPException: If validation fails
        """
        logger.debug(
            f"Validating file: {file.filename}, type: {file_type}, size: {file.size}"
        )

        # Validate filename first
        if not file.filename or len(file.filename.strip()) == 0:
            logger.warning("File upload attempted with empty filename")
            raise HTTPException(status_code=400, detail="Filename is required")

        # Check for dangerous file extensions
        file_extension = Path(file.filename).suffix.lower()
        dangerous_extensions = {".exe", ".bat", ".cmd", ".com", ".scr", ".js", ".vbs"}
        if file_extension in dangerous_extensions:
            logger.warning(
                f"Dangerous file extension blocked: {file_extension} for {file.filename}"
            )
            raise HTTPException(
                status_code=415,
                detail=f"File extension {file_extension} is not allowed for security reasons",
            )

        # Determine size limit
        size_limit = max_size or SIZE_LIMITS_BY_FILE_TYPE.get(file_type, MAX_FILE_SIZE)

        # Streaming file size validation - read file in chunks
        # This prevents memory exhaustion from malicious large files with spoofed Content-Length
        chunks = []
        total_size = 0

        while True:
            chunk = await file.read(STREAMING_CHUNK_SIZE)
            if not chunk:
                break
            total_size += len(chunk)

            # Check size limit during streaming
            if total_size > size_limit:
                logger.warning(
                    f"File {file.filename} too large: {total_size} > {size_limit}"
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size: {size_limit / (1024 * 1024):.1f}MB",
                )
            chunks.append(chunk)

        file_content = b"".join(chunks)

        if total_size == 0:
            logger.warning(f"Empty file uploaded: {file.filename}")
            raise HTTPException(status_code=400, detail="File is empty")

        # Validate actual content type using magic bytes
        allowed_types = ALLOWED_TYPES_BY_FILE_TYPE.get(file_type, set())
        detected_mime: str | None = None

        try:
            # Detect actual MIME type from file content (magic bytes)
            kind = filetype.guess(file_content)
            detected_mime = kind.mime if kind else None

            if detected_mime:
                logger.debug(
                    f"Detected MIME type: {detected_mime}, declared: {file.content_type}"
                )
            else:
                logger.warning(
                    f"Could not detect MIME type for {file.filename}, "
                    f"relying on declared type: {file.content_type}"
                )

            # Check if detected type is in allowed types
            if detected_mime and detected_mime not in allowed_types:
                # Some flexibility for edge cases (e.g., text/plain detected as application/octet-stream)
                # but log the mismatch for security monitoring
                if file.content_type not in allowed_types:
                    logger.warning(
                        f"Unsupported file type for {file.filename}. "
                        f"Declared: {file.content_type}, Detected: {detected_mime}"
                    )
                    raise HTTPException(
                        status_code=415,
                        detail=f"Unsupported file type: {detected_mime}. "
                        f"Allowed types: {', '.join(allowed_types)}",
                    )
                else:
                    # Declared type is allowed, but magic detection differs
                    # This could be a spoofing attempt - log but allow if declared is valid
                    logger.warning(
                        f"Content-type mismatch for {file.filename}: "
                        f"declared={file.content_type}, detected={detected_mime}. Allowing declared type."
                    )
        except HTTPException:
            # Re-raise HTTP exceptions (our own validation errors)
            raise
        except Exception as e:
            logger.error(f"Magic byte detection failed for {file.filename}: {e}")
            # Fall back to declared content type check if magic fails
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported file type: {file.content_type}. "
                    f"Allowed types: {', '.join(allowed_types)}",
                )

        # Sanitize SVG files to prevent XSS
        if (
            file.content_type == "image/svg+xml"
            or detected_mime == "image/svg+xml"
            or (file.filename and file.filename.lower().endswith(".svg"))
        ):
            logger.info(f"Sanitizing SVG file: {file.filename}")
            file_content = sanitize_svg(file_content)

        logger.debug(f"File validation passed for {file.filename}")
        return file_content

    async def upload_file(
        self,
        file: UploadFile,
        file_type: FileType,
        user_id: UUID,
        metadata: dict | None = None,
    ) -> FileRecord:
        """
        Upload file to storage and create database record.

        Args:
            file: File to upload
            file_type: Type of file being uploaded
            user_id: ID of user uploading the file
            metadata: Additional metadata to store

        Returns:
            Created FileRecord instance

        Raises:
            HTTPException: If upload fails or validation fails
        """
        logger.info(
            f"Uploading file '{file.filename}' for user {user_id}, type: {file_type}"
        )

        # Validate file and get content (validation reads the file with streaming)
        file_content = await self.validate_file(file, file_type)

        # Compute hash for deduplication
        file_hash = hashlib.sha256(file_content).hexdigest()
        logger.debug(f"File hash computed: {file_hash}")

        # If an active file with the same hash already exists for this user, reuse it
        existing_file = await self.get_file_by_hash(file_hash, user_id=user_id)
        if existing_file:
            logger.info(
                f"Reusing existing file {existing_file.id} with matching hash for user {user_id}"
            )
            return existing_file

        # Create file record (use actual content size, not declared size)
        actual_file_size = len(file_content)
        file_record = FileRecord(
            filename=file.filename,
            content_type=file.content_type,
            file_size=actual_file_size,
            file_type=file_type.value,  # Convert enum to string
            uploaded_by=user_id,
            file_metadata=metadata or {},
            status="uploading",  # Use string instead of enum
            file_hash=file_hash,
        )

        self.db.add(file_record)
        await self.db.flush()  # Get the file ID
        logger.debug(f"Created file record with ID: {file_record.id}")

        try:
            # Upload to S3
            # Encode filename for S3 metadata to ensure ASCII compatibility
            encoded_filename = self._encode_filename_for_s3(file.filename)
            logger.debug(f"Encoded filename for S3: {encoded_filename}")

            file_path = await storage_service.upload_public_file(
                file_data=file_content,
                file_type=file_type.value,
                file_id=file_record.id,
                filename=encoded_filename,  # Use encoded filename for S3 metadata
                content_type=file.content_type,
                file_size=actual_file_size,
            )

            # Update file record with S3 key and public URL
            file_record.file_path = file_path
            file_record.status = "active"  # Use string instead of enum

            await self.db.commit()
            logger.info(
                f"File uploaded successfully: {file_record.id}, path: {file_path}"
            )

            return file_record

        except Exception as e:
            # Rollback database changes if upload fails
            await self.db.rollback()
            logger.error(f"File upload failed for {file.filename}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="File upload failed")

    async def get_public_url(self, file_path: str) -> str | None:
        """
        Get public URL for a file stored in S3.

        Args:
            file_path: Storage key/path of the file

        Returns:
            Public URL string or None if generation fails
        """
        logger.debug(f"Getting public URL for file path: {file_path}")
        try:
            url = await storage_service.get_public_url(file_path)
            logger.debug(f"Generated public URL for {file_path}")
            return url
        except Exception as e:
            logger.error(
                f"Failed to get public URL for {file_path}: {e}", exc_info=True
            )
            return None

    async def get_file_by_id(self, file_id: UUID) -> FileRecord | None:
        """
        Get file record by ID.

        Args:
            file_id: File identifier

        Returns:
            FileRecord if found, None otherwise
        """
        stmt = select(FileRecord).where(FileRecord.id == file_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_file_by_path(self, file_path: str) -> FileRecord | None:
        """
        Get file record by file path.

        Args:
            file_path: File path/storage key

        Returns:
            FileRecord if found, None otherwise
        """
        stmt = select(FileRecord).where(
            FileRecord.file_path == file_path,
            FileRecord.status
            == FileStatus.ACTIVE.value,  # use string value for SQLite binding
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_file_by_hash(
        self, file_hash: str, user_id: UUID | None = None
    ) -> FileRecord | None:
        """
        Get an active file record by its content hash (optionally scoped to a user).
        """
        stmt = select(FileRecord).where(
            FileRecord.file_hash == file_hash,
            FileRecord.status == FileStatus.ACTIVE.value,
        )
        if user_id:
            stmt = stmt.where(FileRecord.uploaded_by == user_id)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_files(
        self,
        user_id: UUID,
        file_type: FileType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FileRecord]:
        """
        Get files uploaded by a specific user.

        Args:
            user_id: User identifier
            file_type: Optional file type filter
            limit: Maximum number of files to return
            offset: Pagination offset

        Returns:
            List of FileRecord instances
        """
        stmt = select(FileRecord).where(
            FileRecord.uploaded_by == user_id,
            FileRecord.status
            == FileStatus.ACTIVE.value,  # use string value for SQLite binding
        )

        if file_type:
            # file_type may be enum; store as string in DB
            stmt = stmt.where(
                FileRecord.file_type == getattr(file_type, "value", file_type)
            )

        stmt = stmt.order_by(FileRecord.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def download_file(self, file_id: UUID) -> tuple[BinaryIO, str, str]:
        """
        Download file content from storage.

        Args:
            file_id: File identifier

        Returns:
            Tuple of (file_content, content_type, filename)

        Raises:
            HTTPException: If file not found or download fails
        """
        logger.debug(f"Downloading file {file_id}")
        file_record = await self.get_file_by_id(file_id)
        if not file_record:
            logger.warning(f"File {file_id} not found")
            raise HTTPException(status_code=404, detail="File not found")

        if file_record.status != FileStatus.ACTIVE:
            logger.warning(
                f"File {file_id} is not active, status: {file_record.status}"
            )
            raise HTTPException(status_code=410, detail="File is no longer available")

        try:
            file_data, content_type = await storage_service.download_file(
                file_record.s3_key
            )
            logger.info(f"Successfully downloaded file {file_id}")
            return file_data, content_type, file_record.filename

        except Exception as e:
            logger.error(f"File download failed for {file_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="File download failed")

    async def delete_file(self, file_id: UUID, user_id: UUID) -> bool:
        """
        Delete file from storage and mark as deleted in database.

        Args:
            file_id: File identifier
            user_id: ID of user requesting deletion

        Returns:
            True if deletion successful, False otherwise

        Raises:
            HTTPException: If file not found or user not authorized
        """
        logger.info(f"Deleting file {file_id} by user {user_id}")
        file_record = await self.get_file_by_id(file_id)
        if not file_record:
            logger.warning(f"File {file_id} not found for deletion")
            raise HTTPException(status_code=404, detail="File not found")

        # Check user authorization (users can only delete their own files)
        if file_record.uploaded_by != user_id:
            logger.warning(
                f"User {user_id} not authorized to delete file {file_id} (owned by {file_record.uploaded_by})"
            )
            raise HTTPException(
                status_code=403, detail="Not authorized to delete this file"
            )

        try:
            # Delete from storage
            if file_record.file_path:
                logger.debug(f"Deleting file from storage: {file_record.file_path}")
                await storage_service.delete_file(file_record.file_path)

            # Mark as deleted in database
            file_record.status = FileStatus.DELETED
            await self.db.commit()

            logger.info(f"File deleted successfully: {file_id}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"File deletion failed for {file_id}: {e}", exc_info=True)
            return False

    async def generate_download_url(
        self, file_id: UUID, expiration: int = 3600
    ) -> str | None:
        """
        Generate presigned URL for file download.

        Args:
            file_id: File identifier
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL string or None if generation fails
        """
        file_record = await self.get_file_by_id(file_id)
        if not file_record or file_record.status != FileStatus.ACTIVE:
            return None

        return await storage_service.generate_presigned_url(
            file_record.s3_key, expiration=expiration
        )

    async def update_file_metadata(
        self, file_id: UUID, user_id: UUID, metadata: dict
    ) -> FileRecord | None:
        """
        Update file metadata.

        Args:
            file_id: File identifier
            user_id: ID of user updating metadata
            metadata: New metadata to set

        Returns:
            Updated FileRecord or None if not found/authorized
        """
        file_record = await self.get_file_by_id(file_id)
        if not file_record:
            return None

        # Check user authorization
        if file_record.uploaded_by != user_id:
            raise HTTPException(
                status_code=403, detail="Not authorized to update this file"
            )

        file_record.file_metadata = metadata
        await self.db.commit()

        return file_record


def get_file_service():
    """Dependency factory to get FileService instance."""

    async def _get_service(
        session: AsyncSession = Depends(get_async_session),
    ) -> FileService:
        return FileService(session)

    return _get_service
