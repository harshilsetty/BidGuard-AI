import asyncio
import os
import uuid
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, or_
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.api.deps import (
    require_permission,
    get_authorized_tender,
    validate_tender_tenant_access,
)
from app.models.audit import AuditLog
from app.models.user import User
from app.models.tender import (
    Tender,
    TenderDocument,
    TenderDocumentPage,
    TenderProcessingJob,
    TenderRequirement,
    TenderRequirementSource,
    TenderRequirementConflict,
    TenderRequirementEvidence,
    ReviewDecision,
)
from app.models.clause import TenderClause
from app.schemas.tender import (
    TenderResponse,
    TenderDetailResponse,
    TenderDocumentResponse,
    TenderDocumentPageResponse,
    TenderDocumentPagesListResponse,
    TenderProcessingJobResponse,
    ExtractionResultResponse,
    TenderRequirementResponse,
    TenderRequirementsListResponse,
    TenderRequirementSourceResponse,
    TenderRequirementProvenanceResponse,
    TenderRequirementConflictResponse,
    TenderRequirementConflictDetailResponse,
    TenderRequirementConflictsListResponse,
    ConflictDetectionRunResponse,
    TenderRequirementEvidenceResponse,
    TenderRequirementEvidenceListResponse,
    ReviewDecisionRequest,
    ReviewAssignRequest,
    ReviewDecisionResponse,
    ReviewDecisionMutationResponse,
    ReviewQueueItemResponse,
    ReviewQueueListResponse,
    ReviewDecisionHistoryListResponse,
    ReviewWorkloadSummaryResponse,
)
from app.services.requirement_provenance_service import TenderRequirementProvenanceService
from app.services.requirement_conflict_service import TenderRequirementConflictService
from app.services.requirement_evidence_service import TenderRequirementEvidenceService
from app.services.review_service import TenderReviewService
from app.schemas.clause import (
    ClauseResponse,
    ClauseCreateRequest,
    ClauseUpdateRequest,
)
from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import (
    extract_clauses_from_tender_pages,
    CATEGORY_PREFIX_MAP,
)
from app.services.tender_upload_service import (
    cleanup_stored_file,
    resolve_tenant_storage_path,
    sanitize_pdf_filename,
    stream_validate_and_store_pdf,
    validate_document_role,
)
from app.services.tender_processing_worker import ACTIVE_JOB_STATUSES, worker_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenders", tags=["Tenders & Requirement Extraction"])


@router.post("/upload", response_model=TenderResponse, status_code=status.HTTP_201_CREATED)
async def upload_tender_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    gem_tender_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:create")),
):
    """Upload a primary GeM Tender PDF with bounded streaming, SHA-256, and structural validation."""
    safe_filename = sanitize_pdf_filename(file.filename)
    tender_id = uuid.uuid4()
    document_id = uuid.uuid4()
    dest_path = resolve_tenant_storage_path(
        organization_id=current_user.organization_id,
        tender_id=tender_id,
        document_id=document_id,
    )

    file_size_bytes, sha256_hash, total_pages = await stream_validate_and_store_pdf(
        upload_file=file,
        dest_path=dest_path,
    )

    tender = Tender(
        id=tender_id,
        organization_id=current_user.organization_id,
        title=title.strip(),
        gem_tender_id=gem_tender_id.strip() if gem_tender_id else None,
        file_name=safe_filename,
        file_path=str(dest_path),
        total_pages=total_pages,
        extraction_status="UPLOADED",
        next_clause_seq={
            "TECH": 1,
            "FIN": 1,
            "STAT": 1,
            "EXP": 1,
            "DEL": 1,
            "GEN": 1,
        },
    )
    primary_doc = TenderDocument(
        id=document_id,
        tender_id=tender_id,
        document_role="PRIMARY_NIT",
        original_filename=safe_filename,
        storage_path=str(dest_path),
        file_size_bytes=file_size_bytes,
        sha256_hash=sha256_hash,
        total_pages=total_pages,
        processing_status="UPLOADED",
    )

    try:
        db.add(tender)
        db.add(primary_doc)
        db.add(
            AuditLog(
                organization_id=current_user.organization_id,
                user_id=current_user.id,
                action="TENDER_CREATED_WITH_DOCUMENT",
                target_type="Tender",
                target_id=str(tender_id),
                diff_json={"document_id": str(document_id), "sha256": sha256_hash, "bytes": file_size_bytes},
            )
        )
        await db.commit()
        await db.refresh(tender)
    except Exception:
        await db.rollback()
        cleanup_stored_file(dest_path)
        raise

    return TenderResponse(
        id=tender.id,
        title=tender.title,
        gem_tender_id=tender.gem_tender_id,
        file_name=tender.file_name,
        total_pages=tender.total_pages,
        extraction_status=tender.extraction_status,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        clause_count=0,
    )


