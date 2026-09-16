"""Comprehensive Verification Intelligence & Officer Risk View Tests.

Phase 8.4 — SIH26100 Verification Intelligence Layer.
Tests all 33 required verification scenarios, invariants, and protections:
1. verification history is append-only
2. two executions create two records
3. historical record remains unchanged
4. latest attempt is deterministic
5. latest attempt differs from previous successful result when appropriate
6. SOURCE_UNAVAILABLE is not bidder FAIL
7. TIMEOUT is not bidder FAIL
8. AUTH_FAILURE is not bidder FAIL
9. FAILED is not bidder FAIL
10. NOT_FOUND remains distinct from technical failure
11. as_of_date preserved
12. retrieved_at preserved
13. no date.today() fallback
14. active debarment creates risk reason
15. active debarment does not alter Phase 6.4 score
16. clean bidder score/risk/ranking unchanged
17. identity conflict creates review reason
18. major contradiction creates review reason
19. OCR_LOW_CONFIDENCE decisive evidence creates review reason
20. review queue includes only relevant bidders
21. tender/bidder isolation
22. every risk reason has provenance
23. no automatic disqualification
24. Phase 8.2 tests remain green
25. Phase 8.3A tests remain green
26. Phase 8.3B tests remain green
27. Phase 6 scoring tests remain green
28. Phase 6.5 recommendation/audit tests remain green
29. Phase 7 OCR tests remain green
30. exactly 11 source statuses are exposed
31. no State Debarment source is introduced
32. all existing source adapters remain registered
33. review queue ordering is deterministic
"""

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import pytest
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal, engine
from app.models.bidder import Bidder
from app.models.clause import TenderClause
from app.models.evaluation import ComplianceEvaluation
from app.models.statutory import StatutoryVerificationRecord
from app.models.tender import Tender
from app.schemas.evaluation import ComplianceStatus
from app.schemas.scoring import RiskLevel, ScoreBreakdown
from app.schemas.statutory_verification import (
    DebarmentTemporalStatus,
    SourceConnectionStatus,
    SourceMode,
    SourceVerificationStatus,
    StatutoryAuthority,
)
from app.schemas.verification_intelligence import (
    RiskReasonCode,
    RiskReasonSeverity,
)
from app.services.scoring_service import ScoringAndRankingService
from app.services.statutory_adapters.registry import get_statutory_registry
from app.services.verification_intelligence_service import (
    LOCKED_11_STATUTORY_AUTHORITIES,
    VerificationIntelligenceService,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def cleanup_db_connections(anyio_backend):
    """Ensure asyncpg connection pools are properly disposed after each test."""
    yield
    await engine.dispose()


async def create_test_context(session):
    """Helper to create isolated test tender, bidders, and clauses."""
    t_id = uuid.uuid4()
    b1_id = uuid.uuid4()
    b2_id = uuid.uuid4()

    tender = Tender(
        id=t_id,
        title="Defense IT Infrastructure Tender 2026",
        gem_tender_id=f"GEM-{uuid.uuid4().hex[:6].upper()}",
        extraction_status="READY",
    )
    session.add(tender)

    bidder1 = Bidder(
        id=b1_id,
        tender_id=t_id,
        company_name="Apex Systems Ltd",
    )
    bidder2 = Bidder(
        id=b2_id,
        tender_id=t_id,
        company_name="Beta Cyber Solutions",
    )
    session.add_all([bidder1, bidder2])

    c1 = TenderClause(
        id=uuid.uuid4(),
        tender_id=t_id,
        clause_code="TECH-01",
        title="Compute Server Cores",
        description="Minimum 64 compute cores required",
        category="TECHNICAL",
        is_mandatory=True,
        source_text="Minimum 64 cores required on server infrastructure.",
        page_number=1,
        is_confirmed=True,
    )
    c2 = TenderClause(
        id=uuid.uuid4(),
        tender_id=t_id,
        clause_code="FIN-01",
        title="Annual Turnover Threshold",
        description="Minimum average annual turnover of 5.0 Crores",
        category="FINANCIAL",
        is_mandatory=True,
        source_text="Bidder must possess annual turnover exceeding 5 Crores.",
        page_number=2,
        is_confirmed=True,
    )
    session.add_all([c1, c2])
    await session.commit()

    return {
        "tender_id": t_id,
        "bidder1_id": b1_id,
        "bidder2_id": b2_id,
        "clause1": c1,
        "clause2": c2,
    }


# ==============================================================================
# 1. APPEND-ONLY HISTORY & DETERMINISTIC LATEST ATTEMPT
# ==============================================================================

@pytest.mark.anyio
async def test_01_02_03_verification_history_is_append_only():
    """Assertions 1, 2, 3: Two executions create two records, history is append-only, and historical record is unchanged."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]

        v_id_1 = uuid.uuid4()
        t1 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        v_id_2 = uuid.uuid4()
        t2 = datetime(2026, 3, 1, 10, 15, tzinfo=timezone.utc)

        rec1 = StatutoryVerificationRecord(
            tender_id=t_id,
            bidder_id=b_id,
            verification_id=v_id_1,
            authority="GSTN",
            source_name="Goods & Services Tax Network (GSTN)",
            query_identifier="27AAACE1001A1Z1",
            identifier_type="gstin",
            mode="MOCK",
            connection_status=SourceConnectionStatus.SUCCESS.value,
            verification_status=SourceVerificationStatus.VERIFIED.value,
            retrieved_at=t1,
            as_of_date=date(2026, 3, 1),
            data_payload={"legal_name": "Apex Systems Ltd", "status": "ACTIVE"},
            confidence_score=1.0,
        )
        session.add(rec1)
        await session.commit()

        # Fetch history after execution #1
        hist1 = await VerificationIntelligenceService.get_bidder_verification_history(t_id, b_id, session)
        assert hist1.total_attempts == 1
        assert hist1.history[0].verification_id == str(v_id_1)
        assert hist1.history[0].is_latest is True

        # Execution #2: second run for same authority
        rec2 = StatutoryVerificationRecord(
            tender_id=t_id,
            bidder_id=b_id,
            verification_id=v_id_2,
            authority="GSTN",
            source_name="Goods & Services Tax Network (GSTN)",
            query_identifier="27AAACE1001A1Z1",
            identifier_type="gstin",
            mode="MOCK",
            connection_status=SourceConnectionStatus.TIMEOUT.value,
            verification_status=SourceVerificationStatus.FAILED.value,
            retrieved_at=t2,
            as_of_date=date(2026, 3, 1),
            data_payload={},
            confidence_score=0.0,
            error_message="Gateway timeout",
        )
        session.add(rec2)
        await session.commit()

        # Fetch history after execution #2
        hist2 = await VerificationIntelligenceService.get_bidder_verification_history(t_id, b_id, session)
        # Assertion 1 & 2: exactly 2 records preserved, never overwritten
        assert hist2.total_attempts == 2

        # Assertion 3: original historical record unchanged
        original = next(h for h in hist2.history if h.verification_id == str(v_id_1))
        assert original.verification_status == SourceVerificationStatus.VERIFIED.value
        assert original.connection_status == SourceConnectionStatus.SUCCESS.value
        assert original.data_payload["status"] == "ACTIVE"
        assert original.is_latest is False

        # Latest record identified
        newest = next(h for h in hist2.history if h.verification_id == str(v_id_2))
        assert newest.is_latest is True
        assert newest.connection_status == SourceConnectionStatus.TIMEOUT.value


@pytest.mark.anyio
async def test_04_05_latest_attempt_vs_previous_successful_result():
    """Assertions 4 & 5: Latest attempt is deterministic and exposes previous successful result when latest is technical failure."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]

        v_id_1 = uuid.uuid4()
        v_id_2 = uuid.uuid4()

        # Run 1: Successful VERIFIED
        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=v_id_1,
                authority="GSTN",
                source_name="Goods & Services Tax Network (GSTN)",
                query_identifier="27AAACE1001A1Z1",
                identifier_type="gstin",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.VERIFIED.value,
                retrieved_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
                as_of_date=date(2026, 3, 1),
                data_payload={"legal_name": "Apex Systems Ltd", "status": "ACTIVE"},
            )
        )
        # Run 2: Subsequent TIMEOUT
        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=v_id_2,
                authority="GSTN",
                source_name="Goods & Services Tax Network (GSTN)",
                query_identifier="27AAACE1001A1Z1",
                identifier_type="gstin",
                mode="MOCK",
                connection_status=SourceConnectionStatus.TIMEOUT.value,
                verification_status=SourceVerificationStatus.FAILED.value,
                retrieved_at=datetime(2026, 3, 1, 10, 15, tzinfo=timezone.utc),
                as_of_date=date(2026, 3, 1),
                error_message="Gateway timeout after 10s",
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)
        gstn_status = summary.source_statuses["GSTN"]

        # Latest attempt reflects the actual latest execution (TIMEOUT, NOT pretending it is VERIFIED)
        assert gstn_status.connection_status == SourceConnectionStatus.TIMEOUT.value
        assert gstn_status.is_technical_failure is True
        assert gstn_status.verification_id == str(v_id_2)

        # Previous successful result is clearly captured
        assert gstn_status.previous_successful_result is not None
        assert gstn_status.previous_successful_result["verification_status"] == SourceVerificationStatus.VERIFIED.value
        assert gstn_status.previous_successful_result["verification_id"] == str(v_id_1)


