import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import pymupdf
from sqlalchemy import and_, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tender import Tender, TenderDocument, TenderDocumentPage, TenderProcessingJob, TenderRequirement
from app.schemas.bidder import ExtractionMethod
from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.requirement_extractor import (
    RequirementExtractionProviderError,
    TenderRequirementExtractionService,
)

logger = logging.getLogger(__name__)

NON_RETRYABLE_ERROR_CODES = {
    "FILE_NOT_FOUND",
    "STORAGE_PATH_INVALID",
    "INTEGRITY_SIZE_MISMATCH",
    "INTEGRITY_HASH_MISMATCH",
    "PAGE_LIMIT_EXCEEDED",
    "INVALID_PDF",
    "PAGE_EXTRACTION_INCOMPLETE",
    "NO_EXTRACTED_PAGES",
}

ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "RETRY_WAIT")


class JobProcessingError(Exception):
    """Structured, sanitized processing failure."""

    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def map_job_status_to_document_status(job_status: str) -> str:
    if job_status == "QUEUED":
        return "QUEUED"
    if job_status in ("RUNNING", "RETRY_WAIT"):
        return "PROCESSING"
    if job_status == "SUCCEEDED":
        return "READY"
    return "FAILED"


async def set_worker_rls_context(
    db: AsyncSession,
    organization_id: Optional[UUID] = None,
    is_super_admin: bool = True,
) -> None:
    """Set transaction-local PostgreSQL RLS context for worker operations."""
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT set_config('app.is_super_admin', :sa, true)"),
            {"sa": "true" if is_super_admin else "false"},
        )
        await db.execute(
            text("SELECT set_config('app.current_org_id', :oid, true)"),
            {"oid": str(organization_id) if organization_id else ""},
        )


