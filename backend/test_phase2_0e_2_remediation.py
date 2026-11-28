import asyncio
import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.rbac import Role, UserRole
from app.models.tender import (
    ReviewDecision,
    Tender,
    TenderDocument,
    TenderDocumentPage,
    TenderRequirement,
    TenderRequirementConflict,
    TenderRequirementEvidence,
)
from app.models.user import User
from app.services.requirement_conflict_service import TenderRequirementConflictService
from app.services.requirement_evidence_service import TenderRequirementEvidenceService
from app.services.requirement_provenance_service import TenderRequirementProvenanceService
from tests_auth_helper import create_test_officer_and_headers


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_phase2_0e_2_route_contract_assignment_rbac_and_source_invalidation():
    await init_db()
    async with AsyncSessionLocal() as db:
        org_a, admin_a, admin_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        _, _, org_b_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")

        role_po = (await db.execute(select(Role).where(Role.name == "PROCUREMENT_OFFICER"))).scalar_one()
        role_bidder = (await db.execute(select(Role).where(Role.name == "BIDDER"))).scalar_one()
        role_auditor = (await db.execute(select(Role).where(Role.name == "AUDITOR"))).scalar_one()

        po_user = User(
            email=f"po2e2-{uuid.uuid4().hex[:8]}@orga.local",
            password_hash=hash_password("TestPass123!"),
            full_name="PO Reviewer",
            organization_id=org_a.id,
            is_active=True,
            is_verified=True,
        )
        bidder_user = User(
            email=f"bid2e2-{uuid.uuid4().hex[:8]}@orga.local",
            password_hash=hash_password("TestPass123!"),
            full_name="Bidder User",
            organization_id=org_a.id,
            is_active=True,
            is_verified=True,
        )
        auditor_user = User(
            email=f"aud2e2-{uuid.uuid4().hex[:8]}@orga.local",
            password_hash=hash_password("TestPass123!"),
            full_name="Auditor User",
            organization_id=org_a.id,
            is_active=True,
            is_verified=True,
        )
        db.add_all([po_user, bidder_user, auditor_user])
        await db.flush()
        db.add_all([
            UserRole(user_id=po_user.id, role_id=role_po.id, organization_id=org_a.id),
            UserRole(user_id=bidder_user.id, role_id=role_bidder.id, organization_id=org_a.id),
            UserRole(user_id=auditor_user.id, role_id=role_auditor.id, organization_id=org_a.id),
        ])
        await db.flush()

        po_headers = {
            "Authorization": f"Bearer {create_access_token(str(po_user.id), str(org_a.id), ['PROCUREMENT_OFFICER'], ['tender:read', 'evaluation:override', 'audit:read'])}"
        }

        tender = Tender(
            organization_id=org_a.id,
            title="Phase 2.0E.2 Remediation Tender",
            total_pages=1,
            extraction_status="READY",
            next_clause_seq={},
        )
        db.add(tender)
        await db.flush()

        sha_v1 = hashlib.sha256(b"nit-v1").hexdigest()
        doc1 = TenderDocument(
            tender_id=tender.id,
            document_role="PRIMARY_NIT",
            original_filename="nit.pdf",
            storage_path="/tmp/nit-v1.pdf",
            file_size_bytes=50,
            sha256_hash=sha_v1,
            total_pages=1,
            processing_status="READY",
        )
        doc2 = TenderDocument(
            tender_id=tender.id,
            document_role="TECHNICAL_SPEC",
            original_filename="tech.pdf",
            storage_path="/tmp/tech-v1.pdf",
            file_size_bytes=50,
            sha256_hash=hashlib.sha256(b"tech-v1").hexdigest(),
            total_pages=1,
            processing_status="READY",
        )
        db.add_all([doc1, doc2])
        await db.flush()

        db.add(
            TenderDocumentPage(
                tender_document_id=doc1.id,
                page_number=1,
                extracted_text="Bidder must have minimum annual turnover of INR 500 Lakhs with CA certificate.",
                extraction_method="PYMUPDF",
            )
        )
        req1 = TenderRequirement(
            tender_id=tender.id,
            source_document_id=doc1.id,
            requirement_code="FIN-10",
            extraction_version=1,
            source_page_number=1,
            source_text="Bidder must have minimum annual turnover of INR 500 Lakhs with CA certificate.",
            source_quote_verified=True,
            normalized_statement="Minimum annual turnover INR 500 Lakhs.",
            explanatory_interpretation="Turnover check.",
            primary_category="FIN",
            secondary_categories=[],
            requirement_type="FINANCIAL_THRESHOLD",
            mandatory_status="MANDATORY",
            numeric_value="500",
            unit="Lakhs",
            currency="INR",
            review_status="DRAFT",
            provenance_status="VERIFIED",
            source_document_sha256=sha_v1,
        )
        req2 = TenderRequirement(
            tender_id=tender.id,
            source_document_id=doc2.id,
            requirement_code="TECH-10",
            extraction_version=1,
            source_page_number=1,
            source_text="Minimum turnover 8 Crore INR.",
            source_quote_verified=True,
            normalized_statement="Minimum turnover 8 Crore INR.",
            explanatory_interpretation="Spec turnover.",
            primary_category="FIN",
            secondary_categories=[],
            requirement_type="FINANCIAL_THRESHOLD",
            mandatory_status="MANDATORY",
            numeric_value="8",
            unit="Crore",
            currency="INR",
            review_status="DRAFT",
            provenance_status="VERIFIED",
            source_document_sha256=doc2.sha256_hash,
        )
        db.add_all([req1, req2])
        await db.flush()

        conflicts = await TenderRequirementConflictService().detect_conflicts(db, tender.id)
        assert len(conflicts) == 1
        conf_id = conflicts[0].id
        evs = await TenderRequirementEvidenceService().generate_for_requirement(db, tender.id, req1.id)
        assert len(evs) >= 1
        ev_id = evs[0].id
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # P1-1: Verify both routes resolve to distinct payloads
        p2e_q = await client.get(f"/api/v1/tenders/{tender.id}/tenderlens-review-queue", headers=po_headers)
        assert p2e_q.status_code == 200 and "items" in p2e_q.json() and "total" in p2e_q.json()

        p84_q = await client.get(f"/api/v1/tenders/{tender.id}/review-queue", headers=po_headers)
        assert p84_q.status_code == 200 and "total_queued" in p84_q.json()

        # P2-1: Reject assigning BIDDER or AUDITOR (403); allow PO (200)
        for bad_uid in (bidder_user.id, auditor_user.id):
            bad_assign = await client.post(
                f"/api/v1/tenders/{tender.id}/review-assignments",
                json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "assignee_user_id": str(bad_uid), "expected_version": 1},
                headers=admin_headers,
            )
            assert bad_assign.status_code == 403

        ok_assign = await client.post(
            f"/api/v1/tenders/{tender.id}/review-assignments",
            json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "assignee_user_id": str(po_user.id), "expected_version": 1},
            headers=admin_headers,
        )
        assert ok_assign.status_code == 200 and ok_assign.json()["review_version"] == 2

        # Confirm requirement (v2->v3), conflict (v1->v2), evidence (v1->v2)
        assert (await client.post(f"/api/v1/tenders/{tender.id}/review-decisions", json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "decision_type": "CONFIRM", "expected_version": 2, "rationale": "Confirmed v1"}, headers=po_headers)).status_code == 200
        assert (await client.post(f"/api/v1/tenders/{tender.id}/review-decisions", json={"object_type": "CONFLICT", "object_id": str(conf_id), "decision_type": "DISMISS", "expected_version": 1, "rationale": "Dismissed v1"}, headers=po_headers)).status_code == 200
        assert (await client.post(f"/api/v1/tenders/{tender.id}/review-decisions", json={"object_type": "EVIDENCE", "object_id": str(ev_id), "decision_type": "CONFIRM", "expected_version": 1, "rationale": "Confirmed ev v1"}, headers=po_headers)).status_code == 200

    # P1-2: Mutate doc1 SHA-256 -> verify_and_get_provenance must invalidate req1, conf1, and ev1 to NEEDS_REVIEW
    async with AsyncSessionLocal() as db:
        d1 = (await db.execute(select(TenderDocument).where(TenderDocument.id == doc1.id))).scalar_one()
        d1.sha256_hash = hashlib.sha256(b"nit-v2-corrigendum").hexdigest()
        await db.commit()

        prov = await TenderRequirementProvenanceService().verify_and_get_provenance(db, tender.id, req1.id)
        assert prov["verification_status"] == "SOURCE_CHANGED"
        await db.commit()

        # Re-running verify_and_get_provenance again must be idempotent (no duplicate SOURCE_INVALIDATED rows)
        await TenderRequirementProvenanceService().verify_and_get_provenance(db, tender.id, req1.id)
        await db.commit()

        r1_after = (await db.execute(select(TenderRequirement).where(TenderRequirement.id == req1.id))).scalar_one()
        c1_after = (await db.execute(select(TenderRequirementConflict).where(TenderRequirementConflict.id == conf_id))).scalar_one()
        e1_after = (await db.execute(select(TenderRequirementEvidence).where(TenderRequirementEvidence.id == ev_id))).scalar_one()

        assert r1_after.review_status == "NEEDS_REVIEW" and r1_after.review_version == 4
        assert c1_after.status == "NEEDS_REVIEW" and c1_after.review_version == 3
        assert e1_after.mapping_status == "NEEDS_REVIEW" and e1_after.review_version == 3

        # Historical decisions preserved + exactly 1 SOURCE_INVALIDATED per object
        req_hist = (
            await db.execute(
                select(ReviewDecision).where(ReviewDecision.object_id == req1.id).order_by(ReviewDecision.created_at.asc())
            )
        ).scalars().all()
        assert [h.decision_type for h in req_hist] == ["ASSIGN", "CONFIRM", "SOURCE_INVALIDATED"]