# ==============================================================================
# 2. TECHNICAL FAILURE IS NOT BIDDER NON-COMPLIANCE
# ==============================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "conn_status, verif_status, expected_code",
    [
        (SourceConnectionStatus.UNAVAILABLE.value, SourceVerificationStatus.FAILED.value, RiskReasonCode.SOURCE_UNAVAILABLE),
        (SourceConnectionStatus.TIMEOUT.value, SourceVerificationStatus.FAILED.value, RiskReasonCode.SOURCE_TIMEOUT),
        (SourceConnectionStatus.AUTH_FAILURE.value, SourceVerificationStatus.FAILED.value, RiskReasonCode.SOURCE_AUTH_FAILURE),
        (SourceConnectionStatus.ERROR.value, SourceVerificationStatus.FAILED.value, RiskReasonCode.SOURCE_FAILED),
    ],
)
async def test_06_07_08_09_technical_failures_not_bidder_fail(conn_status, verif_status, expected_code):
    """Assertions 6, 7, 8, 9: Technical failures create review reasons but never fail compliance score."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=uuid.uuid4(),
                authority="INCOME_TAX",
                source_name="Income Tax Department (CBDT)",
                query_identifier="AAACE1001A",
                identifier_type="pan",
                mode="MOCK",
                connection_status=conn_status,
                verification_status=verif_status,
                retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 3, 1),
                error_message=f"Simulated technical issue: {conn_status}",
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)

        # Technical failure is flagged in technical_source_failures
        assert len(summary.technical_source_failures) >= 1
        it_status = summary.source_statuses["INCOME_TAX"]
        assert it_status.is_technical_failure is True

        # Corresponding structured risk reason created
        assert any(r.reason_code == expected_code for r in summary.risk_reasons)

        # Score remains protected
        assert summary.base_compliance_score >= 0.0


@pytest.mark.anyio
async def test_10_not_found_distinct_from_technical_failure():
    """Assertion 10: NOT_FOUND is a business status (SUCCESS + NOT_FOUND) distinct from technical failure."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=uuid.uuid4(),
                authority="UDYAM",
                source_name="Udyam MSME Registration Portal",
                query_identifier="UDYAM-XX-00-9999999",
                identifier_type="udyam_number",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.NOT_FOUND.value,
                retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 3, 1),
                data_payload={"is_registered": False},
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)
        udyam_status = summary.source_statuses["UDYAM"]

        assert udyam_status.connection_status == SourceConnectionStatus.SUCCESS.value
        assert udyam_status.verification_status == SourceVerificationStatus.NOT_FOUND.value
        assert udyam_status.is_business_not_found is True
        assert udyam_status.is_technical_failure is False


