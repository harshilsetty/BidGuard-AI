import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.main import app
from app.models.audit import AuditLog
from app.models.tender import (
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

APP_PG_URL = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_phase2_0d_2_audit_immutability_under_bidguard_app():
    if "sqlite" in settings.DATABASE_URL:
        pytest.skip("PostgreSQL-only audit immutability verification")

    engine = create_async_engine(APP_PG_URL, pool_size=1, max_overflow=0)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    org_id, user_id, audit_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    slug = f"audimm-{org_id[:8]}"
    email = f"actor-{user_id[:8]}@test.local"

    try:
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            await s.execute(
                text("INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) VALUES (:id, :n, :s, true, now(), now())"),
                {"id": org_id, "n": slug, "s": slug},
            )
            await s.execute(
                text("INSERT INTO users (id, email, password_hash, full_name, organization_id, is_active, is_verified, created_at, updated_at) VALUES (:id, :e, 'hash', 'Actor', :oid, true, true, now(), now())"),
                {"id": user_id, "e": email, "oid": org_id},
            )
            await s.execute(
                text("INSERT INTO audit_logs (id, timestamp, organization_id, user_id, action, target_type, target_id, diff_json, created_at, updated_at) VALUES (:id, now(), :oid, :uid, 'TEST_ACTION', 'User', :tid, '{\"k\":\"v\"}', now(), now())"),
                {"id": audit_id, "oid": org_id, "uid": user_id, "tid": str(user_id)},
            )
            await s.commit()

        # 1. Direct UPDATE rejected under bidguard_app
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception) as exc_upd:
                await s.execute(text("UPDATE audit_logs SET action = 'TAMPERED' WHERE id = :id"), {"id": audit_id})
                await s.commit()
            assert "append-only" in str(exc_upd.value)
            await s.rollback()

        # 2. Direct DELETE rejected under bidguard_app
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception) as exc_del:
                await s.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": audit_id})
                await s.commit()
            assert "append-only" in str(exc_del.value)
            await s.rollback()

        # 3. Indirect UPDATE via DELETE FROM users (ON DELETE SET NULL) rejected
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception) as exc_user:
                await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
                await s.commit()
            assert "append-only" in str(exc_user.value)
            await s.rollback()

        # 4. Verify historical audit record remains unchanged
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            row = (await s.execute(text("SELECT action, user_id::text FROM audit_logs WHERE id = :id"), {"id": audit_id})).one()
            assert row == ("TEST_ACTION", user_id)
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_phase2_0d_2_member_removal_preserves_audit_and_access_controls():
    await init_db()
    async with AsyncSessionLocal() as db:
        from app.core.security import create_access_token, hash_password
        from app.models.rbac import Role, UserRole
        org_a, admin_a, admin_headers = await create_test_officer_and_headers(db, role_name="ORG_ADMIN")
        role_po = (await db.execute(select(Role).where(Role.name == "PROCUREMENT_OFFICER"))).scalar_one()
        member_a = User(
            email=f"member-{uuid.uuid4().hex[:8]}@test.local",
            password_hash=hash_password("TestPass123!"),
            full_name="Member Alpha",
            organization_id=org_a.id,
            is_active=True,
            is_verified=True,
        )
        db.add(member_a)
        await db.flush()
        db.add(UserRole(user_id=member_a.id, role_id=role_po.id, organization_id=org_a.id))
        await db.flush()
        token = create_access_token(
            str(member_a.id),
            str(org_a.id),
            ["PROCUREMENT_OFFICER"],
            [],
        )
        member_headers = {"Authorization": f"Bearer {token}"}
        # Create an audit log attributed to member_a prior to removal
        audit_row = AuditLog(
            organization_id=org_a.id,
            user_id=member_a.id,
            action="TENDER_VIEWED",
            target_type="Tender",
            target_id="00000000-0000-0000-0000-000000000001",
            diff_json={"note": "pre-removal"},
        )
        db.add(audit_row)
        await db.commit()
        audit_id = audit_row.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Remove member_a
        rem1 = await client.delete(f"/api/v1/organizations/me/members/{member_a.id}", headers=admin_headers)
        assert rem1.status_code == 200

        # Repeated removal behaves safely
        rem2 = await client.delete(f"/api/v1/organizations/me/members/{member_a.id}", headers=admin_headers)
        assert rem2.status_code == 200

        # Removed member loses access immediately
        me_res = await client.get("/api/v1/auth/me", headers=member_headers)
        assert me_res.status_code in (401, 403)

    # Historical audit record retains exact actor attribution
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        saved_audit = (await db.execute(select(AuditLog).where(AuditLog.id == audit_id))).scalar_one()
        assert saved_audit.user_id == member_a.id
        assert saved_audit.action == "TENDER_VIEWED"
        u_row = (await db.execute(select(User).where(User.id == member_a.id))).scalar_one()
        assert u_row.is_active is False


