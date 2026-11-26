import hashlib
import shutil
import tempfile
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.main import app
from app.models.tender import (
    Tender,
    TenderDocument,
    TenderDocumentPage,
    TenderRequirement,
    TenderRequirementConflict,
    TenderRequirementEvidence,
)
from app.services.requirement_conflict_service import TenderRequirementConflictService
from app.services.requirement_evidence_service import TenderRequirementEvidenceService
from app.services.requirement_provenance_service import (
    TenderRequirementProvenanceService,
    verify_quote_against_pages,
)
from tests_auth_helper import create_test_officer_and_headers

APP_PG_URL = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_phase2_0d_provenance_verification_tiers():
    pages = [
        {"page_number": 1, "text": "The bidder must maintain minimum compre-\nhensive turnover of INR 500 Lakhs during the last three years."},
        {"page_number": 2, "text": "Equipment shall carry 3 years comprehensive onsite warranty from commissioning."},
    ]
    assert verify_quote_against_pages(
        "Equipment shall carry 3 years comprehensive onsite warranty from commissioning.",
        2, pages,
    )[0] == "VERIFIED"

    assert verify_quote_against_pages(
        "The bidder must maintain minimum comprehensive turnover of INR 500 Lakhs",
        1, pages,
    )[0] == "PARTIALLY_VERIFIED"

    wrong_page = verify_quote_against_pages(
        "Equipment shall carry 3 years comprehensive onsite warranty",
        1, pages,
    )
    assert wrong_page[0] == "PARTIALLY_VERIFIED"
    assert wrong_page[1] == 2

    assert verify_quote_against_pages("any quote", 5, pages)[0] == "SOURCE_NOT_FOUND"
    assert verify_quote_against_pages("totally fabricated sentence not in pdf", 2, pages)[0] == "UNVERIFIED"
    assert verify_quote_against_pages("any", 1, pages, recorded_sha256="a" * 64, current_sha256="b" * 64)[0] == "SOURCE_CHANGED"


