import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.rbac import Role, UserRole
from app.models.tender import (
    ReviewDecision,
    Tender,
    TenderDocument,
    TenderRequirement,
    TenderRequirementConflict,
    TenderRequirementEvidence,
)
from app.models.user import User
from app.services.requirement_conflict_service import TenderRequirementConflictService
from app.services.requirement_evidence_service import TenderRequirementEvidenceService
from tests_auth_helper import create_test_officer_and_headers

APP_PG_URL = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_phase2_0e_review_workflows_concurrency_rbac_and_preservation():
    await init_db()
    async with AsyncSessionLocal() as db:
        org_a, admin_a, admin_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        _, _, org_b_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        _, _, auditor_headers = await create_test_officer_and_headers(db, role_name="AUDITOR")
        _, _, bidder_headers = await create_test_officer_and_headers(db, role_name="BIDDER")

        # Create a PROCUREMENT_OFFICER in org_a for assignment & decision tests
        role_po = (await db.execute(select(Role).where(Role.name == "PROCUREMENT_OFFICER"))).scalar_one()
        officer_a = User(
            email=f"po-{uuid.uuid4().hex[:8]}@orga.local",
            password_hash=hash_password("TestPass123!"),
            full_name="Officer Alpha",
            organization_id=org_a.id,
            is_active=True,
            is_verified=True,
        )
        db.add(officer_a)
        await db.flush()
        db.add(UserRole(user_id=officer_a.id, role_id=role_po.id, organization_id=org_a.id))
        await db.flush()
        po_token = create_access_token(
            str(officer_a.id),
            str(org_a.id),
            ["PROCUREMENT_OFFICER"],
            ["organization:read", "tender:read", "tender:update", "evaluation:override", "audit:read"],
        )
        po_headers = {"Authorization": f"Bearer {po_token}"}

        tender = Tender(
            organization_id=org_a.id,
            title="Phase 2.0E Human Review Tender",
            total_pages=1,
            extraction_status="READY",
            next_clause_seq={},
        )
        db.add(tender)
        await db.flush()

        doc1 = TenderDocument(
            tender_id=tender.id,
            document_role="PRIMARY_NIT",
            original_filename="nit.pdf",
            storage_path="/tmp/nit.pdf",
            file_size_bytes=50,
            sha256_hash=hashlib.sha256(b"nit").hexdigest(),
            total_pages=1,
            processing_status="READY",
        )
        doc2 = TenderDocument(
            tender_id=tender.id,
            document_role="TECHNICAL_SPEC",
            original_filename="tech.pdf",
            storage_path="/tmp/tech.pdf",
            file_size_bytes=50,
            sha256_hash=hashlib.sha256(b"tech").hexdigest(),
            total_pages=1,
            processing_status="READY",
        )
        db.add_all([doc1, doc2])
        await db.flush()

        req1 = TenderRequirement(
            tender_id=tender.id,
            source_document_id=doc1.id,
            requirement_code="FIN-01",
            extraction_version=1,
            source_page_number=1,
            source_text="Bidder must have minimum annual turnover of INR 500 Lakhs.",
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
        )
        req_changed = TenderRequirement(
            tender_id=tender.id,
            source_document_id=doc2.id,
            requirement_code="TECH-01",
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
            provenance_status="SOURCE_CHANGED",
        )
        db.add_all([req1, req_changed])
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
        # 1. Queue, workload, and RBAC visibility (Phase 2.0E tenderlens-review-queue + Phase 8.4 review-queue)
        q_res = await client.get(f"/api/v1/tenders/{tender.id}/tenderlens-review-queue", headers=po_headers)
        assert q_res.status_code == 200 and q_res.json()["total"] >= 4
        # Phase 8.4 officer review queue must not be shadowed
        p84_res = await client.get(f"/api/v1/tenders/{tender.id}/review-queue", headers=po_headers)
        assert p84_res.status_code == 200 and "total_queued" in p84_res.json()
        wl_res = await client.get(f"/api/v1/tenders/{tender.id}/review-workload", headers=po_headers)
        assert wl_res.status_code == 200 and wl_res.json()["pending_count"] >= 4

        # Cross-tenant & BIDDER denied; AUDITOR cannot mutate
        assert (await client.get(f"/api/v1/tenders/{tender.id}/tenderlens-review-queue", headers=org_b_headers)).status_code in (403, 404)
        assert (await client.get(f"/api/v1/tenders/{tender.id}/tenderlens-review-queue", headers=bidder_headers)).status_code == 403
        assert (
            await client.post(
                f"/api/v1/tenders/{tender.id}/review-decisions",
                json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "decision_type": "CONFIRM", "expected_version": 1},
                headers=auditor_headers,
            )
        ).status_code == 403

        # 2. Assignment RBAC: PO cannot assign (403); ORG_ADMIN assigns to officer_a (200)
        assert (
            await client.post(
                f"/api/v1/tenders/{tender.id}/review-assignments",
                json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "assignee_user_id": str(officer_a.id), "expected_version": 1},
                headers=po_headers,
            )
        ).status_code == 403

        assign_res = await client.post(
            f"/api/v1/tenders/{tender.id}/review-assignments",
            json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "assignee_user_id": str(officer_a.id), "expected_version": 1},
            headers=admin_headers,
        )
        assert assign_res.status_code == 200
        assert assign_res.json()["review_version"] == 2
        assert assign_res.json()["assigned_reviewer_id"] == str(officer_a.id)

        # 3. Validation: empty rationale rejected for REJECT; SOURCE_CHANGED blocks CONFIRM
        assert (
            await client.post(
                f"/api/v1/tenders/{tender.id}/review-decisions",
                json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "decision_type": "REJECT", "expected_version": 2, "rationale": "   "},
                headers=po_headers,
            )
        ).status_code == 422

        assert (
            await client.post(
                f"/api/v1/tenders/{tender.id}/review-decisions",
                json={"object_type": "REQUIREMENT", "object_id": str(req_changed.id), "decision_type": "CONFIRM", "expected_version": 1},
                headers=po_headers,
            )
        ).status_code == 409

        # 4. Optimistic Concurrency: two reviewers submit on v2 -> first succeeds (v3), second gets 409!
        c1 = await client.post(
            f"/api/v1/tenders/{tender.id}/review-decisions",
            json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "decision_type": "CONFIRM", "expected_version": 2, "rationale": "Verified turnover clause"},
            headers=po_headers,
        )
        assert c1.status_code == 200 and c1.json()["new_status"] == "CONFIRMED" and c1.json()["review_version"] == 3

        c_stale = await client.post(
            f"/api/v1/tenders/{tender.id}/review-decisions",
            json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "decision_type": "REJECT", "expected_version": 2, "rationale": "Stale reviewer reject"},
            headers=admin_headers,
        )
        assert c_stale.status_code == 409

        # 5. Reopen CONFIRMED requirement -> NEEDS_REVIEW (v4), history preserved
        reopen_res = await client.post(
            f"/api/v1/tenders/{tender.id}/review-decisions",
            json={"object_type": "REQUIREMENT", "object_id": str(req1.id), "decision_type": "REOPEN", "expected_version": 3, "rationale": "New addendum received"},
            headers=po_headers,
        )
        assert reopen_res.status_code == 200 and reopen_res.json()["new_status"] == "NEEDS_REVIEW"

        # 6. Conflict & Evidence reviews + regeneration preservation
        conf_dec = await client.post(
            f"/api/v1/tenders/{tender.id}/review-decisions",
            json={"object_type": "CONFLICT", "object_id": str(conf_id), "decision_type": "RESOLVE", "expected_version": 1, "rationale": "Officer clarified turnover scope"},
            headers=po_headers,
        )
        assert conf_dec.status_code == 200 and conf_dec.json()["new_status"] == "RESOLVED"

        ev_dec = await client.post(
            f"/api/v1/tenders/{tender.id}/review-decisions",
            json={"object_type": "EVIDENCE", "object_id": str(ev_id), "decision_type": "CONFIRM", "expected_version": 1, "rationale": "CA certificate required"},
            headers=po_headers,
        )
        assert ev_dec.status_code == 200 and ev_dec.json()["new_status"] == "CONFIRMED"

        # Re-run conflict detection & evidence generation -> human decisions preserved!
        await client.post(f"/api/v1/tenders/{tender.id}/detect-conflicts", headers=po_headers)
        await client.post(f"/api/v1/tenders/{tender.id}/requirements/{req1.id}/generate-evidence-mappings", headers=po_headers)

        hist_res = await client.get(f"/api/v1/tenders/{tender.id}/review-history", headers=po_headers)
        assert hist_res.status_code == 200
        # 5 successful mutations (ASSIGN, CONFIRM req1, REOPEN req1, RESOLVE conflict, CONFIRM evidence); stale reject created 0!
        assert hist_res.json()["total"] == 5

    async with AsyncSessionLocal() as db:
        c_row = (await db.execute(select(TenderRequirementConflict).where(TenderRequirementConflict.id == conf_id))).scalar_one()
        e_row = (await db.execute(select(TenderRequirementEvidence).where(TenderRequirementEvidence.id == ev_id))).scalar_one()
        assert c_row.status == "RESOLVED"
        assert e_row.mapping_status == "CONFIRMED"