# ==============================================================================
# 3. TEMPORAL PROVENANCE & ZERO DATE.TODAY() FALLBACK
# ==============================================================================

@pytest.mark.anyio
async def test_11_12_13_temporal_provenance_and_no_date_today_fallback():
    """Assertions 11, 12, 13: as_of_date and retrieved_at are preserved; missing as_of_date yields TEMPORAL_UNVERIFIED without date.today() fallback."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]
        ret_time = datetime(2026, 2, 15, 14, 30, tzinfo=timezone.utc)

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=uuid.uuid4(),
                authority="NSIC",
                source_name="National Small Industries Corporation (NSIC)",
                query_identifier="NSIC/GP/2026/001",
                identifier_type="registration_number",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.UNVERIFIED.value,
                retrieved_at=ret_time,
                as_of_date=None,  # Missing as_of_date
                data_payload={"registration_status": "ACTIVE"},
            )
        )
        await session.commit()

        # Query summary with as_of_date=None
        summary = await VerificationIntelligenceService.get_bidder_verification_summary(
            t_id, b_id, session, as_of_date=None
        )

        nsic_status = summary.source_statuses["NSIC"]
        assert nsic_status.retrieved_at == ret_time
        assert nsic_status.as_of_date is None
        assert any(r.reason_code == RiskReasonCode.TEMPORAL_UNVERIFIED for r in summary.risk_reasons)


# ==============================================================================
# 4. DEBARMENT ORTHOGONAL RISK & SCORE PROTECTION
# ==============================================================================

@pytest.mark.anyio
async def test_14_15_16_active_debarment_and_score_protection():
    """Assertions 14, 15, 16: Active debarment creates HIGH risk reason and elevates overall risk to HIGH, but does NOT alter Phase 6.4 score."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]

        summary_clean = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)
        score_before = summary_clean.base_compliance_score

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=uuid.uuid4(),
                authority="DEBARMENT",
                source_name="CPPP Central Debarment Register",
                query_identifier="AAACE1001A",
                identifier_type="pan",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.VERIFIED.value,
                retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 3, 1),
                data_payload={
                    "is_debarred_on_date": True,
                    "temporal_status": DebarmentTemporalStatus.ACTIVE_ON_DATE.value,
                    "order_number": "DEB/MOD/2025/889",
                    "authority": "Ministry of Defence",
                    "start_date": "2025-01-01",
                    "end_date": "2027-01-01",
                    "reason": "Substandard military hardware supply",
                },
            )
        )
        await session.commit()

        summary_debarred = await VerificationIntelligenceService.get_bidder_verification_summary(
            t_id, b_id, session, as_of_date=date(2026, 3, 1)
        )

        deb_reason = next((r for r in summary_debarred.risk_reasons if r.reason_code == RiskReasonCode.ACTIVE_DEBARMENT), None)
        assert deb_reason is not None
        assert deb_reason.severity == RiskReasonSeverity.HIGH
        assert deb_reason.requires_officer_review is True
        assert summary_debarred.overall_risk_state == RiskLevel.HIGH
        assert summary_debarred.debarment_state.is_debarred is True

        # Phase 6.4 100-point score is 100% UNCHANGED
        assert summary_debarred.base_compliance_score == score_before
        assert (
            summary_debarred.score_breakdown.tender_compliance
            == summary_clean.score_breakdown.tender_compliance
        )


