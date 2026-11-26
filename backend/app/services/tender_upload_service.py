import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from uuid import UUID

import pymupdf
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE_BYTES = 65536  # 64 KB bounded streaming chunks
PDF_MAGIC_PREFIX = b"%PDF-"
MAX_FILENAME_LENGTH = 255

ALLOWED_DOCUMENT_ROLES = {
    "PRIMARY_NIT",
    "TECHNICAL_SPEC",
    "BOQ",
    "CORRIGENDUM",
    "ANNEXURE",
    "OTHER",
}


def validate_document_role(role: str) -> str:
    """Validate and normalize tender document role."""
    cleaned = (role or "").strip().upper()
    if cleaned not in ALLOWED_DOCUMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document_role '{role}'. Allowed: {sorted(ALLOWED_DOCUMENT_ROLES)}.",
        )
    return cleaned


def sanitize_pdf_filename(raw_filename: Optional[str]) -> str:
    """Validate and sanitize an uploaded PDF filename without trusting path inputs."""
    if not raw_filename or not isinstance(raw_filename, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    cleaned = raw_filename.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not be empty.",
        )

    if "\x00" in cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: null bytes are forbidden.",
        )

    # Reject path traversal, absolute paths, and directory separators (POSIX & Windows)
    if (
        "/" in cleaned
        or "\\" in cleaned
        or ".." in cleaned
        or re.match(r"^[A-Za-z]:", cleaned)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: path separators or traversal sequences are not allowed.",
        )

    # Strip remaining non-printable control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
    if len(cleaned) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Filename exceeds maximum length of {MAX_FILENAME_LENGTH} characters.",
        )

    if not cleaned.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files (.pdf extension) are supported.",
        )

    return cleaned


def resolve_tenant_storage_path(
    organization_id: Optional[UUID],
    tender_id: UUID,
    document_id: UUID,
) -> Path:
    """Build and verify a tenant-partitioned, UUID-named PDF storage path inside UPLOAD_DIR."""
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    org_segment = str(organization_id) if organization_id else "platform"
    target_dir = (upload_root / org_segment / str(tender_id)).resolve()
    target_path = (target_dir / f"{document_id}.pdf").resolve()

    if not target_path.is_relative_to(upload_root):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolved storage path escaped upload root.",
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    return target_path


def cleanup_stored_file(file_path: Optional[Path]) -> None:
    """Safely remove a stored file on failure paths."""
    if not file_path:
        return
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError as exc:
        logger.warning(f"Failed to clean up file {file_path}: {exc}")


async def stream_validate_and_store_pdf(
    upload_file: UploadFile,
    dest_path: Path,
    max_upload_mb: Optional[int] = None,
) -> Tuple[int, str, int]:
    """Stream an uploaded PDF in bounded chunks, compute SHA-256, and validate PDF structure.

    Returns:
        Tuple of (file_size_bytes, sha256_hex_digest, total_pages).
    """
    limit_mb = max_upload_mb if max_upload_mb is not None else settings.MAX_UPLOAD_SIZE_MB
    max_bytes = limit_mb * 1024 * 1024

    hasher = hashlib.sha256()
    total_bytes = 0
    header_checked = False

    try:
        with open(dest_path, "wb") as out_file:
            while True:
                chunk = await upload_file.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Uploaded file exceeds maximum allowed size of {limit_mb} MB.",
                    )

                if not header_checked:
                    header_checked = True
                    if not chunk.startswith(PDF_MAGIC_PREFIX):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Invalid PDF content: missing %PDF- file signature.",
                        )

                hasher.update(chunk)
                out_file.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded PDF file is empty (0 bytes).",
            )

        # Structural PDF validation via PyMuPDF
        try:
            doc = pymupdf.open(str(dest_path))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid or corrupted PDF structure: {exc}",
            )

        try:
            if doc.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Encrypted PDFs are not supported. Please upload an unencrypted PDF.",
                )
            total_pages = len(doc)
            if total_pages <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="PDF contains 0 pages.",
                )
        finally:
            doc.close()

        return total_bytes, hasher.hexdigest(), total_pages

    except Exception:
        cleanup_stored_file(dest_path)
        raise
    finally:
        await upload_file.close()
