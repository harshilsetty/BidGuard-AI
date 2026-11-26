import os
import sys
import sqlite3
import pytest
from uuid import UUID

from app.services.scoring_service import ScoringAndRankingService

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BACKEND_DIR, "gem_compliance.db")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_golden_demo_database_exists():
    """Verify the canonical Golden Demo database is present and uncorrupted."""
    assert os.path.exists(DB_PATH), f"Database not found at {DB_PATH}"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, gem_tender_id FROM tenders WHERE gem_tender_id = 'GEM/2026/B/8912450'")
    tender = c.fetchone()
    assert tender is not None, "Golden Demo tender GEM/2026/B/8912450 must exist in baseline database!"
    conn.close()


def test_golden_demo_frozen_clause_counts_and_compliance_rate():
    """
    Verify exact Golden Demo frozen clause evaluation outcomes:
    - EnterpriseTech: 11 PASS, 0 FAIL, 0 REVIEW (100.00% Compliance Rate, QUALIFIED)
    - Legacy Hardware: 1 PASS, 9 FAIL, 1 REVIEW (13.64% Compliance Rate, DISQUALIFIED)
    - Apex Systems: 3 PASS, 5 FAIL, 3 REVIEW (40.91% Compliance Rate, DISQUALIFIED)
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id FROM tenders WHERE gem_tender_id = 'GEM/2026/B/8912450'")
    tender_id = c.fetchone()[0]

    c.execute("""
        SELECT b.id, b.company_name, b.final_status,
               SUM(CASE WHEN ce.status = 'PASS' THEN 1 ELSE 0 END) as pass_cnt,
               SUM(CASE WHEN ce.status = 'FAIL' THEN 1 ELSE 0 END) as fail_cnt,
               SUM(CASE WHEN ce.status = 'REVIEW' THEN 1 ELSE 0 END) as review_cnt,
               COUNT(ce.id) as total_clauses
        FROM bidders b
        JOIN compliance_evaluations ce ON b.id = ce.bidder_id
        JOIN tender_clauses tc ON ce.clause_id = tc.id
        WHERE b.tender_id = ?
        GROUP BY b.id, b.company_name, b.final_status
        ORDER BY b.company_name
    """, (tender_id,))
    bidders = c.fetchall()
    conn.close()

    assert len(bidders) == 3, f"Expected exactly 3 Golden Demo bidders, found {len(bidders)}"

    bidder_map = {b[1]: b for b in bidders}

    # Bidder A: Enterprise Tech Solutions Ltd
    bidder_a = next((b for name, b in bidder_map.items() if "Enterprise" in name), None)
    assert bidder_a is not None
    assert bidder_a[3] == 11, f"EnterpriseTech pass_count expected 11, got {bidder_a[3]}"
    assert bidder_a[4] == 0, f"EnterpriseTech fail_count expected 0, got {bidder_a[4]}"
    assert bidder_a[5] == 0, f"EnterpriseTech review_count expected 0, got {bidder_a[5]}"
    compliance_a = round(((bidder_a[3] + 0.5 * bidder_a[5]) / bidder_a[6]) * 100, 2)
    assert compliance_a == 100.00, f"EnterpriseTech compliance rate expected 100.00%, got {compliance_a}%"
    assert bidder_a[2] == "QUALIFIED"

    # Bidder B: Legacy Hardware Trading Co
    bidder_b = next((b for name, b in bidder_map.items() if "Legacy" in name), None)
    assert bidder_b is not None
    assert bidder_b[3] == 1, f"Legacy Hardware pass_count expected 1, got {bidder_b[3]}"
    assert bidder_b[4] == 9, f"Legacy Hardware fail_count expected 9, got {bidder_b[4]}"
    assert bidder_b[5] == 1, f"Legacy Hardware review_count expected 1 (TECH-02 pending BIS), got {bidder_b[5]}"
    compliance_b = round(((bidder_b[3] + 0.5 * bidder_b[5]) / bidder_b[6]) * 100, 2)
    assert compliance_b == 13.64, f"Legacy Hardware compliance rate expected 13.64%, got {compliance_b}%"
    assert bidder_b[2] == "DISQUALIFIED"

    # Bidder C: Apex System Integrators
    bidder_c = next((b for name, b in bidder_map.items() if "Apex" in name), None)
    assert bidder_c is not None
    assert bidder_c[3] == 3, f"Apex Systems pass_count expected 3, got {bidder_c[3]}"
    assert bidder_c[4] == 5, f"Apex Systems fail_count expected 5, got {bidder_c[4]}"
    assert bidder_c[5] == 3, f"Apex Systems review_count expected 3 (FIN-01, STAT-01, TECH-03), got {bidder_c[5]}"
    compliance_c = round(((bidder_c[3] + 0.5 * bidder_c[5]) / bidder_c[6]) * 100, 2)
    assert compliance_c == 40.91, f"Apex Systems compliance rate expected 40.91%, got {compliance_c}%"
    assert bidder_c[2] == "DISQUALIFIED"


def test_golden_demo_composite_scoring_engine_preservation():
    """
    Verify that the separately defined composite scoring engine produces deterministic
    scores matching the locked architectural baseline.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id, company_name FROM bidders WHERE tender_id IN (SELECT id FROM tenders WHERE gem_tender_id = 'GEM/2026/B/8912450')")
    bidders = c.fetchall()

    for b_id, name in bidders:
        c.execute("""
            SELECT ce.id, tc.clause_code, ce.status, ce.confidence_score, ce.claimed_value,
                   ce.evidence_snippet, ce.reasoning, ce.contradiction_detected, ce.contradiction_details,
                   ce.rule_result, tc.is_mandatory
            FROM compliance_evaluations ce
            JOIN tender_clauses tc ON ce.clause_id = tc.id
            WHERE ce.bidder_id = ?
            ORDER BY tc.clause_code
        """, (b_id,))
        rows = c.fetchall()

        evals = []
        for r in rows:
            evals.append(type("Obj", (), {
                "clause_code": r[1],
                "status": r[2],
                "override_status": None,
                "claimed_value": r[4],
                "evidence_snippet": r[5],
                "reasoning": r[6],
                "contradiction_detected": bool(r[7]),
                "contradiction_details": r[8],
                "rule_result": None,
                "is_mandatory": bool(r[10]),
            }))

        res = ScoringAndRankingService.calculate_bidder_score(
            bidder_id=b_id,
            company_name=name,
            evaluations=evals,
            cross_source_report=None,
        )

        if "Enterprise" in name:
            assert res.overall_score == 100.00
            assert res.risk_level.value == "LOW"
        elif "Legacy" in name:
            assert res.overall_score == 53.41
            assert res.risk_level.value == "HIGH"
        elif "Apex" in name:
            assert res.overall_score == 47.95
            assert res.risk_level.value == "HIGH"
            assert res.summary.major_contradiction_count == 2

    conn.close()