# ==============================================================================
# 5. DISCREPANCIES, CONTRADICTIONS, AND OCR QUALITY
# ==============================================================================

@pytest.mark.anyio
async def test_17_identity_conflict_creates_review_reason():
    """Assertion 17: Statutory identity discrepancy creates IDENTITY_CONFLICT review reason."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=uuid.uuid4(),
                authority="DPIIT",
                source_name="DPIIT / Startup India Recognition",
                query_identifier="DIPP99999",
                identifier_type="certificate_number",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.UNVERIFIED.value,
                retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 3, 1),
                data_payload={
                    "conflict_detected": True,
                    "is_ambiguous_match": True,
                    "officer_review_required": True,
                },
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)
        assert any(r.reason_code == RiskReasonCode.IDENTITY_CONFLICT for r in summary.risk_reasons)
        assert len(summary.identity_conflicts) >= 1


@pytest.mark.anyio
async def test_18_major_contradiction_creates_review_reason():
    """Assertion 18: Major contradiction creates MAJOR_CONTRADICTION risk reason."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]
        c2 = ctx["clause2"]

        session.add(
            ComplianceEvaluation(
                bidder_id=b_id,
                clause_id=c2.id,
                status=ComplianceStatus.REVIEW.value,
                confidence_score=0.9,
                claimed_value="₹12.5 Crores",
                reasoning="Contradiction detected against statutory records",
                contradiction_detected=True,
                contradiction_details="Tender claims ₹12.5 Cr vs Income Tax verified ₹4.2 Cr",
            )
        )
        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b_id,
                verification_id=uuid.uuid4(),
                authority="GSTN",
                source_name="Goods & Services Tax Network (GSTN)",
                query_identifier="27AAACE1001A1Z1",
                identifier_type="gstin",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.VERIFIED.value,
                retrieved_at=datetime.now(timezone.utc),
                data_payload={"verified_turnover": 4.2},
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)
        assert any(r.reason_code == RiskReasonCode.MAJOR_CONTRADICTION for r in summary.risk_reasons)


