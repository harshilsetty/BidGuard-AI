"""
Strict Pydantic schemas for AI Engine structured output contract.
Ensures zero uncontrolled text responses from LLMs.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class ExtractedRequirement(BaseModel):
    requirement_id: str = Field(description="Unique identifier for the requirement, e.g. REQ-001")
    category: str = Field(description="Category, e.g. financial, technical, statutory, experience, legal")
    text: str = Field(description="Exact text or normalized summary of the tender requirement")
    source_clause: Optional[str] = Field(None, description="Clause or section identifier in tender")
    page_number: int = Field(description="1-indexed page number where requirement appears")
    is_mandatory: bool = Field(default=True, description="Whether this is a non-negotiable mandatory qualification criteria")


class EvidenceItem(BaseModel):
    """
    Standard evidence locator citation linking directly to a source document and page.
    """
    text: str = Field(description="Extracted quote or textual evidence snippet from bidder document")
    document: str = Field(description="Filename or identifier of the source PDF document")
    page: int = Field(description="1-indexed page number in the source PDF document")


class ExtractedEvidence(BaseModel):
    evidence_id: str = Field(description="Unique identifier for the extracted evidence snippet")
    source_document: str = Field(description="Name of the bidder submission document")
    page_number: int = Field(description="1-indexed page number in the bidder document")
    extracted_text: str = Field(description="Extracted text snippet or claim from bidder document")
    entity_names: List[str] = Field(default_factory=list, description="Extracted entity names or identifiers")
    dates: List[str] = Field(default_factory=list, description="Extracted dates (DD/MM/YYYY or ISO)")
    monetary_values: List[float] = Field(default_factory=list, description="Extracted currency values in INR")


class AIComplianceEvaluation(BaseModel):
    """
    The canonical AI -> Backend Structured Output Contract.
    Returned by the AI Engine / RAG Pipeline for every evaluated tender requirement.
    """
    requirement_id: str = Field(description="Unique requirement identifier, e.g. REQ-001")
    requirement: str = Field(description="The tender qualification requirement text")
    requirement_type: str = Field(description="Type: financial, technical, statutory, experience, or legal")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="List of evidence items extracted from bidder submissions")
    status: ComplianceStatus = Field(description="Objective verification status: PASS, FAIL, or REVIEW")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence score between 0.0 and 1.0")
    reason: str = Field(description="Grounded justification for the assigned status")
    requires_human_review: bool = Field(default=False, description="True if officer manual inspection is required")
    contradiction_detected: bool = Field(default=False, description="True if contradictory claims exist across documents")
    deterministic_override: bool = Field(default=False, description="True if a hard deterministic business rule overrode model inference")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or rule breakdown")


# Backwards compatibility alias
class MatchingResult(AIComplianceEvaluation):
    pass


class VerificationExtractionReport(BaseModel):
    tender_id: str
    bidder_id: str
    total_requirements: int
    evaluations: List[AIComplianceEvaluation]
    overall_compliance_score: float = Field(ge=0.0, le=100.0)
    officer_review_recommended: bool
