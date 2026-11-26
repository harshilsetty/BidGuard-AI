from sqlalchemy import BigInteger, Column, DateTime, Numeric, String, Integer, JSON, ForeignKey, Text, UniqueConstraint
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