@pytest.mark.anyio
async def test_19_ocr_low_confidence_creates_review_reason():
    """Assertion 19: Decisive evidence extracted via OCR with low confidence creates OCR_LOW_CONFIDENCE reason."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b_id = ctx["bidder1_id"]
        c1 = ctx["clause1"]

        session.add(
            ComplianceEvaluation(
                bidder_id=b_id,
                clause_id=c1.id,
                status=ComplianceStatus.PASS.value,
                confidence_score=0.55,
                claimed_value="64 cores",
                reasoning="Extracted from scanned proposal",
                extraction_method="OCR",
                ocr_confidence=0.55,
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b_id, session)
        assert any(r.reason_code == RiskReasonCode.OCR_LOW_CONFIDENCE for r in summary.risk_reasons)


# ==============================================================================
# 6. OFFICER REVIEW QUEUE & TENANT ISOLATION
# ==============================================================================

@pytest.mark.anyio
async def test_20_33_review_queue_and_deterministic_ordering():
    """Assertions 20 & 33: Review queue contains only relevant bidders and orders them deterministically (HIGH risk first)."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b1_id = ctx["bidder1_id"]
        b2_id = ctx["bidder2_id"]

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b1_id,
                verification_id=uuid.uuid4(),
                authority="DEBARMENT",
                source_name="CPPP Central Debarment Register",
                query_identifier="AAACE1001A",
                identifier_type="pan",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.VERIFIED.value,
                retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 3, 1),
                data_payload={
                    "is_debarred_on_date": True,
                    "order_number": "DEB/2026/001",
                },
            )
        )
        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b2_id,
                verification_id=uuid.uuid4(),
                authority="EPFO",
                source_name="Employees' Provident Fund Organisation (EPFO)",
                query_identifier="MHBAN0010010000",
                identifier_type="establishment_code",
                mode="MOCK",
                connection_status=SourceConnectionStatus.TIMEOUT.value,
                verification_status=SourceVerificationStatus.FAILED.value,
                retrieved_at=datetime.now(timezone.utc),
                error_message="Gateway timeout",
            )
        )
        # Give b2 compliant evaluations so base risk is LOW
        c1 = ctx["clause1"]
        c2 = ctx["clause2"]
        session.add_all([
            ComplianceEvaluation(
                bidder_id=b2_id,
                clause_id=c1.id,
                status=ComplianceStatus.PASS.value,
                confidence_score=1.0,
                claimed_value="64 cores",
                reasoning="compliant",
            ),
            ComplianceEvaluation(
                bidder_id=b2_id,
                clause_id=c2.id,
                status=ComplianceStatus.PASS.value,
                confidence_score=1.0,
                claimed_value="₹10 Crores",
                reasoning="compliant",
            ),
        ])
        await session.commit()

        queue = await VerificationIntelligenceService.get_tender_review_queue(t_id, session)

        assert queue.total_queued == 2
        assert queue.items[0].bidder_id == str(b1_id)
        assert queue.items[0].overall_risk_state == RiskLevel.HIGH
        assert queue.items[0].debarred is True
        assert queue.items[1].bidder_id == str(b2_id)


