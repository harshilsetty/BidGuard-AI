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
    extracted_count: int = 0
    extraction_version: int = 1
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


class TenderRequirementResponse(BaseModel):
    """Source-grounded draft procurement requirement extracted by TenderLens."""
    id: UUID
    tender_id: UUID
    source_document_id: UUID
    processing_job_id: Optional[UUID] = None
    requirement_code: str
    extraction_version: int
    source_page_number: int
    source_page_range: Optional[str] = None
    source_section: Optional[str] = None
    source_text: str
    source_quote_verified: bool
    normalized_statement: str
    explanatory_interpretation: str
    primary_category: str
    secondary_categories: List[str] = []
    requirement_type: str
    mandatory_status: str
    expected_document_or_evidence: Optional[str] = None
    expected_action_by_bidder: Optional[str] = None
    numeric_value: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    period_or_validity: Optional[str] = None
    conditions_and_exceptions: Optional[str] = None
    extraction_method: str
    model_provider: str
    model_version: Optional[str] = None
    extraction_confidence: float
    review_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenderRequirementsListResponse(BaseModel):
    """Paginated TenderLens requirement listing."""
    tender_id: UUID
    total: int
    limit: int
    offset: int
    items: List[TenderRequirementResponse]


class TenderRequirementSourceResponse(BaseModel):
    id: UUID
    requirement_id: UUID
    source_document_id: UUID
    source_role: str
    source_page_number: int
    source_section: Optional[str] = None
    source_text: str
    verification_status: str
    source_document_sha256: Optional[str] = None

    class Config:
        from_attributes = True


class TenderRequirementProvenanceResponse(BaseModel):
    requirement_id: UUID
    tender_id: UUID
    source_document_id: UUID
    source_document_name: Optional[str] = None
    source_document_role: Optional[str] = None
    source_page_number: int
    source_page_range: Optional[str] = None
    source_section: Optional[str] = None
    source_text: str
    normalized_statement: str
    extraction_version: int
    source_document_sha256: Optional[str] = None
    verification_status: str
    matched_page_number: Optional[int] = None
    verification_detail: str
    supporting_sources: List[TenderRequirementSourceResponse] = []


class TenderRequirementConflictResponse(BaseModel):
    id: UUID
    tender_id: UUID
    requirement_a_id: UUID
    requirement_b_id: UUID
    conflict_type: str
    relationship_type: str
    severity: str
    status: str
    scope_summary: Optional[str] = None
    explanation: str
    reviewed_by_user_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenderRequirementConflictDetailResponse(TenderRequirementConflictResponse):
    requirement_a: Optional[TenderRequirementResponse] = None
    requirement_b: Optional[TenderRequirementResponse] = None


class TenderRequirementConflictsListResponse(BaseModel):
    tender_id: UUID
    total: int
    limit: int
    offset: int
    items: List[TenderRequirementConflictResponse]


class ConflictDetectionRunResponse(BaseModel):
    tender_id: UUID
    detected_count: int
    conflicts: List[TenderRequirementConflictResponse]


class TenderRequirementEvidenceResponse(BaseModel):
    id: UUID
    tender_id: UUID
    requirement_id: UUID
    evidence_type: str
    expected_document_name: str
    evidence_purpose: str
    is_mandatory: bool
    source_passage: str
    mapping_method: str
    confidence: float
    mapping_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenderRequirementEvidenceListResponse(BaseModel):
    tender_id: UUID
    requirement_id: UUID
    total: int
    items: List[TenderRequirementEvidenceResponse]