@pytest.mark.anyio
async def test_golden_demo_fused_composite_scoring_preservation():
    """
    Verify that the full fused multi-source pipeline (EvidenceFusionService ->
    CrossSourceVerifier -> ScoringAndRankingService) reproduces the exact
    Phase 0.7 fused composite scores on GEM/2026/B/8912450:
    - EnterpriseTech: 90.45 (LOW)
    - Legacy Hardware: 40.45 (HIGH)
    - Apex Systems: 34.77 (HIGH)
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.tender import Tender
    from app.models.bidder import Bidder
    from app.models.clause import TenderClause
    from app.models.evaluation import ComplianceEvaluation
    from app.services.evidence_fusion_service import EvidenceFusionService
    from app.services.cross_source_verifier import CrossSourceVerifier

    eng = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
    SL = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

    try:
        async with SL() as session:
            t = (await session.execute(select(Tender).where(Tender.gem_tender_id == "GEM/2026/B/8912450"))).scalar_one()
            clauses = (await session.execute(select(TenderClause).where(TenderClause.tender_id == t.id))).scalars().all()
            cmap = {c.clause_code: c.is_mandatory for c in clauses}
            bidders = (await session.execute(select(Bidder).where(Bidder.tender_id == t.id))).scalars().all()

            assert len(bidders) == 3
            for b in bidders:
                evs = (
                    await session.execute(
                        select(ComplianceEvaluation)
                        .where(ComplianceEvaluation.bidder_id == b.id)
                        .options(selectinload(ComplianceEvaluation.clause))
                    )
                ).scalars().all()
                profile = await EvidenceFusionService.fuse_bidder_evidence(b.id, session, t.id, b.company_name)
                cross_report = CrossSourceVerifier.verify_profile(profile)
                score = ScoringAndRankingService.calculate_bidder_score(
                    b.id, b.company_name, evs, cross_report, t.id, cmap
                )

                if "Enterprise" in b.company_name:
                    assert score.overall_score == 90.45
                    assert score.risk_level.value == "LOW"
                elif "Legacy" in b.company_name:
                    assert score.overall_score == 40.45
                    assert score.risk_level.value == "HIGH"
                elif "Apex" in b.company_name:
                    assert score.overall_score == 34.77
                    assert score.risk_level.value == "HIGH"
    finally:
        await eng.dispose()