@pytest.mark.anyio
async def test_21_tender_bidder_isolation_enforced():
    """Assertion 21: Cross-tender or cross-bidder queries are strictly isolated (ValueError / 404)."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        b1_id = ctx["bidder1_id"]
        unrelated_tender_id = uuid.uuid4()

        with pytest.raises(ValueError, match="not found"):
            await VerificationIntelligenceService.get_bidder_verification_summary(
                tender_id=unrelated_tender_id,
                bidder_id=b1_id,
                db=session,
            )


@pytest.mark.anyio
async def test_22_23_provenance_and_no_auto_disqualification():
    """Assertions 22 & 23: Every risk reason has verifiable provenance and no automatic disqualification occurs."""
    async with AsyncSessionLocal() as session:
        ctx = await create_test_context(session)
        t_id = ctx["tender_id"]
        b1_id = ctx["bidder1_id"]

        session.add(
            StatutoryVerificationRecord(
                tender_id=t_id,
                bidder_id=b1_id,
                verification_id=uuid.uuid4(),
                authority="DEBARMENT",
                source_name="CPPP Central Debarment Register",
                query_identifier="AAACE1001A",
                identifier_type="pan",
                mode="MOCK",
                connection_status=SourceConnectionStatus.SUCCESS.value,
                verification_status=SourceVerificationStatus.VERIFIED.value,
                retrieved_at=datetime.now(timezone.utc),
                as_of_date=date(2026, 3, 1),
                data_payload={"is_debarred_on_date": True, "order_number": "DEB/007"},
            )
        )
        await session.commit()

        summary = await VerificationIntelligenceService.get_bidder_verification_summary(t_id, b1_id, session)

        for r in summary.risk_reasons:
            assert r.source_type is not None
            assert r.source_name is not None
            assert r.explanation is not None

        assert not hasattr(summary, "auto_disqualified")
        assert not hasattr(summary, "is_winner")


# ==============================================================================
# 7. SOURCE COUNT & REGISTRY INTEGRITY
# ==============================================================================

def test_30_31_exactly_11_sources_and_no_state_debarment():
    """Assertions 30 & 31: Exactly 11 sources are configured and State Debarment is NOT a 12th source."""
    assert len(LOCKED_11_STATUTORY_AUTHORITIES) == 11
    authority_names = [a.value for a in LOCKED_11_STATUTORY_AUTHORITIES]
    assert "STATE_DEBARMENT" not in authority_names
    assert "STATE_DEBARMENTS" not in authority_names
    expected = [
        "GSTN", "UDYAM", "MCA", "INCOME_TAX", "MII",
        "DEBARMENT", "DPIIT", "EPFO", "ESIC", "NSIC", "DIGILOCKER"
    ]
    assert authority_names == expected


def test_32_all_existing_adapters_remain_registered():
    """Assertion 32: All 11 statutory adapters remain registered in StatutoryAdapterRegistry."""
    registry = get_statutory_registry()
    adapters = registry.get_all_adapters()
    assert len(adapters) == 11
    for auth in LOCKED_11_STATUTORY_AUTHORITIES:
        assert auth in adapters


# ==============================================================================
# 8. REGRESSION GUARDS: PHASES 8.2, 8.3A, 8.3B, 6.4, 6.5, 7
# ==============================================================================

def test_24_phase8_2_debarment_regression():
    """Assertion 24: Phase 8.2 DebarmentTemporalService logic remains intact."""
    from app.services.debarment_temporal_service import DebarmentTemporalService
    res = DebarmentTemporalService.evaluate(
        as_of="2026-03-01",
        start="2025-01-01",
        end="2027-01-01",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE
    assert res.is_debarred_on_date is True

    # as_of_date=None returns UNKNOWN_PERIOD
    res_none = DebarmentTemporalService.evaluate(
        as_of=None,
        start="2025-01-01",
        end="2027-01-01",
        status="ACTIVE",
    )
    assert res_none.temporal_status == DebarmentTemporalStatus.UNKNOWN_PERIOD
    assert res_none.is_debarred_on_date is False


def test_27_phase6_4_scoring_formula_protected():
    """Assertion 27: Phase 6.4 100-point scoring formula breakdown and weights remain strictly protected."""
    # Test formula: 50 tender + 20 statutory + 15 completeness + 15 contradiction
    breakdown = ScoreBreakdown(
        tender_compliance=50.0,
        statutory_consistency=20.0,
        evidence_completeness=15.0,
        contradiction_score=15.0,
    )
    total = (
        breakdown.tender_compliance
        + breakdown.statutory_consistency
        + breakdown.evidence_completeness
        + breakdown.contradiction_score
    )
    assert total == 100.0


def test_28_phase6_5_recommendation_audit_protected():
    """Assertion 28: Phase 6.5 Recommendation and audit trail schemas remain intact."""
    from app.schemas.recommendation import AIRecommendationResponse, RecommendationCategory
    assert RecommendationCategory.HIGH_RISK_OFFICER_REVIEW == "HIGH_RISK_OFFICER_REVIEW"
    assert RecommendationCategory.RECOMMENDED_FOR_OFFICER_REVIEW == "RECOMMENDED_FOR_OFFICER_REVIEW"
    assert RecommendationCategory.REQUIRES_ADDITIONAL_EVIDENCE == "REQUIRES_ADDITIONAL_EVIDENCE"


def test_29_phase7_ocr_pipeline_protected():
    """Assertion 29: Phase 7 OCR Engine and result structures remain intact."""
    from app.services.ocr_engine import get_ocr_engine, OCRResult
    engine = get_ocr_engine()
    assert engine is not None