@pytest.mark.anyio
async def test_phase2_0d_end_to_end_provenance_conflicts_evidence_and_security():
    await init_db()
    tmp_dir = tempfile.mkdtemp(prefix="bidguard_2_0d_")
    try:
        async with AsyncSessionLocal() as db:
            org_a, _, headers_a = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            _, _, headers_b = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            _, _, auditor_headers = await create_test_officer_and_headers(db, role_name="AUDITOR")

            tender = Tender(
                organization_id=org_a.id,
                title="Phase 2.0D Provenance & Conflict Tender",
                total_pages=2,
                extraction_status="READY",
                next_clause_seq={},
            )
            db.add(tender)
            await db.flush()

            doc_nit = TenderDocument(
                tender_id=tender.id,
                document_role="PRIMARY_NIT",
                original_filename="nit.pdf",
                storage_path=f"{tmp_dir}/nit.pdf",
                file_size_bytes=100,
                sha256_hash=hashlib.sha256(b"nit").hexdigest(),
                total_pages=1,
                processing_status="READY",
            )
            doc_corr = TenderDocument(
                tender_id=tender.id,
                document_role="CORRIGENDUM",
                original_filename="corrigendum_1.pdf",
                storage_path=f"{tmp_dir}/corr.pdf",
                file_size_bytes=120,
                sha256_hash=hashlib.sha256(b"corr").hexdigest(),
                total_pages=1,
                processing_status="READY",
            )
            doc_tech = TenderDocument(
                tender_id=tender.id,
                document_role="TECHNICAL_SPEC",
                original_filename="tech.pdf",
                storage_path=f"{tmp_dir}/tech.pdf",
                file_size_bytes=110,
                sha256_hash=hashlib.sha256(b"tech").hexdigest(),
                total_pages=1,
                processing_status="READY",
            )
            db.add_all([doc_nit, doc_corr, doc_tech])
            await db.flush()

            db.add_all([
                TenderDocumentPage(
                    tender_document_id=doc_nit.id,
                    page_number=1,
                    extracted_text=(
                        "Minimum average annual turnover of INR 500 Lakhs with audited balance sheets. "
                        "Lot 1 delivery within 30 days. Bidder must hold valid ISO 9001 certificate."
                    ),
                    word_count=26,
                    extraction_method="DIGITAL_TEXT",
                    extraction_status="SUCCEEDED",
                ),
                TenderDocumentPage(
                    tender_document_id=doc_corr.id,
                    page_number=1,
                    extracted_text="Corrigendum: Minimum average annual turnover is amended to INR 8 Crore.",
                    word_count=10,
                    extraction_method="DIGITAL_TEXT",
                    extraction_status="SUCCEEDED",
                ),
                TenderDocumentPage(
                    tender_document_id=doc_tech.id,
                    page_number=1,
                    extracted_text="Lot 2 delivery within 60 days from PO.",
                    word_count=8,
                    extraction_method="DIGITAL_TEXT",
                    extraction_status="SUCCEEDED",
                ),
            ])

            # Requirements:
            # 1. NIT turnover (FIN, 500 Lakhs INR) + audited balance sheets
            # 2. Corrigendum turnover (FIN, 8 Crore INR) -> POTENTIAL_AMENDMENT
            # 3. Lot 1 delivery (DEL, 30 days) vs Lot 2 delivery (DEL, 60 days) -> disjoint scope, NOT conflict!
            # 4. Unsupported quote requirement -> no fabricated evidence!
            req_nit = TenderRequirement(
                tender_id=tender.id,
                source_document_id=doc_nit.id,
                requirement_code="FIN-01",
                extraction_version=1,
                source_page_number=1,
                source_text="Minimum average annual turnover of INR 500 Lakhs with audited balance sheets",
                source_quote_verified=True,
                normalized_statement="Minimum average annual turnover of INR 500 Lakhs with audited balance sheets.",
                explanatory_interpretation="Turnover threshold.",
                primary_category="FIN",
                secondary_categories=[],
                requirement_type="FINANCIAL_THRESHOLD",
                mandatory_status="MANDATORY",
                numeric_value="500",
                unit="Lakhs",
                currency="INR",
                review_status="DRAFT",
            )
            req_corr = TenderRequirement(
                tender_id=tender.id,
                source_document_id=doc_corr.id,
                requirement_code="FIN-02",
                extraction_version=1,
                source_page_number=1,
                source_text="Corrigendum: Minimum average annual turnover is amended to INR 8 Crore",
                source_quote_verified=True,
                normalized_statement="Amended minimum annual turnover of INR 8 Crore.",
                explanatory_interpretation="Corrigendum turnover amendment.",
                primary_category="FIN",
                secondary_categories=[],
                requirement_type="FINANCIAL_THRESHOLD",
                mandatory_status="MANDATORY",
                numeric_value="8",
                unit="Crore",
                currency="INR",
                review_status="DRAFT",
            )
            req_lot1 = TenderRequirement(
                tender_id=tender.id,
                source_document_id=doc_nit.id,
                requirement_code="DEL-01",
                extraction_version=1,
                source_page_number=1,
                source_text="Lot 1 delivery within 30 days",
                source_quote_verified=True,
                normalized_statement="Lot 1 delivery within 30 days.",
                explanatory_interpretation="Lot 1 schedule.",
                primary_category="DEL",
                secondary_categories=[],
                requirement_type="DELIVERY_CONDITION",
                mandatory_status="MANDATORY",
                numeric_value="30",
                unit="days",
                review_status="DRAFT",
            )
            req_lot2 = TenderRequirement(
                tender_id=tender.id,
                source_document_id=doc_tech.id,
                requirement_code="DEL-02",
                extraction_version=1,
                source_page_number=1,
                source_text="Lot 2 delivery within 60 days from PO",
                source_quote_verified=True,
                normalized_statement="Lot 2 delivery within 60 days from PO.",
                explanatory_interpretation="Lot 2 schedule.",
                primary_category="DEL",
                secondary_categories=[],
                requirement_type="DELIVERY_CONDITION",
                mandatory_status="MANDATORY",
                numeric_value="60",
                unit="days",
                review_status="DRAFT",
            )
            req_ungrounded = TenderRequirement(
                tender_id=tender.id,
                source_document_id=doc_nit.id,
                requirement_code="TECH-01",
                extraction_version=1,
                source_page_number=1,
                source_text="Unsupported quote without evidence keywords",
                source_quote_verified=False,
                normalized_statement="Generic ungrounded note.",
                explanatory_interpretation="Unclear statement.",
                primary_category="TECH",
                secondary_categories=[],
                requirement_type="OTHER",
                mandatory_status="UNCLEAR",
                review_status="NEEDS_REVIEW",
            )
            db.add_all([req_nit, req_corr, req_lot1, req_lot2, req_ungrounded])
            await db.flush()

            # Add additional supporting source without overwriting primary source
            prov_svc = TenderRequirementProvenanceService()
            await prov_svc.add_supporting_source(
                db, tender.id, req_nit.id, doc_corr.id, 1,
                "Corrigendum: Minimum average annual turnover is amended to INR 8 Crore",
                source_role="POTENTIALLY_CONTRADICTORY",
            )
            await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Provenance API
            prov_res = await client.get(
                f"/api/v1/tenders/{tender.id}/requirements/{req_nit.id}/provenance",
                headers=headers_a,
            )
            assert prov_res.status_code == 200
            assert prov_res.json()["verification_status"] == "VERIFIED"
            assert len(prov_res.json()["supporting_sources"]) == 1
            assert prov_res.json()["supporting_sources"][0]["source_role"] == "POTENTIALLY_CONTRADICTORY"

            # Cross-tenant provenance denied
            assert (
                await client.get(
                    f"/api/v1/tenders/{tender.id}/requirements/{req_nit.id}/provenance",
                    headers=headers_b,
                )
            ).status_code in (403, 404)

            # Unauthorized conflict trigger denied
            assert (
                await client.post(f"/api/v1/tenders/{tender.id}/detect-conflicts", headers=auditor_headers)
            ).status_code == 403

            # Conflict detection: FIN-01 vs FIN-02 detected as POTENTIAL_AMENDMENT; Lot 1 vs Lot 2 NOT flagged!
            det_res = await client.post(f"/api/v1/tenders/{tender.id}/detect-conflicts", headers=headers_a)
            assert det_res.status_code == 200
            assert det_res.json()["detected_count"] == 1
            c_item = det_res.json()["conflicts"][0]
            assert c_item["conflict_type"] == "FINANCIAL_MISMATCH"
            assert c_item["relationship_type"] == "POTENTIAL_AMENDMENT"
            assert c_item["status"] == "NEEDS_REVIEW"  # Never RESOLVED automatically

            c_list = await client.get(f"/api/v1/tenders/{tender.id}/conflicts", headers=headers_a)
            assert c_list.status_code == 200 and c_list.json()["total"] == 1
            c_detail = await client.get(f"/api/v1/tenders/{tender.id}/conflicts/{c_item['id']}", headers=headers_a)
            assert c_detail.status_code == 200
            assert c_detail.json()["requirement_a"]["id"] in (str(req_nit.id), str(req_corr.id))

            # Evidence mapping generation & unsupported inference check
            ev_res = await client.post(
                f"/api/v1/tenders/{tender.id}/requirements/{req_nit.id}/generate-evidence-mappings",
                headers=headers_a,
            )
            assert ev_res.status_code == 200
            ev_types = {e["evidence_type"] for e in ev_res.json()["items"]}
            assert "AUDITED_FINANCIAL_STATEMENTS" in ev_types
            assert "TURNOVER_CERTIFICATE" in ev_types
            assert all(e["mapping_status"] == "SUGGESTED" for e in ev_res.json()["items"])

            # Unsupported requirement produces 0 fabricated mappings
            ev_empty = await client.post(
                f"/api/v1/tenders/{tender.id}/requirements/{req_ungrounded.id}/generate-evidence-mappings",
                headers=headers_a,
            )
            assert ev_empty.status_code == 200
            assert ev_empty.json()["total"] == 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_phase2_0d_postgres_rls_under_bidguard_app():
    if "sqlite" in settings.DATABASE_URL:
        pytest.skip("PostgreSQL-only RLS verification")

    engine = create_async_engine(APP_PG_URL, pool_size=1, max_overflow=0)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    t_a, t_b = str(uuid.uuid4()), str(uuid.uuid4())
    d_a, d_b = str(uuid.uuid4()), str(uuid.uuid4())
    r_a, r_b = str(uuid.uuid4()), str(uuid.uuid4())
    ev_a, ev_b = str(uuid.uuid4()), str(uuid.uuid4())

    try:
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for oid in (org_a, org_b):
                slug = f"rls2d-{oid[:8]}"
                await s.execute(
                    text("INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) VALUES (:id, :n, :s, true, now(), now())"),
                    {"id": oid, "n": slug, "s": slug},
                )
            for tid, oid in [(t_a, org_a), (t_b, org_b)]:
                await s.execute(
                    text("INSERT INTO tenders (id, organization_id, title, total_pages, extraction_status, next_clause_seq, created_at, updated_at) VALUES (:id, :oid, 'RLS', 1, 'READY', '{}', now(), now())"),
                    {"id": tid, "oid": oid},
                )
            for did, tid, h in [(d_a, t_a, "1" * 64), (d_b, t_b, "2" * 64)]:
                await s.execute(
                    text("INSERT INTO tender_documents (id, tender_id, document_role, original_filename, storage_path, file_size_bytes, sha256_hash, total_pages, processing_status, created_at, updated_at) VALUES (:id, :tid, 'PRIMARY_NIT', 'd.pdf', '/tmp/d.pdf', 10, :h, 1, 'READY', now(), now())"),
                    {"id": did, "tid": tid, "h": h},
                )
            for rid, tid, did in [(r_a, t_a, d_a), (r_b, t_b, d_b)]:
                await s.execute(
                    text(
                        "INSERT INTO tender_requirements (id, tender_id, source_document_id, requirement_code, extraction_version, source_page_number, source_text, source_quote_verified, normalized_statement, explanatory_interpretation, primary_category, secondary_categories, requirement_type, mandatory_status, extraction_method, model_provider, extraction_confidence, review_status, provenance_status, created_at, updated_at) "
                        "VALUES (:id, :tid, :did, 'FIN-01', 1, 1, 'quote', true, 'norm', 'interp', 'FIN', '[]', 'FINANCIAL_THRESHOLD', 'MANDATORY', 'LLM_STRUCTURED', 'nvidia_nim', 0.9, 'DRAFT', 'VERIFIED', now(), now())"
                    ),
                    {"id": rid, "tid": tid, "did": did},
                )
            for eid, tid, rid in [(ev_a, t_a, r_a), (ev_b, t_b, r_b)]:
                await s.execute(
                    text(
                        "INSERT INTO tender_requirement_evidence (id, tender_id, requirement_id, evidence_type, expected_document_name, evidence_purpose, is_mandatory, source_passage, mapping_method, confidence, mapping_status, created_at, updated_at) "
                        "VALUES (:id, :tid, :rid, 'TURNOVER_CERTIFICATE', 'CA Cert', 'Verify', true, 'quote', 'DETERMINISTIC_RULE', 0.85, 'SUGGESTED', now(), now())"
                    ),
                    {"id": eid, "tid": tid, "rid": rid},
                )
            await s.commit()

        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_a})
            assert (await s.execute(text("SELECT id::text FROM tender_requirement_evidence"))).scalars().all() == [ev_a]
            await s.commit()

        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_b})
            assert (await s.execute(text("SELECT id::text FROM tender_requirement_evidence"))).scalars().all() == [ev_b]
            await s.commit()
    finally:
        await engine.dispose()