@router.post(
    "/{tender_id}/documents",
    response_model=TenderDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_tender_document(
    tender_id: UUID,
    file: UploadFile = File(...),
    document_role: str = Form("ANNEXURE"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Upload an additional PDF document (NIT, Technical Spec, BoQ, Corrigendum, Annexure) to a tender."""
    tender = await get_authorized_tender(tender_id, current_user, db)
    role_clean = validate_document_role(document_role)
    safe_filename = sanitize_pdf_filename(file.filename)

    document_id = uuid.uuid4()
    dest_path = resolve_tenant_storage_path(
        organization_id=tender.organization_id or current_user.organization_id,
        tender_id=tender.id,
        document_id=document_id,
    )

    file_size_bytes, sha256_hash, total_pages = await stream_validate_and_store_pdf(
        upload_file=file,
        dest_path=dest_path,
    )

    # Check duplicate SHA-256 within the same tender
    dup_stmt = select(TenderDocument).where(
        TenderDocument.tender_id == tender.id,
        TenderDocument.sha256_hash == sha256_hash,
    )
    if (await db.execute(dup_stmt)).scalar_one_or_none():
        cleanup_stored_file(dest_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate document: an identical PDF (matching SHA-256) is already attached to this tender.",
        )

    doc_record = TenderDocument(
        id=document_id,
        tender_id=tender.id,
        document_role=role_clean,
        original_filename=safe_filename,
        storage_path=str(dest_path),
        file_size_bytes=file_size_bytes,
        sha256_hash=sha256_hash,
        total_pages=total_pages,
        processing_status="UPLOADED",
    )

    try:
        db.add(doc_record)
        db.add(
            AuditLog(
                organization_id=current_user.organization_id,
                user_id=current_user.id,
                action="TENDER_DOCUMENT_UPLOADED",
                target_type="TenderDocument",
                target_id=str(document_id),
                diff_json={
                    "tender_id": str(tender.id),
                    "role": role_clean,
                    "filename": safe_filename,
                    "sha256": sha256_hash,
                },
            )
        )
        await db.commit()
        await db.refresh(doc_record)
    except Exception:
        await db.rollback()
        cleanup_stored_file(dest_path)
        raise

    return TenderDocumentResponse.model_validate(doc_record)


@router.get("/{tender_id}/documents", response_model=List[TenderDocumentResponse])
async def list_tender_documents(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """List tenant-scoped document metadata attached to a tender, including latest job state."""
    await get_authorized_tender(tender_id, current_user, db)
    stmt = (
        select(TenderDocument)
        .where(TenderDocument.tender_id == tender_id)
        .order_by(TenderDocument.created_at.asc())
    )
    docs = (await db.execute(stmt)).scalars().all()

    jobs_stmt = (
        select(TenderProcessingJob)
        .where(TenderProcessingJob.tender_id == tender_id)
        .order_by(TenderProcessingJob.created_at.desc())
    )
    jobs = (await db.execute(jobs_stmt)).scalars().all()
    latest_by_doc = {}
    for j in jobs:
        if j.tender_document_id not in latest_by_doc:
            latest_by_doc[j.tender_document_id] = j

    output = []
    for d in docs:
        resp = TenderDocumentResponse.model_validate(d)
        if d.id in latest_by_doc:
            resp.latest_job = TenderProcessingJobResponse.model_validate(latest_by_doc[d.id])
        output.append(resp)
    return output


@router.post(
    "/{tender_id}/documents/{document_id}/process",
    response_model=TenderProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_document_processing(
    tender_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Enqueue persistent asynchronous PDF/OCR page extraction (idempotent for active jobs)."""
    await get_authorized_tender(tender_id, current_user, db)

    doc_record = (
        await db.execute(
            select(TenderDocument).where(
                TenderDocument.id == document_id,
                TenderDocument.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not doc_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender document not found.",
        )

    idempotency_key = f"PAGE_EXTRACTION:{document_id}"
    active_job = (
        await db.execute(
            select(TenderProcessingJob)
            .where(
                TenderProcessingJob.tender_document_id == document_id,
                TenderProcessingJob.idempotency_key == idempotency_key,
                TenderProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(TenderProcessingJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if active_job:
        return TenderProcessingJobResponse.model_validate(active_job)

    job = TenderProcessingJob(
        tender_id=tender_id,
        tender_document_id=document_id,
        job_type="PAGE_EXTRACTION",
        status="QUEUED",
        idempotency_key=idempotency_key,
        retry_count=0,
        max_retries=settings.JOB_DEFAULT_MAX_RETRIES,
        progress_pct=0,
        current_stage="QUEUED",
    )
    doc_record.processing_status = "QUEUED"
    db.add(job)
    db.add(
        AuditLog(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="TENDER_DOCUMENT_PROCESSING_ENQUEUED",
            target_type="TenderProcessingJob",
            target_id=str(document_id),
            diff_json={"tender_id": str(tender_id), "job_type": "PAGE_EXTRACTION"},
        )
    )
    await db.commit()
    await db.refresh(job)

    worker_manager.notify()
    return TenderProcessingJobResponse.model_validate(job)


@router.get(
    "/{tender_id}/jobs/{job_id}",
    response_model=TenderProcessingJobResponse,
)
async def get_tender_job_status(
    tender_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Retrieve persistent processing job status, stage, progress, and sanitized errors."""
    await get_authorized_tender(tender_id, current_user, db)
    job = (
        await db.execute(
            select(TenderProcessingJob).where(
                TenderProcessingJob.id == job_id,
                TenderProcessingJob.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found.")
    return TenderProcessingJobResponse.model_validate(job)


@router.post(
    "/{tender_id}/jobs/{job_id}/retry",
    response_model=TenderProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_tender_job(
    tender_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Retry an eligible FAILED processing job while preserving prior error metadata in audit logs."""
    await get_authorized_tender(tender_id, current_user, db)
    job = (
        await db.execute(
            select(TenderProcessingJob).where(
                TenderProcessingJob.id == job_id,
                TenderProcessingJob.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found.")

    if job.status != "FAILED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only FAILED jobs can be retried (current status: {job.status}).",
        )

    if job.retry_count >= job.max_retries:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Maximum retry count has been exhausted for this job.",
        )

    existing_active = (
        await db.execute(
            select(TenderProcessingJob).where(
                TenderProcessingJob.tender_document_id == job.tender_document_id,
                TenderProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
                TenderProcessingJob.id != job.id,
            )
        )
    ).scalar_one_or_none()
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another active processing job is already running for this document.",
        )

    prev_error = {"error_code": job.error_code, "error_message": job.error_message}
    job.retry_count += 1
    job.status = "QUEUED"
    job.current_stage = "QUEUED"
    job.progress_pct = 0
    job.worker_id = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    job.completed_at = None
    job.error_code = None
    job.error_message = None

    doc_record = (
        await db.execute(
            select(TenderDocument).where(TenderDocument.id == job.tender_document_id)
        )
    ).scalar_one_or_none()
    if doc_record:
        doc_record.processing_status = "QUEUED"

    db.add(
        AuditLog(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="TENDER_PROCESSING_JOB_RETRIED",
            target_type="TenderProcessingJob",
            target_id=str(job.id),
            diff_json={"retry_count": job.retry_count, "previous_error": prev_error},
        )
    )
    await db.commit()
    await db.refresh(job)

    worker_manager.notify()
    return TenderProcessingJobResponse.model_validate(job)


@router.get(
    "/{tender_id}/documents/{document_id}/pages",
    response_model=TenderDocumentPagesListResponse,
)
async def list_tender_document_pages(
    tender_id: UUID,
    document_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Retrieve paginated persisted page-level extraction results for a tender document."""
    await get_authorized_tender(tender_id, current_user, db)
    doc_record = (
        await db.execute(
            select(TenderDocument).where(
                TenderDocument.id == document_id,
                TenderDocument.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not doc_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender document not found.")

    total = (
        await db.execute(
            select(func.count(TenderDocumentPage.id)).where(
                TenderDocumentPage.tender_document_id == document_id
            )
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(TenderDocumentPage)
            .where(TenderDocumentPage.tender_document_id == document_id)
            .order_by(TenderDocumentPage.page_number.asc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return TenderDocumentPagesListResponse(
        tender_id=tender_id,
        tender_document_id=document_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[TenderDocumentPageResponse.model_validate(r) for r in rows],
    )


@router.get("/{tender_id}/documents/{document_id}", response_model=TenderDocumentResponse)
async def get_tender_document_metadata(
    tender_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Retrieve metadata for a specific document belonging to an authorized tender."""
    await get_authorized_tender(tender_id, current_user, db)
    stmt = select(TenderDocument).where(
        TenderDocument.id == document_id,
        TenderDocument.tender_id == tender_id,
    )
    doc_record = (await db.execute(stmt)).scalar_one_or_none()
    if not doc_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender document not found.",
        )
    return TenderDocumentResponse.model_validate(doc_record)


@router.post(
    "/{tender_id}/documents/{document_id}/extract-requirements",
    response_model=TenderProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_requirement_extraction(
    tender_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Enqueue an asynchronous TenderLens requirement-extraction job for a processed document."""
    await get_authorized_tender(tender_id, current_user, db)
    doc_record = (
        await db.execute(
            select(TenderDocument).where(
                TenderDocument.id == document_id,
                TenderDocument.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not doc_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender document not found.")

    if doc_record.processing_status != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document page extraction must complete (READY) before requirement extraction.",
        )

    page_count = (
        await db.execute(
            select(func.count(TenderDocumentPage.id)).where(
                TenderDocumentPage.tender_document_id == document_id
            )
        )
    ).scalar() or 0
    if page_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No extracted pages are available for requirement extraction.",
        )

    existing_active = (
        await db.execute(
            select(TenderProcessingJob)
            .where(
                TenderProcessingJob.tender_document_id == document_id,
                TenderProcessingJob.job_type == "REQUIREMENT_EXTRACTION",
                TenderProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(TenderProcessingJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_active:
        worker_manager.notify()
        return TenderProcessingJobResponse.model_validate(existing_active)

    max_ver = (
        await db.execute(
            select(func.max(TenderProcessingJob.extraction_version)).where(
                TenderProcessingJob.tender_document_id == document_id,
                TenderProcessingJob.job_type == "REQUIREMENT_EXTRACTION",
            )
        )
    ).scalar()
    next_version = int(max_ver or 0) + 1
    idem_key = f"REQUIREMENT_EXTRACTION:{document_id}:v{next_version}"

    job = TenderProcessingJob(
        tender_id=tender_id,
        tender_document_id=document_id,
        job_type="REQUIREMENT_EXTRACTION",
        status="QUEUED",
        idempotency_key=idem_key,
        extraction_version=next_version,
        extracted_count=0,
        retry_count=0,
        max_retries=settings.JOB_DEFAULT_MAX_RETRIES,
        progress_pct=0,
        current_stage="QUEUED",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    worker_manager.notify()
    return TenderProcessingJobResponse.model_validate(job)


@router.get("/{tender_id}/requirement-jobs/{job_id}", response_model=TenderProcessingJobResponse)
async def get_requirement_extraction_job_status(
    tender_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Fetch status, progress, extracted_count, and sanitized error state for a requirement-extraction job."""
    await get_authorized_tender(tender_id, current_user, db)
    job = (
        await db.execute(
            select(TenderProcessingJob).where(
                TenderProcessingJob.id == job_id,
                TenderProcessingJob.tender_id == tender_id,
                TenderProcessingJob.job_type == "REQUIREMENT_EXTRACTION",
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement extraction job not found.")
    return TenderProcessingJobResponse.model_validate(job)


@router.get("/{tender_id}/requirements", response_model=TenderRequirementsListResponse)
async def list_tender_requirements(
    tender_id: UUID,
    primary_category: Optional[str] = Query(None),
    mandatory_status: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    source_document_id: Optional[UUID] = Query(None),
    extraction_version: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """List extracted TenderLens requirements with pagination and taxonomy/review filters."""
    await get_authorized_tender(tender_id, current_user, db)
    conditions = [TenderRequirement.tender_id == tender_id]
    if primary_category:
        conditions.append(TenderRequirement.primary_category == primary_category.strip().upper())
    if mandatory_status:
        conditions.append(TenderRequirement.mandatory_status == mandatory_status.strip().upper())
    if review_status:
        conditions.append(TenderRequirement.review_status == review_status.strip().upper())
    if source_document_id:
        conditions.append(TenderRequirement.source_document_id == source_document_id)
    if extraction_version is not None:
        conditions.append(TenderRequirement.extraction_version == extraction_version)

    total = (
        await db.execute(select(func.count(TenderRequirement.id)).where(*conditions))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(TenderRequirement)
            .where(*conditions)
            .order_by(
                TenderRequirement.extraction_version.desc(),
                TenderRequirement.source_page_number.asc(),
                TenderRequirement.requirement_code.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return TenderRequirementsListResponse(
        tender_id=tender_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[TenderRequirementResponse.model_validate(r) for r in rows],
    )


@router.get("/{tender_id}/requirements/{requirement_id}", response_model=TenderRequirementResponse)
async def get_tender_requirement_detail(
    tender_id: UUID,
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Retrieve full structured detail and source grounding for a single requirement."""
    await get_authorized_tender(tender_id, current_user, db)
    row = (
        await db.execute(
            select(TenderRequirement).where(
                TenderRequirement.id == requirement_id,
                TenderRequirement.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender requirement not found.")
    return TenderRequirementResponse.model_validate(row)


@router.post("/{tender_id}/extract", response_model=ExtractionResultResponse)
async def extract_tender_clauses(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Run AI clause extraction across 3-page sliding windows using NVIDIA NIM GPT-OSS 20B."""
    tender = await get_authorized_tender(tender_id, current_user, db)

    if not tender.file_path or not os.path.exists(tender.file_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tender PDF file not found on disk")

    # Update status to EXTRACTING
    tender.extraction_status = "EXTRACTING"
    await db.commit()

    try:
        with open(tender.file_path, "rb") as f:
            pdf_bytes = f.read()

        pages_data = await asyncio.to_thread(extract_pages_from_pdf, pdf_bytes)

        # Run extraction using sliding windows + NVIDIA NIM
        current_seq = tender.next_clause_seq or {}
        extracted_clauses, updated_seq = await extract_clauses_from_tender_pages(pages_data, current_seq)

        # Delete any prior unconfirmed clauses if re-extracting
        del_stmt = delete(TenderClause).where(
            TenderClause.tender_id == tender_id,
            TenderClause.is_confirmed == False
        )
        await db.execute(del_stmt)

        # Insert new clauses
        created_models = []
        for c in extracted_clauses:
            clause_obj = TenderClause(
                tender_id=tender.id,
                clause_code=c["clause_code"],
                category=c["category"],
                title=c["title"],
                description=c["description"],
                is_mandatory=c["is_mandatory"],
                rule_config=c["rule_config"],
                source_text=c["source_text"],
                page_number=c["page_number"],
                is_confirmed=False
            )
            db.add(clause_obj)
            created_models.append(clause_obj)

        tender.next_clause_seq = updated_seq
        tender.extraction_status = "REVIEW"
        await db.commit()

        # Reload with clauses
        query = select(TenderClause).where(TenderClause.tender_id == tender_id).order_by(TenderClause.clause_code)
        clauses_result = await db.execute(query)
        persisted_clauses = clauses_result.scalars().all()

        return ExtractionResultResponse(
            tender_id=tender.id,
            extraction_status=tender.extraction_status,
            total_pages=tender.total_pages,
            extracted_count=len(persisted_clauses),
            clauses=[ClauseResponse.model_validate(c) for c in persisted_clauses]
        )

    except Exception as e:
        logger.error(f"Clause extraction failed for tender {tender_id}: {e}")
        tender.extraction_status = "FAILED"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clause extraction failed: {str(e)}"
        )


@router.get("", response_model=List[TenderResponse])
async def list_tenders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """List all tenders with status and clause counts, strictly scoped to user's organization."""
    stmt = (
        select(
            Tender,
            func.count(TenderClause.id).label("clause_count")
        )
        .outerjoin(TenderClause, Tender.id == TenderClause.tender_id)
    )
    if "SUPER_ADMIN" not in getattr(current_user, "live_roles", []):
        stmt = stmt.where(Tender.organization_id == current_user.organization_id)
    stmt = stmt.group_by(Tender.id).order_by(Tender.created_at.desc())
    result = await db.execute(stmt)
    rows = result.all()

    output = []
    for tender, count in rows:
        resp = TenderResponse(
            id=tender.id,
            title=tender.title,
            gem_tender_id=tender.gem_tender_id,
            file_name=tender.file_name,
            total_pages=tender.total_pages,
            extraction_status=tender.extraction_status,
            created_at=tender.created_at,
            updated_at=tender.updated_at,
            clause_count=count
        )
        output.append(resp)
    return output


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender_detail(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Get tender details and all associated clauses."""
    stmt = (
        select(Tender)
        .options(selectinload(Tender.clauses), selectinload(Tender.documents))
        .where(Tender.id == tender_id)
    )
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()

    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    validate_tender_tenant_access(tender, current_user)

    return TenderDetailResponse(
        id=tender.id,
        title=tender.title,
        gem_tender_id=tender.gem_tender_id,
        file_name=tender.file_name,
        total_pages=tender.total_pages,
        extraction_status=tender.extraction_status,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        clauses=[ClauseResponse.model_validate(c) for c in sorted(tender.clauses, key=lambda x: x.clause_code)],
        documents=[TenderDocumentResponse.model_validate(d) for d in tender.documents],
    )


@router.get("/{tender_id}/clauses", response_model=List[ClauseResponse])
async def get_tender_clauses(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Fetch all clauses for human review."""
    await get_authorized_tender(tender_id, current_user, db)

    stmt = (
        select(TenderClause)
        .where(TenderClause.tender_id == tender_id)
        .order_by(TenderClause.clause_code)
    )
    result = await db.execute(stmt)
    clauses = result.scalars().all()
    return [ClauseResponse.model_validate(c) for c in clauses]


@router.post("/{tender_id}/clauses", response_model=ClauseResponse, status_code=status.HTTP_201_CREATED)
async def add_manual_clause(
    tender_id: UUID,
    req: ClauseCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Manually add a custom clause with a unique, non-recycled code."""
    tender = await get_authorized_tender(tender_id, current_user, db)

    # Generate next code without recycling
    prefix = CATEGORY_PREFIX_MAP.get(req.category.upper(), "GEN")
    tracker = dict(tender.next_clause_seq or {})
    seq = tracker.get(prefix, 1)
    code = f"{prefix}-{seq:02d}"
    tracker[prefix] = seq + 1
    tender.next_clause_seq = tracker

    new_clause = TenderClause(
        tender_id=tender_id,
        clause_code=code,
        category=req.category.upper(),
        title=req.title.strip(),
        description=req.description.strip(),
        is_mandatory=req.is_mandatory,
        rule_config=req.rule_config,
        source_text=req.source_text.strip(),
        page_number=req.page_number,
        is_confirmed=False
    )
    db.add(new_clause)
    await db.commit()
    await db.refresh(new_clause)
    return ClauseResponse.model_validate(new_clause)


@router.put("/{tender_id}/clauses/{clause_id}", response_model=ClauseResponse)
async def update_clause(
    tender_id: UUID,
    clause_id: UUID,
    req: ClauseUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Update clause fields during human review."""
    await get_authorized_tender(tender_id, current_user, db)

    stmt = select(TenderClause).where(
        TenderClause.id == clause_id,
        TenderClause.tender_id == tender_id
    )
    result = await db.execute(stmt)
    clause = result.scalar_one_or_none()

    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")

    if req.category is not None:
        clause.category = req.category.upper()
    if req.title is not None:
        clause.title = req.title.strip()
    if req.description is not None:
        clause.description = req.description.strip()
    if req.is_mandatory is not None:
        clause.is_mandatory = req.is_mandatory
    if req.rule_config is not None:
        clause.rule_config = req.rule_config
    if req.source_text is not None:
        clause.source_text = req.source_text.strip()
    if req.page_number is not None:
        clause.page_number = req.page_number
    if req.is_confirmed is not None:
        clause.is_confirmed = req.is_confirmed

    await db.commit()
    await db.refresh(clause)
    return ClauseResponse.model_validate(clause)


@router.delete("/{tender_id}/clauses/{clause_id}", status_code=status.HTTP_200_OK)
async def delete_clause(
    tender_id: UUID,
    clause_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Delete a clause from review. The sequence number is NOT recycled."""
    await get_authorized_tender(tender_id, current_user, db)

    stmt = select(TenderClause).where(
        TenderClause.id == clause_id,
        TenderClause.tender_id == tender_id
    )
    result = await db.execute(stmt)
    clause = result.scalar_one_or_none()

    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")

    await db.delete(clause)
    await db.commit()
    return {"deleted": True, "clause_id": str(clause_id)}


@router.post("/{tender_id}/confirm", response_model=TenderDetailResponse)
async def confirm_tender_clauses(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Human Confirmation: Lock all clauses and mark tender status as READY."""
    stmt = (
        select(Tender)
        .options(selectinload(Tender.clauses))
        .where(Tender.id == tender_id)
    )
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()

    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    validate_tender_tenant_access(tender, current_user)

    if not tender.clauses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot confirm tender with 0 clauses. Extract or add clauses first."
        )

    # Lock all clauses
    for c in tender.clauses:
        c.is_confirmed = True

    tender.extraction_status = "READY"
    await db.commit()
    await db.refresh(tender)

    return TenderDetailResponse(
        id=tender.id,
        title=tender.title,
        gem_tender_id=tender.gem_tender_id,
        file_name=tender.file_name,
        total_pages=tender.total_pages,
        extraction_status=tender.extraction_status,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        clauses=[ClauseResponse.model_validate(c) for c in sorted(tender.clauses, key=lambda x: x.clause_code)]
    )


# ==============================================================================
# Phase 2.0D: Requirement Provenance, Conflict Detection & Evidence Mapping
# ==============================================================================


@router.get(
    "/{tender_id}/requirements/{requirement_id}/provenance",
    response_model=TenderRequirementProvenanceResponse,
)
async def get_requirement_provenance(
    tender_id: UUID,
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Verify and return full source provenance and supporting passages for a requirement."""
    await get_authorized_tender(tender_id, current_user, db)
    svc = TenderRequirementProvenanceService()
    try:
        res = await svc.verify_and_get_provenance(db, tender_id, requirement_id, persist_status=True)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender requirement not found.")
    await db.commit()

    req: TenderRequirement = res["requirement"]
    doc: Optional[TenderDocument] = res["source_document"]
    return TenderRequirementProvenanceResponse(
        requirement_id=req.id,
        tender_id=req.tender_id,
        source_document_id=req.source_document_id,
        source_document_name=doc.original_filename if doc else None,
        source_document_role=doc.document_role if doc else None,
        source_page_number=req.source_page_number,
        source_page_range=req.source_page_range,
        source_section=req.source_section,
        source_text=req.source_text,
        normalized_statement=req.normalized_statement,
        extraction_version=req.extraction_version,
        source_document_sha256=req.source_document_sha256 or (doc.sha256_hash if doc else None),
        verification_status=res["verification_status"],
        matched_page_number=res["matched_page_number"],
        verification_detail=res["verification_detail"],
        supporting_sources=[
            TenderRequirementSourceResponse.model_validate(s) for s in res["supporting_sources"]
        ],
    )


@router.post("/{tender_id}/detect-conflicts", response_model=ConflictDetectionRunResponse)
async def detect_tender_conflicts(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Run deterministic scope-aware cross-document conflict and potential-amendment detection."""
    await get_authorized_tender(tender_id, current_user, db)
    svc = TenderRequirementConflictService()
    conflicts = await svc.detect_conflicts(db, tender_id)
    await db.commit()
    return ConflictDetectionRunResponse(
        tender_id=tender_id,
        detected_count=len(conflicts),
        conflicts=[TenderRequirementConflictResponse.model_validate(c) for c in conflicts],
    )


@router.get("/{tender_id}/conflicts", response_model=TenderRequirementConflictsListResponse)
async def list_tender_conflicts(
    tender_id: UUID,
    conflict_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    conflict_status: Optional[str] = Query(None, alias="status"),
    source_document_id: Optional[UUID] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """List detected cross-document conflicts with pagination and filtering."""
    await get_authorized_tender(tender_id, current_user, db)
    conditions = [TenderRequirementConflict.tender_id == tender_id]
    if conflict_type:
        conditions.append(TenderRequirementConflict.conflict_type == conflict_type.strip().upper())
    if severity:
        conditions.append(TenderRequirementConflict.severity == severity.strip().upper())
    if conflict_status:
        conditions.append(TenderRequirementConflict.status == conflict_status.strip().upper())

    if source_document_id or category:
        req_sub_conds = [TenderRequirement.tender_id == tender_id]
        if source_document_id:
            req_sub_conds.append(TenderRequirement.source_document_id == source_document_id)
        if category:
            req_sub_conds.append(TenderRequirement.primary_category == category.strip().upper())
        matching_req_ids = select(TenderRequirement.id).where(*req_sub_conds)
        conditions.append(
            or_(
                TenderRequirementConflict.requirement_a_id.in_(matching_req_ids),
                TenderRequirementConflict.requirement_b_id.in_(matching_req_ids),
            )
        )

    total = (
        await db.execute(select(func.count(TenderRequirementConflict.id)).where(*conditions))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(TenderRequirementConflict)
            .where(*conditions)
            .order_by(TenderRequirementConflict.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return TenderRequirementConflictsListResponse(
        tender_id=tender_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[TenderRequirementConflictResponse.model_validate(r) for r in rows],
    )


@router.get("/{tender_id}/conflicts/{conflict_id}", response_model=TenderRequirementConflictDetailResponse)
async def get_tender_conflict_detail(
    tender_id: UUID,
    conflict_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """Retrieve conflict detail with both source requirement records."""
    await get_authorized_tender(tender_id, current_user, db)
    conflict = (
        await db.execute(
            select(TenderRequirementConflict).where(
                TenderRequirementConflict.id == conflict_id,
                TenderRequirementConflict.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not conflict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender conflict not found.")

    req_a = (
        await db.execute(select(TenderRequirement).where(TenderRequirement.id == conflict.requirement_a_id))
    ).scalar_one_or_none()
    req_b = (
        await db.execute(select(TenderRequirement).where(TenderRequirement.id == conflict.requirement_b_id))
    ).scalar_one_or_none()

    base = TenderRequirementConflictResponse.model_validate(conflict).model_dump()
    return TenderRequirementConflictDetailResponse(
        **base,
        requirement_a=TenderRequirementResponse.model_validate(req_a) if req_a else None,
        requirement_b=TenderRequirementResponse.model_validate(req_b) if req_b else None,
    )


@router.get(
    "/{tender_id}/requirements/{requirement_id}/evidence-mappings",
    response_model=TenderRequirementEvidenceListResponse,
)
async def get_requirement_evidence_mappings(
    tender_id: UUID,
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:read")),
):
    """List expected bidder evidence mappings for a tender requirement."""
    await get_authorized_tender(tender_id, current_user, db)
    req = (
        await db.execute(
            select(TenderRequirement).where(
                TenderRequirement.id == requirement_id,
                TenderRequirement.tender_id == tender_id,
            )
        )
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender requirement not found.")

    rows = (
        await db.execute(
            select(TenderRequirementEvidence)
            .where(
                TenderRequirementEvidence.requirement_id == requirement_id,
                TenderRequirementEvidence.tender_id == tender_id,
            )
            .order_by(TenderRequirementEvidence.created_at.asc())
        )
    ).scalars().all()

    return TenderRequirementEvidenceListResponse(
        tender_id=tender_id,
        requirement_id=requirement_id,
        total=len(rows),
        items=[TenderRequirementEvidenceResponse.model_validate(r) for r in rows],
    )


@router.post(
    "/{tender_id}/requirements/{requirement_id}/generate-evidence-mappings",
    response_model=TenderRequirementEvidenceListResponse,
)
async def generate_requirement_evidence_mappings(
    tender_id: UUID,
    requirement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tender:update")),
):
    """Generate source-grounded expected evidence mappings for a tender requirement."""
    await get_authorized_tender(tender_id, current_user, db)
    svc = TenderRequirementEvidenceService()
    try:
        rows = await svc.generate_for_requirement(db, tender_id, requirement_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender requirement not found.")
    await db.commit()
    return TenderRequirementEvidenceListResponse(
        tender_id=tender_id,
        requirement_id=requirement_id,
        total=len(rows),
        items=[TenderRequirementEvidenceResponse.model_validate(r) for r in rows],
    )


# ==============================================================================
# Phase 2.0E: Human Review & Decision Workflows
# ==============================================================================


@router.get("/{tender_id}/tenderlens-review-queue", response_model=ReviewQueueListResponse)
async def list_tender_review_queue(
    tender_id: UUID,
    object_type: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None, alias="status"),
    primary_category: Optional[str] = Query(None),
    provenance_status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    assigned_reviewer_id: Optional[UUID] = Query(None),
    unassigned_only: bool = Query(False),
    source_document_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    """Consolidated review queue across requirements, conflicts, and evidence mappings."""
    await get_authorized_tender(tender_id, current_user, db)
    total, items = await TenderReviewService.list_review_queue(
        db=db,
        tender_id=tender_id,
        object_type=object_type,
        review_status=review_status,
        primary_category=primary_category,
        provenance_status=provenance_status,
        severity=severity,
        assigned_reviewer_id=assigned_reviewer_id,
        unassigned_only=unassigned_only,
        source_document_id=source_document_id,
        limit=limit,
        offset=offset,
    )
    return ReviewQueueListResponse(
        tender_id=tender_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[ReviewQueueItemResponse(**it) for it in items],
    )


@router.get("/{tender_id}/review-workload", response_model=ReviewWorkloadSummaryResponse)
async def get_tender_review_workload(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    """Retrieve review workload counts across requirements, conflicts, and evidence mappings."""
    await get_authorized_tender(tender_id, current_user, db)
    summary = await TenderReviewService.get_workload_summary(db, tender_id)
    return ReviewWorkloadSummaryResponse(**summary)


@router.post("/{tender_id}/review-decisions", response_model=ReviewDecisionMutationResponse)
async def submit_tender_review_decision(
    tender_id: UUID,
    payload: ReviewDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("evaluation:override")),
):
    """Submit a human review decision or reopen a previously reviewed item with optimistic concurrency."""
    tender = await get_authorized_tender(tender_id, current_user, db)
    updated_obj, decision = await TenderReviewService.submit_decision(
        db=db,
        tender=tender,
        actor=current_user,
        object_type=payload.object_type,
        object_id=payload.object_id,
        decision_type=payload.decision_type,
        expected_version=payload.expected_version,
        rationale=payload.rationale,
    )
    return ReviewDecisionMutationResponse(
        object_type=decision.object_type,
        object_id=decision.object_id,
        new_status=decision.new_status,
        review_version=updated_obj.review_version,
        assigned_reviewer_id=updated_obj.assigned_reviewer_id,
        decision=ReviewDecisionResponse.model_validate(decision),
    )


@router.post("/{tender_id}/review-assignments", response_model=ReviewDecisionMutationResponse)
async def assign_tender_reviewer(
    tender_id: UUID,
    payload: ReviewAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:manage")),
):
    """Assign or reassign a reviewable item to an active organization reviewer."""
    tender = await get_authorized_tender(tender_id, current_user, db)
    updated_obj, decision = await TenderReviewService.assign_reviewer(
        db=db,
        tender=tender,
        actor=current_user,
        object_type=payload.object_type,
        object_id=payload.object_id,
        assignee_user_id=payload.assignee_user_id,
        expected_version=payload.expected_version,
        rationale=payload.rationale,
    )
    return ReviewDecisionMutationResponse(
        object_type=decision.object_type,
        object_id=decision.object_id,
        new_status=decision.new_status,
        review_version=updated_obj.review_version,
        assigned_reviewer_id=updated_obj.assigned_reviewer_id,
        decision=ReviewDecisionResponse.model_validate(decision),
    )


@router.get("/{tender_id}/review-history", response_model=ReviewDecisionHistoryListResponse)
async def list_tender_review_history(
    tender_id: UUID,
    object_type: Optional[str] = Query(None),
    object_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit:read")),
):
    """Retrieve append-only human review decision history for a tender or specific review item."""
    await get_authorized_tender(tender_id, current_user, db)
    conditions = [ReviewDecision.tender_id == tender_id]
    if object_type:
        conditions.append(ReviewDecision.object_type == object_type.strip().upper())
    if object_id:
        conditions.append(ReviewDecision.object_id == object_id)

    total = (await db.execute(select(func.count(ReviewDecision.id)).where(*conditions))).scalar() or 0
    rows = (
        await db.execute(
            select(ReviewDecision)
            .where(*conditions)
            .order_by(ReviewDecision.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return ReviewDecisionHistoryListResponse(
        tender_id=tender_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[ReviewDecisionResponse.model_validate(r) for r in rows],
    )