@pytest.mark.anyio
async def test_phase2_0e_review_history_immutability_and_rls_under_bidguard_app():
    if "sqlite" in settings.DATABASE_URL:
        pytest.skip("PostgreSQL-only RLS and immutability verification")

    engine = create_async_engine(APP_PG_URL, pool_size=1, max_overflow=0)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    t_a, t_b = str(uuid.uuid4()), str(uuid.uuid4())
    d_a, d_b = str(uuid.uuid4()), str(uuid.uuid4())
    obj_a, obj_b = str(uuid.uuid4()), str(uuid.uuid4())

    try:
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for oid in (org_a, org_b):
                slug = f"rls2e-{oid[:8]}"
                await s.execute(text("INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) VALUES (:id, :n, :s, true, now(), now())"), {"id": oid, "n": slug, "s": slug})
            for tid, oid in [(t_a, org_a), (t_b, org_b)]:
                await s.execute(text("INSERT INTO tenders (id, organization_id, title, total_pages, extraction_status, next_clause_seq, created_at, updated_at) VALUES (:id, :oid, 'RLS', 1, 'READY', '{}', now(), now())"), {"id": tid, "oid": oid})
            for did, oid, tid, obid in [(d_a, org_a, t_a, obj_a), (d_b, org_b, t_b, obj_b)]:
                await s.execute(
                    text("INSERT INTO review_decisions (id, organization_id, tender_id, object_type, object_id, decision_type, previous_status, new_status, rationale, object_version, created_at, updated_at) VALUES (:id, :oid, :tid, 'REQUIREMENT', :obid, 'CONFIRM', 'DRAFT', 'CONFIRMED', 'Verified', 2, now(), now())"),
                    {"id": did, "oid": oid, "tid": tid, "obid": obid},
                )
            await s.commit()

        # RLS isolation
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_a})
            assert (await s.execute(text("SELECT id::text FROM review_decisions"))).scalars().all() == [d_a]
            await s.commit()

        # Append-only trigger under bidguard_app
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception) as exc_u:
                await s.execute(text("UPDATE review_decisions SET rationale = 'hack' WHERE id = :id"), {"id": d_a})
                await s.commit()
            assert "append-only" in str(exc_u.value)
            await s.rollback()

        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception) as exc_d:
                await s.execute(text("DELETE FROM review_decisions WHERE id = :id"), {"id": d_a})
                await s.commit()
            assert "append-only" in str(exc_d.value)
            await s.rollback()
    finally:
        await engine.dispose()
