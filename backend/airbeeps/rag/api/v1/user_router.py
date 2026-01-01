import contextlib
import logging
import uuid as uuid_pkg
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.auth import current_active_user
from airbeeps.database import get_async_session
from airbeeps.files.storage import storage_service
from airbeeps.rag.models import Document
from airbeeps.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag")


@router.get(
    "/documents/preview-row",
    summary="Preview a row from an Excel/CSV document",
    description="Returns row data for a given sheet/row number. Requires ownership.",
)
async def preview_excel_row(
    row_number: int,
    file_path: str | None = None,
    document_id: uuid_pkg.UUID | None = None,
    sheet: str | None = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """
    Fetch a single row from an uploaded spreadsheet for the current user.
    """
    logger.debug(
        "User %s previewing row %s (doc_id=%s, file_path=%s), sheet=%s",
        current_user.id,
        row_number,
        document_id,
        file_path,
        sheet,
    )
    try:
        document = None

        # Prefer document lookup by ID when provided
        if document_id:
            doc_result = await session.execute(
                select(Document).where(
                    and_(Document.id == document_id, Document.status == "ACTIVE")
                )
            )
            document = doc_result.scalar_one_or_none()

        # Fallback to file_path lookup if no doc_id or doc not found
        if not document:
            if not file_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either document_id or file_path is required",
                )
            normalized_path = file_path.lstrip("/")
            doc_result = await session.execute(
                select(Document).where(
                    and_(
                        Document.file_path == normalized_path,
                        Document.status == "ACTIVE",
                    )
                )
            )
            document = doc_result.scalar_one_or_none()

        if not document:
            logger.warning("Document with file_path %s not found", file_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        if document.owner_id != current_user.id and not current_user.is_superuser:
            logger.warning(
                "User %s denied access to document %s", current_user.id, file_path
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # Use the canonical stored file path
        canonical_path = document.file_path
        file_bytes, _ = await storage_service.download_file(canonical_path)
        buffer = file_bytes if isinstance(file_bytes, BytesIO) else BytesIO(file_bytes)
        buffer.seek(0)

        sheets = pd.read_excel(buffer, sheet_name=None)
        if not sheets:
            logger.warning("No sheets found in Excel file %s", file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No sheets found in Excel file",
            )
        sheet_name = sheet if sheet and sheet in sheets else next(iter(sheets.keys()))
        df = sheets[sheet_name].dropna(axis=1, how="all")

        row_index = max(row_number - 2, 0)
        if row_index >= len(df):
            logger.warning("Row %s not found in file %s", row_number, file_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Row not found"
            )

        row = df.iloc[row_index]

        def _clean(val: Any):
            if pd.isna(val):
                return None
            # Normalize numpy / pandas scalars to native Python types
            if hasattr(val, "item"):
                with contextlib.suppress(Exception):
                    val = val.item()
            if isinstance(val, float) and val.is_integer():
                return int(val)
            return val

        row_data = {
            str(col): _clean(val) for col, val in row.items() if not pd.isna(val)
        }

        logger.debug("Successfully previewed row %s from %s", row_number, file_path)
        return {
            "sheet": sheet_name,
            "row_number": row_number,
            "row": row_data,
            "file_path": canonical_path,
            "document_id": str(document.id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to preview row %s from %s: %s",
            row_number,
            file_path,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview row: {exc}",
        )


@router.get(
    "/documents/preview-pdf-page",
    summary="Get a PDF page thumbnail",
    description="Returns a rendered image of a specific PDF page. Requires ownership.",
)
async def preview_pdf_page(
    page_number: int,
    file_path: str | None = None,
    document_id: uuid_pkg.UUID | None = None,
    dpi: int = 150,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """
    Render and return a PDF page as an image for preview.
    """
    logger.debug(
        "User %s previewing PDF page %s (doc_id=%s, file_path=%s)",
        current_user.id,
        page_number,
        document_id,
        file_path,
    )
    try:
        document = None

        # Prefer document lookup by ID when provided
        if document_id:
            doc_result = await session.execute(
                select(Document).where(
                    and_(Document.id == document_id, Document.status == "ACTIVE")
                )
            )
            document = doc_result.scalar_one_or_none()

        # Fallback to file_path lookup if no doc_id or doc not found
        if not document:
            if not file_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either document_id or file_path is required",
                )
            normalized_path = file_path.lstrip("/")
            doc_result = await session.execute(
                select(Document).where(
                    and_(
                        Document.file_path == normalized_path,
                        Document.status == "ACTIVE",
                    )
                )
            )
            document = doc_result.scalar_one_or_none()

        if not document:
            logger.warning("Document with file_path %s not found", file_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        if document.owner_id != current_user.id and not current_user.is_superuser:
            logger.warning(
                "User %s denied access to document %s", current_user.id, file_path
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # Check if it's a PDF
        if document.file_type != "pdf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is not a PDF",
            )

        # Download the PDF file
        canonical_path = document.file_path
        file_bytes, _ = await storage_service.download_file(canonical_path)
        buffer = file_bytes if isinstance(file_bytes, BytesIO) else BytesIO(file_bytes)
        buffer.seek(0)

        # Generate the page thumbnail
        from airbeeps.rag.pdf_processor import pdf_processor

        image_data = pdf_processor.get_page_thumbnail(
            buffer,
            page_number,
            dpi=min(dpi, 200),  # Cap DPI at 200 for performance
        )

        if not image_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page {page_number} not found or could not be rendered",
            )

        logger.debug(
            "Successfully rendered PDF page %s from %s (%d bytes)",
            page_number,
            file_path,
            len(image_data),
        )

        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Content-Disposition": f"inline; filename=page_{page_number}.png",
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to preview PDF page %s from %s: %s",
            page_number,
            file_path,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render PDF page: {exc}",
        )
