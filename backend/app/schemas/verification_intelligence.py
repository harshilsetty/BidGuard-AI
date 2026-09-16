"""Pydantic schemas for Phase 8.4 Verification Intelligence & Officer Risk View.

Aggregates statutory source verification facts, cross-source contradiction facts,
debarment temporal facts, compliance clause evaluations, and OCR quality signals
into structured officer-facing intelligence for procurement decision support.

Strict Protections:
- 100-Point Score Formula is untouched.
- Technical source failures (TIMEOUT, UNAVAILABLE, AUTH_FAILURE, FAILED) != bidder non-compliance.
- Missing as_of_date remains UNKNOWN_PERIOD / UNVERIFIED without date.today() fallback.
- Exactly 11 statutory/mock sources.
- Append-only verification history.
- Decision support only (no automatic disqualification or winner selection).
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.scoring import RiskLevel, ScoreBreakdown


OFFICER_INTELLIGENCE_DISCLAIMER = (
    "Procurement Officer Verification Intelligence & Decision Support. "
    "Statutory facts, temporal provenance, and risk signals are aggregated for human evaluation. "
    "Final procurement qualification and award decisions remain exclusively with the authorized officer."
)


class RiskReasonCode(str, Enum):
    """Deterministic, structured risk and review reason codes."""
    ACTIVE_DEBARMENT = "ACTIVE_DEBARMENT"
    MAJOR_CONTRADICTION = "MAJOR_CONTRADICTION"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_TIMEOUT = "SOURCE_TIMEOUT"
    SOURCE_AUTH_FAILURE = "SOURCE_AUTH_FAILURE"
    SOURCE_FAILED = "SOURCE_FAILED"
    TEMPORAL_UNVERIFIED = "TEMPORAL_UNVERIFIED"
    OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
    MANDATORY_CLAUSE_FAIL = "MANDATORY_CLAUSE_FAIL"
    RECOMMENDATION_REVIEW = "RECOMMENDATION_REVIEW"


class RiskReasonSeverity(str, Enum):
    """Standardized severity classification for structured risk reasons."""
    HIGH = "HIGH"
    REVIEW = "REVIEW"
    INFO = "INFO"


class RiskReasonItem(BaseModel):
    """Structured, explainable risk or review reason with explicit provenance."""
    model_config = ConfigDict(from_attributes=True)

    reason_code: RiskReasonCode = Field(..., description="Machine-readable deterministic reason code")
    severity: RiskReasonSeverity = Field(..., description="Severity level: HIGH, REVIEW, or INFO")
    title: str = Field(..., description="Concise human-readable title for officer UI")
    explanation: str = Field(..., description="Factual explanation traceable to source data")
    source_type: str = Field(..., description="Category: STATUTORY, DEBARMENT, CROSS_SOURCE, TENDER_CLAUSE, OCR, RECOMMENDATION")
    source_name: str = Field(..., description="Specific authority or document name")
    verification_id: Optional[str] = Field(None, description="Statutory verification execution ID if applicable")
    clause_code: Optional[str] = Field(None, description="Tender clause code if applicable (e.g. FIN-01)")
    evidence_reference: Optional[str] = Field(None, description="Evidence chunk, document reference, or order number")
    requires_officer_review: bool = Field(True, description="Whether this item requires officer attention")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when risk reason was identified"
    )


class SourceStatusItem(BaseModel):
    """Normalized status and provenance for one of the 11 statutory/mock sources."""
    model_config = ConfigDict(from_attributes=True)

    authority: str = Field(..., description="Authority identifier (e.g. GSTN, UDYAM, NSIC, DIGILOCKER)")
    source_name: str = Field(..., description="Human-readable authority name")
    connection_status: str = Field(..., description="Transport status: SUCCESS, TIMEOUT, UNAVAILABLE, AUTH_FAILURE, ERROR")
    verification_status: str = Field(..., description="Business status: VERIFIED, NOT_FOUND, UNVERIFIED, EXPIRED, INACTIVE, FAILED")
    is_technical_failure: bool = Field(..., description="True if transport or execution failed (not bidder fault)")
    is_business_not_found: bool = Field(..., description="True if transport succeeded but entity was not found")
    retrieved_at: Optional[datetime] = Field(None, description="Exact timestamp of retrieval from source")
    as_of_date: Optional[date] = Field(None, description="Evaluation reference date used during query")
    query_identifier: Optional[str] = Field(None, description="Identifier sent to source")
    identifier_type: Optional[str] = Field(None, description="Type of identifier (pan, cin, gstin, etc.)")
    validity_start: Optional[str] = Field(None, description="Registration or document validity start date")
    validity_end: Optional[str] = Field(None, description="Registration or document expiry date")
    provenance_note: str = Field("", description="Authoritative banner or mock demonstration disclaimer")
    verification_id: Optional[str] = Field(None, description="Verification execution UUID")
    error_message: Optional[str] = Field(None, description="Technical error detail if connection/execution failed")
    is_mock: bool = Field(True, description="True for synthetic demonstration source")
    previous_successful_result: Optional[Dict[str, Any]] = Field(
        None,
        description="Historical successful verification if latest attempt suffered a technical failure"
    )


class DebarmentStateSummary(BaseModel):
    """Consolidated debarment verification state for bidder."""
    model_config = ConfigDict(from_attributes=True)

    is_debarred: bool = Field(..., description="Whether entity is actively debarred as of reference date")
    temporal_status: str = Field(..., description="ACTIVE_ON_DATE, EXPIRED_BEFORE_DATE, STARTS_AFTER_DATE, UNKNOWN_PERIOD, NOT_FOUND")
    order_number: Optional[str] = Field(None, description="Official debarment order number")
    authority: Optional[str] = Field(None, description="Debarring authority (CPPP, State, etc.)")
    start_date: Optional[str] = Field(None, description="Debarment start date")
    end_date: Optional[str] = Field(None, description="Debarment end date")
    as_of_date: Optional[date] = Field(None, description="Reference date evaluated")
    reason: Optional[str] = Field(None, description="Debarment grounds or explanation")
    verification_id: Optional[str] = Field(None, description="Debarment verification execution ID")
    provenance_note: str = Field("", description="Source provenance note")


class OfficerBidderVerificationSummary(BaseModel):
    """Consolidated officer-facing verification intelligence summary for a bidder."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder UUID")
    tender_id: str = Field(..., description="Tender UUID")
    company_name: str = Field(..., description="Bidder legal enterprise name")
    overall_risk_state: RiskLevel = Field(..., description="Overall risk state: LOW, MEDIUM, or HIGH")
    base_compliance_score: float = Field(..., ge=0.0, le=100.0, description="Phase 6.4 100-point score (unaltered)")
    score_breakdown: ScoreBreakdown = Field(..., description="Four-part 100-point score component breakdown")
    debarment_state: DebarmentStateSummary = Field(..., description="Consolidated debarment facts")
    source_statuses: Dict[str, SourceStatusItem] = Field(
        ...,
        description="Status map for all 11 authorities (GSTN, Udyam, MCA, Income Tax, MII, Debarment, DPIIT, EPFO, ESIC, NSIC, DigiLocker)"
    )
    major_contradictions: List[str] = Field(default_factory=list, description="List of major cross-source contradiction descriptions")
    identity_conflicts: List[str] = Field(default_factory=list, description="List of identity conflicts between bidder and source")
    missing_or_insufficient_evidence: List[str] = Field(default_factory=list, description="Clauses lacking required substantiating evidence")
    technical_source_failures: List[str] = Field(default_factory=list, description="Technical source connection or execution issues")
    officer_review_required: bool = Field(..., description="True if any risk trigger necessitates officer human review")
    risk_reasons: List[RiskReasonItem] = Field(default_factory=list, description="Exhaustive structured risk reasons with provenance")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of evaluation")
    as_of_date: Optional[date] = Field(None, description="Reference evaluation date")
    disclaimer: str = Field(default=OFFICER_INTELLIGENCE_DISCLAIMER, description="Statutory decision support disclaimer")


