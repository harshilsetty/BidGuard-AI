from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Numeric, String, Integer, JSON, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import BaseModelMixin


class Tender(Base, BaseModelMixin):
    __tablename__ = "tenders"

    # Multi-tenant scoping: nullable to maintain 100% backward compatibility with Golden Demo fixtures
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    gem_tender_id = Column(String(100), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    file_name = Column(String(300), nullable=True)
    file_path = Column(String(1000), nullable=True)
    total_pages = Column(Integer, default=0, nullable=False)

    # Allowed statuses: UPLOADED, EXTRACTING, REVIEW, READY, FAILED
    extraction_status = Column(String(50), default="UPLOADED", nullable=False, index=True)

    # Tracks highest sequence number per category so codes are never recycled
    # e.g., {"TECH": 4, "FIN": 2, "STAT": 3, "EXP": 1, "DEL": 1}
    next_clause_seq = Column(JSON, default=dict, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="tenders")
    documents = relationship(
        "TenderDocument",
        back_populates="tender",
        cascade="all, delete-orphan",
        order_by="TenderDocument.created_at",
    )
    clauses = relationship("TenderClause", back_populates="tender", cascade="all, delete-orphan", order_by="TenderClause.clause_code")
    bidders = relationship("Bidder", back_populates="tender", cascade="all, delete-orphan")


class TenderDocument(Base, BaseModelMixin):
    """Multi-document attachment belonging to a tenant-scoped Tender."""
    __tablename__ = "tender_documents"
    __table_args__ = (
        UniqueConstraint("tender_id", "sha256_hash", name="uq_tender_documents_tender_sha256"),
    )

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Supported roles: PRIMARY_NIT, TECHNICAL_SPEC, BOQ, CORRIGENDUM, ANNEXURE, OTHER
    document_role = Column(String(50), default="PRIMARY_NIT", nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(1000), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    sha256_hash = Column(String(64), nullable=False, index=True)
    total_pages = Column(Integer, nullable=True)
    # Allowed statuses: UPLOADED, QUEUED, PROCESSING, READY, FAILED
    processing_status = Column(String(50), default="UPLOADED", nullable=False, index=True)
    # Optional Phase 2.0D relationship metadata (never invented)
    document_date = Column(DateTime(timezone=True), nullable=True)
    issue_date = Column(DateTime(timezone=True), nullable=True)
    reference_number = Column(String(128), nullable=True)
    related_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    applicability_scope = Column(String(200), nullable=True)
    revision_info = Column(String(128), nullable=True)

    tender = relationship("Tender", back_populates="documents")
    pages = relationship(
        "TenderDocumentPage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="TenderDocumentPage.page_number",
    )
    processing_jobs = relationship(
        "TenderProcessingJob",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="TenderProcessingJob.created_at.desc()",
    )


class TenderProcessingJob(Base, BaseModelMixin):
    """Persistent PostgreSQL-backed asynchronous document processing job."""
    __tablename__ = "tender_processing_jobs"

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tender_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type = Column(String(50), default="PAGE_EXTRACTION", nullable=False)
    # States: QUEUED, RUNNING, RETRY_WAIT, SUCCEEDED, FAILED
    status = Column(String(50), default="QUEUED", nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    progress_pct = Column(Integer, default=0, nullable=False)
    # Stages: QUEUED, VALIDATING_DOCUMENT, EXTRACTING_PAGES, PERSISTING_PAGES, FINALIZING
    current_stage = Column(String(64), default="QUEUED", nullable=False)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    worker_id = Column(String(128), nullable=True)
    ownership_generation = Column(Integer, default=0, nullable=False)
    extracted_count = Column(Integer, default=0, nullable=False)
    extraction_version = Column(Integer, default=1, nullable=False)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("TenderDocument", back_populates="processing_jobs")


class TenderDocumentPage(Base, BaseModelMixin):
    """Persisted page-level digital/OCR extraction output for a TenderDocument."""
    __tablename__ = "tender_document_pages"
    __table_args__ = (
        UniqueConstraint("tender_document_id", "page_number", name="uq_tender_document_pages_doc_page"),
    )

    tender_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number = Column(Integer, nullable=False)
    extracted_text = Column(Text, default="", nullable=False)
    word_count = Column(Integer, default=0, nullable=False)
    # DIGITAL_TEXT, OCR_PROCESSED, OCR_LOW_CONFIDENCE, OCR_FAILED, EMPTY_SCANNED
    extraction_method = Column(String(50), nullable=False)
    ocr_confidence = Column(Numeric(4, 3), nullable=True)
    # SUCCEEDED, EMPTY, FAILED
    extraction_status = Column(String(50), default="SUCCEEDED", nullable=False)

    document = relationship("TenderDocument", back_populates="pages")


class TenderRequirement(Base, BaseModelMixin):
    """Source-grounded procurement requirement extracted from TenderDocumentPage records."""
    __tablename__ = "tender_requirements"

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requirement_code = Column(String(50), nullable=False, index=True)
    extraction_version = Column(Integer, default=1, nullable=False, index=True)

    source_page_number = Column(Integer, nullable=False)
    source_page_range = Column(String(32), nullable=True)
    source_section = Column(String(200), nullable=True)
    source_text = Column(Text, nullable=False)
    source_quote_verified = Column(Boolean, default=False, nullable=False)

    normalized_statement = Column(Text, nullable=False)
    explanatory_interpretation = Column(Text, nullable=False)

    # ELIG, TECH, FIN, STAT, EXP, DOC, DEL, SUB, DATE, PREF, UNCLASSIFIED
    primary_category = Column(String(32), nullable=False, index=True)
    secondary_categories = Column(JSON, default=list, nullable=False)
    requirement_type = Column(String(50), default="OTHER", nullable=False)
    # MANDATORY, OPTIONAL, UNCLEAR
    mandatory_status = Column(String(20), default="UNCLEAR", nullable=False, index=True)

    expected_document_or_evidence = Column(Text, nullable=True)
    expected_action_by_bidder = Column(Text, nullable=True)
    numeric_value = Column(String(64), nullable=True)
    unit = Column(String(64), nullable=True)
    currency = Column(String(16), nullable=True)
    period_or_validity = Column(String(128), nullable=True)
    conditions_and_exceptions = Column(Text, nullable=True)

    extraction_method = Column(String(50), default="LLM_STRUCTURED", nullable=False)
    model_provider = Column(String(64), default="nvidia_nim", nullable=False)
    model_version = Column(String(128), nullable=True)
    extraction_confidence = Column(Float, default=0.5, nullable=False)
    # DRAFT, CONFIRMED, REJECTED, NEEDS_REVIEW, SUPERSEDED
    review_status = Column(String(32), default="DRAFT", nullable=False, index=True)
    # VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, SOURCE_NOT_FOUND, SOURCE_CHANGED, NEEDS_REVIEW
    provenance_status = Column(String(32), default="UNVERIFIED", nullable=False, index=True)
    source_document_sha256 = Column(String(64), nullable=True)
    review_version = Column(Integer, default=1, nullable=False)
    assigned_reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    last_reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)


class TenderRequirementSource(Base, BaseModelMixin):
    """Additional supporting, contextual, or contradictory source passage for a TenderRequirement."""
    __tablename__ = "tender_requirement_sources"

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # PRIMARY_SUPPORTING, ADDITIONAL_SUPPORTING, CONTEXTUAL, POTENTIALLY_CONTRADICTORY
    source_role = Column(String(40), default="ADDITIONAL_SUPPORTING", nullable=False)
    source_page_number = Column(Integer, nullable=False)
    source_section = Column(String(200), nullable=True)
    source_text = Column(Text, nullable=False)
    # VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, SOURCE_NOT_FOUND, SOURCE_CHANGED, NEEDS_REVIEW
    verification_status = Column(String(32), default="UNVERIFIED", nullable=False)
    source_document_sha256 = Column(String(64), nullable=True)


class TenderRequirementConflict(Base, BaseModelMixin):
    """Cross-document conflict or potential corrigendum amendment detected between requirements."""
    __tablename__ = "tender_requirement_conflicts"

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_a_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_b_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NUMERIC_MISMATCH, DATE_MISMATCH, TECHNICAL_MISMATCH, ELIGIBILITY_MISMATCH,
    # FINANCIAL_MISMATCH, DOCUMENT_MISMATCH, DELIVERY_MISMATCH, SCOPE_MISMATCH, OTHER
    conflict_type = Column(String(40), nullable=False, index=True)
    # CONFLICT, POTENTIAL_AMENDMENT
    relationship_type = Column(String(40), default="CONFLICT", nullable=False)
    # LOW, MEDIUM, HIGH, CRITICAL
    severity = Column(String(20), default="MEDIUM", nullable=False, index=True)
    # DETECTED, NEEDS_REVIEW, CONFIRMED, DISMISSED, RESOLVED
    status = Column(String(24), default="DETECTED", nullable=False, index=True)
    scope_summary = Column(String(255), nullable=True)
    explanation = Column(Text, nullable=False)
    review_version = Column(Integer, default=1, nullable=False)
    assigned_reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)


class TenderRequirementEvidence(Base, BaseModelMixin):
    """Expected bidder evidence mapping grounded in a TenderRequirement."""
    __tablename__ = "tender_requirement_evidence"

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tender_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type = Column(String(64), nullable=False, index=True)
    expected_document_name = Column(String(255), nullable=False)
    evidence_purpose = Column(Text, nullable=False)
    is_mandatory = Column(Boolean, default=True, nullable=False)
    source_passage = Column(Text, nullable=False)
    mapping_method = Column(String(50), default="DETERMINISTIC_RULE", nullable=False)
    confidence = Column(Float, default=0.75, nullable=False)
    # SUGGESTED, NEEDS_REVIEW, CONFIRMED, REJECTED
    mapping_status = Column(String(24), default="SUGGESTED", nullable=False, index=True)
    review_version = Column(Integer, default=1, nullable=False)
    assigned_reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)


class ReviewDecision(Base, BaseModelMixin):
    """Append-only, immutable human review decision history across requirements, conflicts, and evidence."""
    __tablename__ = "review_decisions"

    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # REQUIREMENT, CONFLICT, EVIDENCE
    object_type = Column(String(32), nullable=False, index=True)
    object_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    reviewer_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # CONFIRM, REJECT, REQUEST_CLARIFICATION, DISMISS, RESOLVE, REOPEN, ASSIGN
    decision_type = Column(String(32), nullable=False, index=True)
    previous_status = Column(String(32), nullable=False)
    new_status = Column(String(32), nullable=False)
    rationale = Column(Text, nullable=False)
    object_version = Column(Integer, nullable=False)
    source_document_sha256 = Column(String(64), nullable=True)
    assigned_to_user_id = Column(UUID(as_uuid=True), nullable=True)
