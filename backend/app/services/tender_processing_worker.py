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
from sqlalchemy import and_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tender import Tender, TenderDocument, TenderDocumentPage, TenderProcessingJob
from app.schemas.bidder import ExtractionMethod
from app.services.pdf_extractor import extract_pages_from_pdf

logger = logging.getLogger(__name__)

NON_RETRYABLE_ERROR_CODES = {
    "FILE_NOT_FOUND",
    "STORAGE_PATH_INVALID",
    "INTEGRITY_SIZE_MISMATCH",
    "INTEGRITY_HASH_MISMATCH",
    "PAGE_LIMIT_EXCEEDED",
    "INVALID_PDF",
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
    """Reconcile RUNNING jobs with expired leases (crash/restart recovery)."""
    await set_worker_rls_context(db, is_super_admin=True)
    now = datetime.now(timezone.utc)
    stmt = select(TenderProcessingJob).where(
        TenderProcessingJob.status == "RUNNING",
        TenderProcessingJob.lease_expires_at.is_not(None),
        TenderProcessingJob.lease_expires_at < now,
    )
    expired_jobs = (await db.execute(stmt)).scalars().all()
    recovered = 0

    for job in expired_jobs:
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


async def claim_next_job(db: AsyncSession, worker_id: str) -> Optional[UUID]:
    """Atomically claim the oldest QUEUED job using FOR UPDATE SKIP LOCKED on PostgreSQL."""
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

        job.status = "RUNNING"
        job.worker_id = worker_id
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.lease_expires_at = lease_until
        job.current_stage = "VALIDATING_DOCUMENT"
        job.progress_pct = max(job.progress_pct, 5)

        await db.execute(
            update(TenderDocument)
            .where(TenderDocument.id == job.tender_document_id)
            .values(processing_status="PROCESSING")
        )
        await db.commit()
        return job.id

    # SQLite fallback: conditional atomic UPDATE
    cand_id = (
        await db.execute(
            select(TenderProcessingJob.id)
            .where(TenderProcessingJob.status == "QUEUED")
            .order_by(TenderProcessingJob.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not cand_id:
        return None

    res = await db.execute(
        update(TenderProcessingJob)
        .where(TenderProcessingJob.id == cand_id, TenderProcessingJob.status == "QUEUED")
        .values(
            status="RUNNING",
            worker_id=worker_id,
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
    return cand_id


async def _heartbeat_loop(
    job_id: UUID,
    worker_id: str,
    stop_event: asyncio.Event,
) -> None:
    """Extend lease_expires_at periodically while long-running extraction executes."""
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
                await db.execute(
                    update(TenderProcessingJob)
                    .where(
                        TenderProcessingJob.id == job_id,
                        TenderProcessingJob.worker_id == worker_id,
                        TenderProcessingJob.status == "RUNNING",
                    )
                    .values(
                        heartbeat_at=now,
                        lease_expires_at=now + timedelta(seconds=settings.JOB_LEASE_SECONDS),
                    )
                )
                await db.commit()
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
) -> str:
    """Execute a claimed job across short DB transactions with bounded CPU execution."""
    stop_heartbeat = asyncio.Event()
    hb_task = asyncio.create_task(_heartbeat_loop(job_id, worker_id, stop_heartbeat))
    org_id: Optional[UUID] = None
    doc_id: Optional[UUID] = None

    try:
        # 1. Load job, document, and parent tender in a short transaction
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, is_super_admin=True)
            job = (
                await db.execute(
                    select(TenderProcessingJob).where(TenderProcessingJob.id == job_id)
                )
            ).scalar_one_or_none()
            if not job or job.status != "RUNNING" or job.worker_id != worker_id:
                return "SKIPPED"

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
            storage_path_str = doc.storage_path
            expected_size = int(doc.file_size_bytes)
            expected_sha256 = doc.sha256_hash

        # 2. Verify stored file & page cap outside any DB transaction
        resolved_path, total_pages = await asyncio.to_thread(
            _verify_file_and_page_count_sync,
            storage_path_str,
            expected_size,
            expected_sha256,
            settings.MAX_TENDER_PDF_PAGES,
        )

        # 3. Advance stage -> EXTRACTING_PAGES
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
            await db.execute(
                update(TenderProcessingJob)
                .where(TenderProcessingJob.id == job_id, TenderProcessingJob.worker_id == worker_id)
                .values(current_stage="EXTRACTING_PAGES", progress_pct=20)
            )
            await db.commit()

        # 4. Run PyMuPDF + OCR extraction in bounded thread pool
        sem = cpu_semaphore or asyncio.Semaphore(settings.JOB_MAX_CONCURRENT_WORKERS)
        async with sem:
            pages_data = await asyncio.to_thread(extract_pages_from_pdf, str(resolved_path))

        # 5. Advance stage -> PERSISTING_PAGES
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
            await db.execute(
                update(TenderProcessingJob)
                .where(TenderProcessingJob.id == job_id, TenderProcessingJob.worker_id == worker_id)
                .values(current_stage="PERSISTING_PAGES", progress_pct=70)
            )
            await _persist_pages_idempotently(db, doc_id, pages_data)
            await db.commit()

        # 6. Finalize job + document status atomically
        async with AsyncSessionLocal() as db:
            await set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)
            now = datetime.now(timezone.utc)
            await db.execute(
                update(TenderDocument)
                .where(TenderDocument.id == doc_id)
                .values(total_pages=total_pages, processing_status="READY")
            )
            await db.execute(
                update(TenderProcessingJob)
                .where(TenderProcessingJob.id == job_id, TenderProcessingJob.worker_id == worker_id)
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
            await db.commit()

        return "SUCCEEDED"

    except asyncio.CancelledError:
        # Graceful shutdown: release lease back to QUEUED so another startup/worker can resume
        try:
            async with AsyncSessionLocal() as db:
                await set_worker_rls_context(db, is_super_admin=True)
                await db.execute(
                    update(TenderProcessingJob)
                    .where(TenderProcessingJob.id == job_id, TenderProcessingJob.status == "RUNNING")
                    .values(
                        status="QUEUED",
                        current_stage="QUEUED",
                        worker_id=None,
                        lease_expires_at=None,
                    )
                )
                if doc_id:
                    await db.execute(
                        update(TenderDocument)
                        .where(TenderDocument.id == doc_id)
                        .values(processing_status="QUEUED")
                    )
                await db.commit()
        except Exception as exc:
            logger.warning(f"Failed graceful release for cancelled job {job_id}: {exc}")
        raise

    except JobProcessingError as jpe:
        return await _handle_job_failure(job_id, doc_id, jpe.code, jpe.message, retryable=jpe.retryable)

    except Exception as exc:
        logger.exception(f"Unexpected error processing job {job_id}: {exc}")
        return await _handle_job_failure(
            job_id,
            doc_id,
            "EXTRACTION_ERROR",
            "Document page extraction failed due to an internal processing error.",
            retryable=True,
        )
    finally:
        stop_heartbeat.set()
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
) -> str:
    """Transition a failed job to RETRY_WAIT/QUEUED or terminal FAILED without wiping prior pages."""
    async with AsyncSessionLocal() as db:
        await set_worker_rls_context(db, is_super_admin=True)
        job = (
            await db.execute(
                select(TenderProcessingJob).where(TenderProcessingJob.id == job_id)
            )
        ).scalar_one_or_none()
        if not job:
            return "FAILED"

        now = datetime.now(timezone.utc)
        can_retry = retryable and (error_code not in NON_RETRYABLE_ERROR_CODES) and (job.retry_count < job.max_retries)

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
                        claimed_id = await claim_next_job(db, self.worker_id)

                    if claimed_id:
                        task = asyncio.create_task(
                            execute_claimed_job(claimed_id, self.worker_id, self._cpu_semaphore)
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