@pytest.mark.anyio
async def test_phase2_0d_2_human_decision_preservation_and_needs_review():
    await init_db()
    async with AsyncSessionLocal() as db:
        org_a, _, _ = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
        tender = Tender(
            organization_id=org_a.id,
            title="2.0D.2 Preservation Tender",
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
            sha256_hash=hashlib.sha256(b"nit-v1").hexdigest(),
            total_pages=1,
            processing_status="READY",
        )
        doc2 = TenderDocument(
            tender_id=tender.id,
            document_role="TECHNICAL_SPEC",
            original_filename="tech.pdf",
            storage_path="/tmp/tech.pdf",
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
                extracted_text="Bidder must submit valid ISO 9001 certificate and minimum annual turnover 500 Lakhs.",
                word_count=12,
                extraction_method="DIGITAL_TEXT",
                extraction_status="SUCCEEDED",
            )
        )

        # Ungrounded requirement -> NEEDS_REVIEW evidence mapping
        req_needs_review = TenderRequirement(
            tender_id=tender.id,
            source_document_id=doc1.id,
            requirement_code="TECH-01",
            extraction_version=1,
            source_page_number=1,
            source_text="Bidder must submit valid ISO 9001 certificate and minimum annual turnover 500 Lakhs.",
            source_quote_verified=False,  # Forces NEEDS_REVIEW on evidence mapping
            normalized_statement="Submit ISO 9001 certificate.",
            explanatory_interpretation="ISO 9001 certification.",
            primary_category="TECH",
            secondary_categories=[],
            requirement_type="CERTIFICATION",
            mandatory_status="MANDATORY",
            numeric_value="500",
            unit="Lakhs",
            currency="INR",
            review_status="DRAFT",
            provenance_status="VERIFIED",
            source_document_sha256=doc1.sha256_hash,
        )
        req_conflict_b = TenderRequirement(
            tender_id=tender.id,
            source_document_id=doc2.id,
            requirement_code="TECH-02",
            extraction_version=1,
            source_page_number=1,
            source_text="Minimum turnover 8 Crore INR.",
            source_quote_verified=True,
            normalized_statement="Minimum turnover 8 Crore INR.",
            explanatory_interpretation="Turnover mismatch.",
            primary_category="TECH",
            secondary_categories=[],
            requirement_type="CERTIFICATION",
            mandatory_status="MANDATORY",
            numeric_value="8",
            unit="Crore",
            currency="INR",
            review_status="DRAFT",
        )
        db.add_all([req_needs_review, req_conflict_b])
        await db.flush()

        # 1. Evidence mapping NEEDS_REVIEW, then CONFIRMED/REJECTED preservation
        ev_svc = TenderRequirementEvidenceService()
        evs = await ev_svc.generate_for_requirement(db, tender.id, req_needs_review.id)
        assert len(evs) >= 2
        assert all(e.mapping_status == "NEEDS_REVIEW" for e in evs)

        # Human marks one CONFIRMED and one REJECTED
        evs[0].mapping_status = "CONFIRMED"
        evs[1].mapping_status = "REJECTED"
        await db.flush()

        # Re-generate -> CONFIRMED & REJECTED preserved, no duplicates
        evs_after = await ev_svc.generate_for_requirement(db, tender.id, req_needs_review.id)
        statuses = {e.evidence_type: e.mapping_status for e in evs_after}
        assert statuses[evs[0].evidence_type] == "CONFIRMED"
        assert statuses[evs[1].evidence_type] == "REJECTED"

        # 2. Conflict DISMISSED preservation across re-detection
        conf_svc = TenderRequirementConflictService()
        conflicts_1 = await conf_svc.detect_conflicts(db, tender.id)
        assert len(conflicts_1) == 1
        conflicts_1[0].status = "DISMISSED"
        conflicts_1[0].reviewed_at = datetime.now(timezone.utc)
        await db.flush()

        conflicts_2 = await conf_svc.detect_conflicts(db, tender.id)
        assert len(conflicts_2) == 1
        assert conflicts_2[0].status == "DISMISSED"

        # 3. Provenance SOURCE_CHANGED when document SHA-256 changes
        doc1.sha256_hash = hashlib.sha256(b"nit-modified-v2").hexdigest()
        await db.flush()
        prov_res = await TenderRequirementProvenanceService().verify_and_get_provenance(
            db, tender.id, req_needs_review.id, persist_status=True
        )
        assert prov_res["verification_status"] == "SOURCE_CHANGED"
        await db.commit()
