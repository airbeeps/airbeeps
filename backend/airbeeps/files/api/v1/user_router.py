"""
File upload endpoints.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from airbeeps.auth.fastapi_users import current_user
from airbeeps.files.models import FileType
from airbeeps.files.service import FileService, get_file_service
from airbeeps.files.storage import storage_service
from airbeeps.users.models import User

router = APIRouter()


class FileResponse(BaseModel):
    """Response model for file information."""

    id: UUID
    filename: str
    content_type: str
    file_size: int
    file_type: FileType
    file_path: str | None = None
    created_at: str
    metadata: dict
    url: str | None = None  # Download URL for the file

    class Config:
        from_attributes = True


class FileListResponse(BaseModel):
    """Response model for file list."""

    files: list[FileResponse]
    total: int


class FileUrlResponse(BaseModel):
    """Response model for file URL."""

    file_key: str
    url: str | None = None
    message: str | None = None


@router.post("/files/upload", response_model=FileResponse)
async def upload_file(
    file: UploadFile = File(...),
    file_type: FileType = Form(...),
    metadata: str | None = Form(None),
    current_user: User = Depends(current_user),
    file_service: FileService = Depends(get_file_service()),
):
    """
    Upload a file to the system.

    - **file**: The file to upload
    - **file_type**: Type of file (avatar, document)
    - **metadata**: Optional JSON string with additional file metadata
    - **Returns**: File information including ID and storage details
    """

    # Parse metadata if provided
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    # Upload file
    file_record = await file_service.upload_file(
        file=file,
        file_type=file_type,
        user_id=current_user.id,
        metadata=parsed_metadata,
    )

    # Generate download URL for the uploaded file
    download_url = await file_service.get_public_url(file_path=file_record.file_path)

    return FileResponse(
        id=file_record.id,
        filename=file_record.filename,
        content_type=file_record.content_type,
        file_size=file_record.file_size,
        file_type=file_record.file_type,
        file_path=file_record.file_path,
        created_at=file_record.created_at.isoformat(),
        metadata=file_record.file_metadata,
        url=download_url,
    )


@router.get("/files/url/{file_key:path}", response_model=FileUrlResponse)
async def get_file_url(
    file_key: str,
    current_user: User = Depends(current_user),
    file_service: FileService = Depends(get_file_service()),
):
    """
    Get public URL for a file by its file key (file path).

    - **file_key**: The file key/path (e.g., "avatars/user123/avatar.jpg")
    - **Returns**: Public URL for accessing the file
    """

    # Get public URL for the file
    public_url = await file_service.get_public_url(file_key)

    if public_url:
        return FileUrlResponse(
            file_key=file_key, url=public_url, message="URL generated successfully"
        )
    return FileUrlResponse(
        file_key=file_key, url=None, message="Failed to generate URL for the file"
    )


@router.get("/files/public-url/{file_key:path}", response_model=FileUrlResponse)
async def get_public_file_url(
    file_key: str,
    file_service: FileService = Depends(get_file_service()),
):
    """
    Get public URL for a file by its file key (file path) - No authentication required.

    - **file_key**: The file key/path (e.g., "avatar/2024/01/01/uuid.jpg")
    - **Returns**: Public URL for accessing the file

    Note: This endpoint is public but ONLY allows access to avatar files.
    Other file types require authentication via /files/url/{file_key}.
    """
    # Security: Only allow public access to avatar files
    # Avatar files are stored with paths like "avatar/YYYY/MM/DD/uuid.ext"
    if not file_key.startswith("avatar/"):
        raise HTTPException(
            status_code=403,
            detail="Public access is only allowed for avatar files. Use authenticated endpoint for other files.",
        )

    # Get public URL for the file
    public_url = await file_service.get_public_url(file_key)

    if public_url:
        return FileUrlResponse(
            file_key=file_key, url=public_url, message="URL generated successfully"
        )
    return FileUrlResponse(
        file_key=file_key, url=None, message="Failed to generate URL for the file"
    )


@router.get("/files/download/{file_key:path}")
async def download_file_by_path(
    file_key: str,
    current_user: User = Depends(current_user),
):
    """
    Download/view file by its file key (storage path).

    - **file_key**: The file key/path (e.g., "document/2024/01/01/uuid.pdf")
    - **Returns**: File content as streaming response

    Note: Requires authentication.
    """
    try:
        # Check if file exists
        exists = await storage_service.file_exists(file_key)
        if not exists:
            raise HTTPException(status_code=404, detail="File not found")

        # Download file from storage
        file_data, content_type = await storage_service.download_file(file_key)

        # Extract filename from file_key for Content-Disposition
        filename = file_key.split("/")[-1] if "/" in file_key else file_key

        # For PDFs and images, use inline disposition for viewing in browser
        if content_type in [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
        ]:
            disposition = f'inline; filename="{filename}"'
        else:
            disposition = f'attachment; filename="{filename}"'

        return StreamingResponse(
            file_data,
            media_type=content_type,
            headers={"Content-Disposition": disposition},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
