from sqlalchemy import Column, String, Integer, JSON, ForeignKey
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
    clauses = relationship("TenderClause", back_populates="tender", cascade="all, delete-orphan", order_by="TenderClause.clause_code")
    bidders = relationship("Bidder", back_populates="tender", cascade="all, delete-orphan")