def _verify_file_and_page_count_sync(
    storage_path_str: str,
    expected_size: int,
    expected_sha256: str,
    max_pages: int,
) -> Tuple[Path, int]:
    """Verify stored PDF path, existence, size, SHA-256, and page-count cap."""
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    resolved = Path(storage_path_str).resolve()
    if not resolved.is_relative_to(upload_root):
        raise JobProcessingError(
            "STORAGE_PATH_INVALID",
            "Stored document path failed security root validation.",
            retryable=False,
        )

    if not resolved.exists() or not resolved.is_file():
        raise JobProcessingError(
            "FILE_NOT_FOUND",
            "Stored PDF file is missing from document storage.",
            retryable=False,
        )

    actual_size = resolved.stat().st_size
    if actual_size != expected_size:
        raise JobProcessingError(
            "INTEGRITY_SIZE_MISMATCH",
            "Stored PDF size does not match persisted metadata.",
            retryable=False,
        )

    hasher = hashlib.sha256()
    with open(resolved, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    if hasher.hexdigest() != expected_sha256:
        raise JobProcessingError(
            "INTEGRITY_HASH_MISMATCH",
            "Stored PDF SHA-256 digest failed integrity verification.",
            retryable=False,
        )

    try:
        doc = pymupdf.open(str(resolved))
    except Exception:
        raise JobProcessingError(
            "INVALID_PDF",
            "Stored file could not be opened as a valid PDF.",
            retryable=False,
        )

    try:
        if doc.is_encrypted:
            raise JobProcessingError(
                "INVALID_PDF",
                "Encrypted PDFs are not supported for page extraction.",
                retryable=False,
            )
        page_count = len(doc)
    finally:
        doc.close()

    if page_count <= 0:
        raise JobProcessingError(
            "INVALID_PDF",
            "PDF contains zero extractable pages.",
            retryable=False,
        )

    if page_count > max_pages:
        raise JobProcessingError(
            "PAGE_LIMIT_EXCEEDED",
            f"PDF has {page_count} pages, exceeding the configured maximum of {max_pages} pages.",
            retryable=False,
        )

    return resolved, page_count


def _derive_page_extraction_status(method: str) -> str:
    if method == ExtractionMethod.EMPTY_SCANNED.value:
        return "EMPTY"
    if method == ExtractionMethod.OCR_FAILED.value:
        return "FAILED"
    return "SUCCEEDED"


async def recover_expired_leases(db: AsyncSession) -> int:
    """Reconcile RUNNING jobs with expired leases and advance ownership_generation."""
    await set_worker_rls_context(db, is_super_admin=True)
    now = datetime.now(timezone.utc)
    is_pg = bool(db.bind and db.bind.dialect.name == "postgresql")
    stmt = select(TenderProcessingJob).where(
        TenderProcessingJob.status == "RUNNING",
        TenderProcessingJob.lease_expires_at.is_not(None),
        TenderProcessingJob.lease_expires_at < now,
    )
    if is_pg:
        stmt = stmt.with_for_update(skip_locked=True)
    expired_jobs = (await db.execute(stmt)).scalars().all()
    recovered = 0

    for job in expired_jobs:
        job.ownership_generation = (job.ownership_generation or 0) + 1
        if job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = "QUEUED"
            job.current_stage = "QUEUED"
            job.worker_id = None
            job.lease_expires_at = None
            job.error_code = "LEASE_EXPIRED"
            job.error_message = "Worker lease expired; job automatically re-queued."
            doc_status = "QUEUED"
        else:
            job.status = "FAILED"
            job.current_stage = "FAILED"
            job.completed_at = now
            job.lease_expires_at = None
            job.error_code = "LEASE_EXPIRED_MAX_RETRIES"
            job.error_message = "Worker lease expired and maximum retry attempts were exhausted."
            doc_status = "FAILED"

        await db.execute(
            update(TenderDocument)
            .where(TenderDocument.id == job.tender_document_id)
            .values(processing_status=doc_status)
        )
        recovered += 1

    if recovered:
        await db.commit()
    return recovered


async def claim_next_job_fenced(db: AsyncSession, worker_id: str) -> Optional[Tuple[UUID, int]]:
    """Atomically claim the oldest QUEUED job and return (job_id, new_ownership_generation)."""
    await set_worker_rls_context(db, is_super_admin=True)
    now = datetime.now(timezone.utc)
    lease_until = now + timedelta(seconds=settings.JOB_LEASE_SECONDS)

    is_pg = bool(db.bind and db.bind.dialect.name == "postgresql")
    if is_pg:
        stmt = (
            select(TenderProcessingJob)
            .where(TenderProcessingJob.status == "QUEUED")
            .order_by(TenderProcessingJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            return None

        new_gen = (job.ownership_generation or 0) + 1
        job.status = "RUNNING"
        job.worker_id = worker_id
        job.ownership_generation = new_gen
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.lease_expires_at = lease_until
        job.current_stage = "VALIDATING_DOCUMENT"
        job.progress_pct = max(job.progress_pct, 5)

        if job.job_type == "PAGE_EXTRACTION":
            await db.execute(
                update(TenderDocument)
                .where(TenderDocument.id == job.tender_document_id)
                .values(processing_status="PROCESSING")
            )
        await db.commit()
        return job.id, new_gen

    # SQLite fallback: conditional atomic UPDATE with ownership_generation fence
    cand = (
        await db.execute(
            select(TenderProcessingJob.id, TenderProcessingJob.ownership_generation)
            .where(TenderProcessingJob.status == "QUEUED")
            .order_by(TenderProcessingJob.created_at.asc())
            .limit(1)
        )
    ).first()
    if not cand:
        return None
    cand_id, cand_gen = cand[0], int(cand[1] or 0)
    new_gen = cand_gen + 1

    res = await db.execute(
        update(TenderProcessingJob)
        .where(
            TenderProcessingJob.id == cand_id,
            TenderProcessingJob.status == "QUEUED",
            TenderProcessingJob.ownership_generation == cand_gen,
        )
        .values(
            status="RUNNING",
            worker_id=worker_id,
            ownership_generation=new_gen,
            started_at=now,
            heartbeat_at=now,
            lease_expires_at=lease_until,
            current_stage="VALIDATING_DOCUMENT",
            progress_pct=5,
        )
    )
    if res.rowcount == 0:
        await db.rollback()
        return None

    doc_id = (
        await db.execute(
            select(TenderProcessingJob.tender_document_id).where(TenderProcessingJob.id == cand_id)
        )
    ).scalar_one()
    await db.execute(
        update(TenderDocument)
        .where(TenderDocument.id == doc_id)
        .values(processing_status="PROCESSING")
    )
    await db.commit()
    return cand_id, new_gen


async def claim_next_job(db: AsyncSession, worker_id: str) -> Optional[UUID]:
    """Atomically claim the oldest QUEUED job using FOR UPDATE SKIP LOCKED on PostgreSQL."""
    claimed = await claim_next_job_fenced(db, worker_id)
    return claimed[0] if claimed else None


async def _heartbeat_loop(
    job_id: UUID,
    worker_id: str,
    ownership_generation: int,
    stop_event: asyncio.Event,
    ownership_lost_event: Optional[asyncio.Event] = None,
) -> None:
    """Extend lease_expires_at only while worker_id and ownership_generation still match."""
    interval = max(1.0, float(settings.JOB_HEARTBEAT_SECONDS))
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass

        try:
            async with AsyncSessionLocal() as db:
                await set_worker_rls_context(db, is_super_admin=True)
                now = datetime.now(timezone.utc)
                res = await db.execute(
                    update(TenderProcessingJob)
                    .where(
                        TenderProcessingJob.id == job_id,
                        TenderProcessingJob.worker_id == worker_id,
                        TenderProcessingJob.ownership_generation == ownership_generation,
                        TenderProcessingJob.status == "RUNNING",
                    )
                    .values(
                        heartbeat_at=now,
                        lease_expires_at=now + timedelta(seconds=settings.JOB_LEASE_SECONDS),
                    )
                )
                await db.commit()
                if res.rowcount == 0:
                    logger.warning(
                        f"OWNERSHIP_LOST event=heartbeat_fenced job_id={job_id} "
                        f"worker_id={worker_id} generation={ownership_generation}"
                    )
                    if ownership_lost_event is not None:
                        ownership_lost_event.set()
                    stop_event.set()
                    break
        except Exception as exc:
            logger.warning(f"Heartbeat update failed for job {job_id}: {exc}")


async def _persist_pages_idempotently(
    db: AsyncSession,
    document_id: UUID,
    pages_data: List[Dict[str, Any]],
) -> None:
    """Upsert TenderDocumentPage rows idempotently without corrupting prior state on partial fail."""
    for p in pages_data:
        page_num = int(p["page_number"])
        method = str(p["extraction_method"])
        ext_status = _derive_page_extraction_status(method)
        existing = (
            await db.execute(
                select(TenderDocumentPage).where(
                    TenderDocumentPage.tender_document_id == document_id,
                    TenderDocumentPage.page_number == page_num,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.extracted_text = p.get("text") or ""
            existing.word_count = int(p.get("word_count") or 0)
            existing.extraction_method = method
            existing.ocr_confidence = p.get("ocr_confidence")
            existing.extraction_status = ext_status
        else:
            db.add(
                TenderDocumentPage(
                    tender_document_id=document_id,
                    page_number=page_num,
                    extracted_text=p.get("text") or "",
                    word_count=int(p.get("word_count") or 0),
                    extraction_method=method,
                    ocr_confidence=p.get("ocr_confidence"),
                    extraction_status=ext_status,
                )
            )


async def execute_claimed_job(
    job_id: UUID,
    worker_id: str,
    cpu_semaphore: Optional[asyncio.Semaphore] = None,
    ownership_generation: Optional[int] = None,
) -> str:
    """Execute a claimed job across short DB transactions with strict ownership fencing."""
    stop_heartbeat = asyncio.Event()
    ownership_lost_event = asyncio.Event()
    hb_task: Optional[asyncio.Task] = None
    org_id: Optional[UUID] = None
    doc_id: Optional[UUID] = None
    expected_gen: Optional[int] = ownership_generation

    try:
        # 1. Load job, document, and parent tender in a short transaction and verify ownership
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, is_super_admin=True)
            job = (
                await db.execute(
                    select(TenderProcessingJob).where(TenderProcessingJob.id == job_id)
                )
            ).scalar_one_or_none()
            if (
                not job
                or job.status != "RUNNING"
                or job.worker_id != worker_id
                or (ownership_generation is not None and int(job.ownership_generation) != ownership_generation)
            ):
                logger.warning(
                    f"OWNERSHIP_LOST event=precheck_fenced job_id={job_id} "
                    f"worker_id={worker_id} expected_gen={ownership_generation}"
                )
                return "OWNERSHIP_LOST"

            expected_gen = int(job.ownership_generation)

            doc = (
                await db.execute(
                    select(TenderDocument).where(TenderDocument.id == job.tender_document_id)
                )
            ).scalar_one_or_none()
            tender = (
                await db.execute(select(Tender).where(Tender.id == job.tender_id))
            ).scalar_one_or_none()

            if not doc or not tender:
                raise JobProcessingError(
                    "DOCUMENT_NOT_FOUND",
                    "Associated tender document record no longer exists.",
                    retryable=False,
                )

            org_id = tender.organization_id
            doc_id = doc.id
            job_type = job.job_type
            job_tender_id = job.tender_id
            job_extraction_version = int(job.extraction_version or 1)
            doc_status_now = doc.processing_status
            storage_path_str = doc.storage_path
            expected_size = int(doc.file_size_bytes)
            expected_sha256 = doc.sha256_hash

        hb_task = asyncio.create_task(
            _heartbeat_loop(job_id, worker_id, expected_gen, stop_heartbeat, ownership_lost_event)
        )

        if job_type == "REQUIREMENT_EXTRACTION":
            if doc_status_now != "READY":
                raise JobProcessingError(
                    "PAGE_EXTRACTION_INCOMPLETE",
                    "Document page extraction must complete before requirement extraction.",
                    retryable=False,
                )

            async with AsyncSessionLocal() as db:
                await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
                page_rows = (
                    await db.execute(
                        select(TenderDocumentPage)
                        .where(TenderDocumentPage.tender_document_id == doc_id)
                        .order_by(TenderDocumentPage.page_number.asc())
                    )
                ).scalars().all()
                pages_payload = [
                    {"page_number": p.page_number, "text": p.extracted_text}
                    for p in page_rows
                    if (p.extracted_text or "").strip()
                ]
                if not pages_payload:
                    raise JobProcessingError(
                        "NO_EXTRACTED_PAGES",
                        "No usable extracted page text is available for requirement extraction.",
                        retryable=False,
                    )

                res = await db.execute(
                    update(TenderProcessingJob)
                    .where(
                        TenderProcessingJob.id == job_id,
                        TenderProcessingJob.status == "RUNNING",
                        TenderProcessingJob.worker_id == worker_id,
                        TenderProcessingJob.ownership_generation == expected_gen,
                    )
                    .values(current_stage="EXTRACTING_REQUIREMENTS", progress_pct=25)
                )
                if res.rowcount == 0:
                    await db.rollback()
                    return "OWNERSHIP_LOST"
                await db.commit()

            sem = cpu_semaphore or asyncio.Semaphore(settings.JOB_MAX_CONCURRENT_WORKERS)
            async with sem:
                try:
                    extracted_reqs = await TenderRequirementExtractionService().extract_from_pages(pages_payload)
                except RequirementExtractionProviderError as rpe:
                    raise JobProcessingError(rpe.code, rpe.message, retryable=rpe.retryable) from rpe

            if ownership_lost_event.is_set():
                return "OWNERSHIP_LOST"

            async with AsyncSessionLocal() as db:
                await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
                now = datetime.now(timezone.utc)
                res = await db.execute(
                    update(TenderProcessingJob)
                    .where(
                        TenderProcessingJob.id == job_id,
                        TenderProcessingJob.status == "RUNNING",
                        TenderProcessingJob.worker_id == worker_id,
                        TenderProcessingJob.ownership_generation == expected_gen,
                    )
                    .values(
                        status="SUCCEEDED",
                        current_stage="FINALIZING",
                        progress_pct=100,
                        extracted_count=len(extracted_reqs),
                        completed_at=now,
                        lease_expires_at=None,
                        error_code=None,
                        error_message=None,
                    )
                )
                if res.rowcount == 0:
                    await db.rollback()
                    logger.warning(
                        f"OWNERSHIP_LOST event=req_finalize_fenced job_id={job_id} "
                        f"worker_id={worker_id} generation={expected_gen}"
                    )
                    return "OWNERSHIP_LOST"

                # Never overwrite CONFIRMED or REJECTED requirements
                await db.execute(
                    delete(TenderRequirement).where(
                        TenderRequirement.source_document_id == doc_id,
                        TenderRequirement.extraction_version == job_extraction_version,
                        TenderRequirement.review_status.in_(["DRAFT", "NEEDS_REVIEW"]),
                    )
                )
                for req in extracted_reqs:
                    db.add(
                        TenderRequirement(
                            tender_id=job_tender_id,
                            source_document_id=doc_id,
                            processing_job_id=job_id,
                            extraction_version=job_extraction_version,
                            **req,
                        )
                    )
                await db.commit()

            return "SUCCEEDED"

        # 2. Verify stored file & page cap outside any DB transaction
        resolved_path, total_pages = await asyncio.to_thread(
            _verify_file_and_page_count_sync,
            storage_path_str,
            expected_size,
            expected_sha256,
            settings.MAX_TENDER_PDF_PAGES,
        )

        if ownership_lost_event.is_set():
            logger.warning(
                f"OWNERSHIP_LOST event=pre_extract_fenced job_id={job_id} "
                f"worker_id={worker_id} generation={expected_gen}"
            )
            return "OWNERSHIP_LOST"

        # 3. Advance stage -> EXTRACTING_PAGES (fenced)
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
            res = await db.execute(
                update(TenderProcessingJob)
                .where(
                    TenderProcessingJob.id == job_id,
                    TenderProcessingJob.status == "RUNNING",
                    TenderProcessingJob.worker_id == worker_id,
                    TenderProcessingJob.ownership_generation == expected_gen,
                )
                .values(current_stage="EXTRACTING_PAGES", progress_pct=20)
            )
            if res.rowcount == 0:
                await db.rollback()
                logger.warning(
                    f"OWNERSHIP_LOST event=stage_extract_fenced job_id={job_id} "
                    f"worker_id={worker_id} generation={expected_gen}"
                )
                return "OWNERSHIP_LOST"
            await db.commit()

        # 4. Run PyMuPDF + OCR extraction in bounded thread pool (no DB transaction held)
        sem = cpu_semaphore or asyncio.Semaphore(settings.JOB_MAX_CONCURRENT_WORKERS)
        async with sem:
            pages_data = await asyncio.to_thread(extract_pages_from_pdf, str(resolved_path))

        if ownership_lost_event.is_set():
            logger.warning(
                f"OWNERSHIP_LOST event=post_extract_fenced job_id={job_id} "
                f"worker_id={worker_id} generation={expected_gen}"
            )
            return "OWNERSHIP_LOST"

        # 5. Advance stage -> PERSISTING_PAGES & upsert pages ONLY if ownership still matches
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
            res = await db.execute(
                update(TenderProcessingJob)
                .where(
                    TenderProcessingJob.id == job_id,
                    TenderProcessingJob.status == "RUNNING",
                    TenderProcessingJob.worker_id == worker_id,
                    TenderProcessingJob.ownership_generation == expected_gen,
                )
                .values(current_stage="PERSISTING_PAGES", progress_pct=70)
            )
            if res.rowcount == 0:
                await db.rollback()
                logger.warning(
                    f"OWNERSHIP_LOST event=page_persist_fenced job_id={job_id} "
                    f"worker_id={worker_id} generation={expected_gen}"
                )
                return "OWNERSHIP_LOST"
            await _persist_pages_idempotently(db, doc_id, pages_data)
            await db.commit()

        # 6. Finalize job + document status atomically ONLY if ownership still matches
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
            now = datetime.now(timezone.utc)
            res = await db.execute(
                update(TenderProcessingJob)
                .where(
                    TenderProcessingJob.id == job_id,
                    TenderProcessingJob.status == "RUNNING",
                    TenderProcessingJob.worker_id == worker_id,
                    TenderProcessingJob.ownership_generation == expected_gen,
                )
                .values(
                    status="SUCCEEDED",
                    current_stage="FINALIZING",
                    progress_pct=100,
                    completed_at=now,
                    lease_expires_at=None,
                    error_code=None,
                    error_message=None,
                )
            )
            if res.rowcount == 0:
                await db.rollback()
                logger.warning(
                    f"OWNERSHIP_LOST event=finalize_fenced job_id={job_id} "
                    f"worker_id={worker_id} generation={expected_gen}"
                )
                return "OWNERSHIP_LOST"

            await db.execute(
                update(TenderDocument)
                .where(TenderDocument.id == doc_id)
                .values(total_pages=total_pages, processing_status="READY")
            )
            await db.commit()

        return "SUCCEEDED"

    except asyncio.CancelledError:
        # Graceful shutdown: release lease ONLY if this worker + generation still owns it
        if expected_gen is not None:
            try:
                async with AsyncSessionLocal() as db:
                    await set_worker_rls_context(db, is_super_admin=True)
                    res = await db.execute(
                        update(TenderProcessingJob)
                        .where(
                            TenderProcessingJob.id == job_id,
                            TenderProcessingJob.status == "RUNNING",
                            TenderProcessingJob.worker_id == worker_id,
                            TenderProcessingJob.ownership_generation == expected_gen,
                        )
                        .values(
                            status="QUEUED",
                            current_stage="QUEUED",
                            worker_id=None,
                            lease_expires_at=None,
                            ownership_generation=expected_gen + 1,
                        )
                    )
                    if res.rowcount == 1 and doc_id and job_type == "PAGE_EXTRACTION":
                        await db.execute(
                            update(TenderDocument)
                            .where(TenderDocument.id == doc_id)
                            .values(processing_status="QUEUED")
                        )
                        await db.commit()
                    else:
                        await db.rollback()
                        logger.warning(
                            f"OWNERSHIP_LOST event=shutdown_release_fenced job_id={job_id} "
                            f"worker_id={worker_id} generation={expected_gen}"
                        )
            except Exception as exc:
                logger.warning(f"Failed graceful release for cancelled job {job_id}: {exc}")
        raise

    except JobProcessingError as jpe:
        return await _handle_job_failure(
            job_id,
            doc_id,
            jpe.code,
            jpe.message,
            retryable=jpe.retryable,
            worker_id=worker_id,
            ownership_generation=expected_gen,
        )

    except Exception as exc:
        logger.exception(f"Unexpected error processing job {job_id}: {exc}")
        return await _handle_job_failure(
            job_id,
            doc_id,
            "EXTRACTION_ERROR",
            "Document page extraction failed due to an internal processing error.",
            retryable=True,
            worker_id=worker_id,
            ownership_generation=expected_gen,
        )
    finally:
        stop_heartbeat.set()
        if hb_task is not None:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass


async def _handle_job_failure(
    job_id: UUID,
    doc_id: Optional[UUID],
    error_code: str,
    error_message: str,
    retryable: bool,
    worker_id: Optional[str] = None,
    ownership_generation: Optional[int] = None,
) -> str:
    """Transition a failed job ONLY if the caller still owns (RUNNING, worker_id, ownership_generation)."""
    async with AsyncSessionLocal() as db:
        await set_worker_rls_context(db, is_super_admin=True)
        is_pg = bool(db.bind and db.bind.dialect.name == "postgresql")
        conditions = [
            TenderProcessingJob.id == job_id,
            TenderProcessingJob.status == "RUNNING",
        ]
        if worker_id is not None:
            conditions.append(TenderProcessingJob.worker_id == worker_id)
        if ownership_generation is not None:
            conditions.append(TenderProcessingJob.ownership_generation == ownership_generation)

        stmt = select(TenderProcessingJob).where(*conditions)
        if is_pg:
            stmt = stmt.with_for_update()
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            logger.warning(
                f"OWNERSHIP_LOST event=failure_handler_fenced job_id={job_id} "
                f"worker_id={worker_id} generation={ownership_generation}"
            )
            return "OWNERSHIP_LOST"

        now = datetime.now(timezone.utc)
        can_retry = retryable and (error_code not in NON_RETRYABLE_ERROR_CODES) and (job.retry_count < job.max_retries)
        job.ownership_generation = (job.ownership_generation or 0) + 1

        if can_retry:
            job.retry_count += 1
            job.status = "QUEUED"
            job.current_stage = "QUEUED"
            job.worker_id = None
            job.lease_expires_at = None
            job.error_code = error_code
            job.error_message = error_message
            next_doc_status = "QUEUED"
            result_status = "RETRY_QUEUED"
        else:
            job.status = "FAILED"
            job.current_stage = "FAILED"
            job.completed_at = now
            job.lease_expires_at = None
            job.error_code = error_code
            job.error_message = error_message
            next_doc_status = "FAILED"
            result_status = "FAILED"

        target_doc_id = doc_id or job.tender_document_id
        # Preserve any previously persisted TenderDocumentPage rows!
        if job.job_type == "PAGE_EXTRACTION":
            await db.execute(
                update(TenderDocument)
                .where(TenderDocument.id == target_doc_id)
                .values(processing_status=next_doc_status)
            )
        await db.commit()
        return result_status


class TenderProcessingWorkerManager:
    """Application-managed PostgreSQL polling worker with bounded concurrency & graceful shutdown."""

    def __init__(self) -> None:
        self.worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._loop_task: Optional[asyncio.Task] = None
        self._active_tasks: set[asyncio.Task] = set()
        self._cpu_semaphore = asyncio.Semaphore(settings.JOB_MAX_CONCURRENT_WORKERS)

    def notify(self) -> None:
        """Wake the polling loop immediately when a new job is enqueued."""
        self._wake_event.set()

    async def start(self) -> None:
        self._stop_event.clear()
        try:
            async with AsyncSessionLocal() as db:
                recovered = await recover_expired_leases(db)
                if recovered:
                    logger.info(f"Recovered {recovered} expired tender processing job(s) on startup.")
        except Exception as exc:
            logger.warning(f"Startup lease recovery skipped: {exc}")

        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info(f"TenderProcessingWorkerManager started ({self.worker_id}).")

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        for t in list(self._active_tasks):
            t.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        logger.info(f"TenderProcessingWorkerManager stopped ({self.worker_id}).")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if len(self._active_tasks) < settings.JOB_MAX_CONCURRENT_WORKERS:
                    async with AsyncSessionLocal() as db:
                        await recover_expired_leases(db)
                        claimed = await claim_next_job_fenced(db, self.worker_id)

                    if claimed:
                        claimed_id, generation = claimed
                        task = asyncio.create_task(
                            execute_claimed_job(
                                claimed_id,
                                self.worker_id,
                                self._cpu_semaphore,
                                ownership_generation=generation,
                            )
                        )
                        self._active_tasks.add(task)
                        task.add_done_callback(self._active_tasks.discard)
                        continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Worker poll iteration error: {exc}")

            self._wake_event.clear()
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=float(settings.JOB_POLL_INTERVAL_SECONDS),
                )
            except asyncio.TimeoutError:
                pass


worker_manager = TenderProcessingWorkerManager()