class VerificationHistoryItem(BaseModel):
    """Individual append-only verification attempt record."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Database record primary key")
    verification_id: str = Field(..., description="Execution batch UUID")
    authority: str = Field(..., description="Authority identifier")
    source_name: str = Field(..., description="Source name")
    query_identifier: str = Field(..., description="Identifier queried")
    identifier_type: str = Field(..., description="Identifier type (pan, cin, gstin, etc.)")
    connection_status: str = Field(..., description="Transport connection status")
    verification_status: str = Field(..., description="Business verification status")
    is_latest: bool = Field(False, description="True if this is the most recent execution for this authority")
    retrieved_at: datetime = Field(..., description="Execution timestamp")
    as_of_date: Optional[date] = Field(None, description="As-of evaluation date")
    data_payload: Dict[str, Any] = Field(default_factory=dict, description="Sanitized factual payload")
    confidence_score: float = Field(1.0, description="Source confidence score")
    provenance_note: str = Field("", description="Provenance note")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    execution_time_ms: float = Field(0.0, description="Execution time in ms")


class VerificationHistoryResponse(BaseModel):
    """Complete append-only historical audit trail of statutory verification attempts."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder UUID")
    tender_id: str = Field(..., description="Tender UUID")
    total_attempts: int = Field(..., description="Total historical attempts recorded")
    history: List[VerificationHistoryItem] = Field(
        default_factory=list,
        description="Chronologically sorted historical records"
    )
    disclaimer: str = Field(default=OFFICER_INTELLIGENCE_DISCLAIMER, description="Audit trail disclaimer")


class ReviewQueueItem(BaseModel):
    """Item in the officer human review queue representing a bidder requiring attention."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder UUID")
    tender_id: str = Field(..., description="Tender UUID")
    company_name: str = Field(..., description="Bidder company name")
    overall_risk_state: RiskLevel = Field(..., description="Risk level (HIGH, MEDIUM, LOW)")
    compliance_score: float = Field(..., description="100-point compliance score")
    review_triggers: List[str] = Field(default_factory=list, description="Specific triggers placing bidder in review queue")
    primary_risk_reasons: List[RiskReasonItem] = Field(default_factory=list, description="Top structured risk reasons")
    debarred: bool = Field(False, description="Whether bidder is actively debarred")
    contradiction_count: int = Field(0, description="Count of major contradictions")
    technical_failure_count: int = Field(0, description="Count of statutory technical failures")
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Queue entry timestamp")


class OfficerReviewQueueResponse(BaseModel):
    """Consolidated review queue for all bidders under a tender requiring officer review."""
    model_config = ConfigDict(from_attributes=True)

    tender_id: str = Field(..., description="Tender UUID")
    total_queued: int = Field(..., description="Number of bidders requiring officer review")
    items: List[ReviewQueueItem] = Field(
        default_factory=list,
        description="Bidders ordered deterministically: HIGH risk first, then by trigger count, then bidder ID"
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Report generation timestamp")
    disclaimer: str = Field(default=OFFICER_INTELLIGENCE_DISCLAIMER, description="Advisory queue disclaimer")
