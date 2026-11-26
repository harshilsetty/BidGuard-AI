from typing import Optional, List, Dict, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.clause import ClauseResponse


TenderDocumentRole = Literal[
    "PRIMARY_NIT",
    "TECHNICAL_SPEC",
    "BOQ",
    "CORRIGENDUM",
    "ANNEXURE",
    "OTHER",
]


class TenderProcessingJobResponse(BaseModel):
    """Sanitized asynchronous document processing job state (no internal paths or worker IDs)."""
    id: UUID
    tender_id: UUID
    tender_document_id: UUID
    job_type: str
    status: str
    current_stage: str
    progress_pct: int
    retry_count: int
    max_retries: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenderDocumentPageResponse(BaseModel):
    """Persisted page-level digital/OCR extraction output."""
    id: UUID
    tender_document_id: UUID
    page_number: int
    extracted_text: str
    word_count: int
    extraction_method: str
    ocr_confidence: Optional[float] = None
    extraction_status: str

    class Config:
        from_attributes = True


class TenderDocumentPagesListResponse(BaseModel):
    """Paginated page extraction results."""
    tender_id: UUID
    tender_document_id: UUID
    total: int
    limit: int
    offset: int
    items: List[TenderDocumentPageResponse]


class TenderDocumentResponse(BaseModel):
    """Public tender document metadata (never exposes internal storage_path)."""
    id: UUID
    tender_id: UUID
    document_role: str
    original_filename: str
    file_size_bytes: int
    sha256_hash: str
    total_pages: Optional[int] = None
    processing_status: str
    created_at: datetime
    updated_at: datetime
    latest_job: Optional[TenderProcessingJobResponse] = None

    class Config:
        from_attributes = True


class TenderCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    gem_tender_id: Optional[str] = Field(None, max_length=100)


class TenderResponse(BaseModel):
    id: UUID
    title: str
    gem_tender_id: Optional[str] = None
    file_name: Optional[str] = None
    total_pages: int
    extraction_status: str
    created_at: datetime
    updated_at: datetime
    clause_count: int = 0

    class Config:
        from_attributes = True


class TenderDetailResponse(BaseModel):
    id: UUID
    title: str
    gem_tender_id: Optional[str] = None
    file_name: Optional[str] = None
    total_pages: int
    extraction_status: str
    created_at: datetime
    updated_at: datetime
    clauses: List[ClauseResponse] = []
    documents: List[TenderDocumentResponse] = []

    class Config:
        from_attributes = True


class ExtractionResultResponse(BaseModel):
    tender_id: UUID
    extraction_status: str
    total_pages: int
    extracted_count: int
    clauses: List[ClauseResponse]
