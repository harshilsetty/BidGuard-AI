"""
End-to-End Integration Test: Core Procurement Verification Flow (SIH26100)
Validates the full pipeline:
Tender ➔ Requirements ➔ Bidder ➔ Evidence ➔ Compliance Evaluation ➔ Result

Required Integration Test Cases:
1. PASS case
2. FAIL case
3. REVIEW case
4. Missing evidence case
5. Numeric threshold validation
6. Contradictory evidence detection
"""

import os
import sys
import pytest

# Ensure ai-engine directory is on sys.path
ai_engine_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ai-engine"))
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)

from schemas import ComplianceStatus, AIComplianceEvaluation, EvidenceItem
from matcher.rule_validator import RuleValidator
from matcher.semantic_matcher import SemanticMatcher


@pytest.fixture
def matcher():
    return SemanticMatcher()


@pytest.fixture
def validator():
    return RuleValidator()


# 1. PASS Case: Bidder evidence conclusively satisfies technical criteria
def test_pass_case(matcher):
    req_text = "Bidder must have completed at least 3 government supply orders."
    ev_item = EvidenceItem(
        text="Successfully completed 3 government supply orders for Indian Railways in 2023.",
        document="completion_certificates.pdf",
        page=4
    )

    result = matcher.evaluate_multi_evidence(
        requirement_id="REQ-TECH-01",
        requirement_text=req_text,
        requirement_type="technical",
        evidence_items=[ev_item]
    )

    assert isinstance(result, AIComplianceEvaluation)
    assert result.status == ComplianceStatus.PASS
    assert result.confidence >= 0.75
    assert result.requires_human_review is False
    assert len(result.evidence) == 1
    assert result.evidence[0].page == 4


# 2. FAIL Case: Bidder fails mandatory legal/debarment check
def test_fail_case(matcher):
    req_text = "Bidder must not be debarred or blacklisted by any Government entity."
    ev_item = EvidenceItem(
        text="Self declaration on stamp paper stating no debarment.",
        document="declaration.pdf",
        page=1
    )

    result = matcher.evaluate_multi_evidence(
        requirement_id="REQ-LEGAL-01",
        requirement_text=req_text,
        requirement_type="legal",
        evidence_items=[ev_item],
        deterministic_rules={
            "is_debarred": True,
            "debarment_reason": "Order issued by Ministry of Telecom valid until Dec 2026"
        }
    )

    assert result.status == ComplianceStatus.FAIL
    assert result.deterministic_override is True
    assert "actively debarred" in result.reason
    assert result.confidence == 1.0


# 3. REVIEW Case: Borderline semantic match requiring officer inspection
def test_review_case(matcher):
    req_text = "Bidder must provide Tier-4 datacenter uptime certification."
    ev_item = EvidenceItem(
        text="Data center facilities are managed under standard commercial uptime SLA guidelines.",
        document="sla_annexure.pdf",
        page=12
    )

    result = matcher.evaluate_multi_evidence(
        requirement_id="REQ-TECH-02",
        requirement_text=req_text,
        requirement_type="technical",
        evidence_items=[ev_item]
    )

    assert result.status == ComplianceStatus.REVIEW
    assert result.requires_human_review is True
    assert "Officer manual inspection" in result.reason or "review" in result.reason.lower()


# 4. Missing Evidence Case: Bidder submitted nothing for a mandatory requirement
def test_missing_evidence(matcher):
    req_text = "Bidder must submit audited balance sheet for FY 2023-24."

    result = matcher.evaluate_multi_evidence(
        requirement_id="REQ-FIN-02",
        requirement_text=req_text,
        requirement_type="financial",
        evidence_items=[]  # Zero evidence items
    )

    assert result.status == ComplianceStatus.REVIEW
    assert result.requires_human_review is True
    assert len(result.evidence) == 0
    assert "No supporting evidence" in result.reason


# 5. Numeric Threshold Validation: Strict code-level comparison (₹3.2 Cr vs ₹5.0 Cr)
def test_numeric_threshold(validator, matcher):
    req_text = "Minimum average annual turnover of INR 5.0 crore."
    ev_item = EvidenceItem(
        text="Audited average turnover for last 3 years is INR 3.2 crore.",
        document="ca_certificate.pdf",
        page=2
    )

    # Deterministic Rule Engine Test
    status, reason = validator.validate_turnover(required_amount_lakhs=500.0, presented_amount_lakhs=320.0)
    assert status == ComplianceStatus.FAIL
    assert "below the mandatory threshold" in reason

    # Matcher Evaluation with Rule Injection
    result = matcher.evaluate_multi_evidence(
        requirement_id="REQ-FIN-01",
        requirement_text=req_text,
        requirement_type="financial",
        evidence_items=[ev_item],
        deterministic_rules={"required_turnover": 500.0, "presented_turnover": 320.0}
    )

    assert result.status == ComplianceStatus.FAIL
    assert result.deterministic_override is True
    assert result.confidence == 1.0


# 6. Contradictory Evidence Case: Document A claims 6 yrs exp, Document B proves founded in 2023
def test_contradictory_evidence(matcher):
    req_text = "Bidder must have at least 5 years continuous operational experience."
    ev_a = EvidenceItem(
        text="The company possesses 6 years of proven industry experience.",
        document="technical_overview.pdf",
        page=2
    )
    ev_b = EvidenceItem(
        text="Certificate of Incorporation under Companies Act dated 15 July 2023.",
        document="incorporation_cert.pdf",
        page=1
    )

    result = matcher.evaluate_multi_evidence(
        requirement_id="REQ-EXP-01",
        requirement_text=req_text,
        requirement_type="experience",
        evidence_items=[ev_a, ev_b]
    )

    assert result.status == ComplianceStatus.REVIEW
    assert result.contradiction_detected is True
    assert result.requires_human_review is True
    assert "Conflicting evidence detected" in result.reason
    assert len(result.evidence) == 2
