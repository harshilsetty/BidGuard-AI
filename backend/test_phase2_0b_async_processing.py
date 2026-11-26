"""Phase 2.0B Tests: Persistent Async Jobs, Atomic Claiming, Lease Recovery,
PDF/OCR Page Persistence, Tenant Isolation, and PostgreSQL RLS under bidguard_app.
"""
import asyncio
import hashlib
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.main import app
from app.models.tender import TenderDocument, TenderDocumentPage, TenderProcessingJob
from app.services.ocr_engine import OCRResult
from app.services.tender_processing_worker import (
    claim_next_job,
    execute_claimed_job,
    recover_expired_leases,
)
from tests_auth_helper import create_test_officer_and_headers


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        if body:
            page.insert_text((72, 72), body)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.anyio
async def test_phase2_0b_job_lifecycle_pages_retry_and_security():
    await init_db()
    tmp_dir = tempfile.mkdtemp(prefix="bidguard_2_0b_")
    try:
        async with AsyncSessionLocal() as db:
            _, _, headers_a = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            _, _, auditor_headers = await create_test_officer_and_headers(db, role_name="AUDITOR")
            _, _, headers_b = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            await db.commit()

        pdf_2_pages = _make_pdf_bytes([
            "Section 1 Mandatory Technical Eligibility Criteria for Servers and Storage Systems",
            "",  # blank page -> EMPTY_SCANNED
        ])
        expected_sha256 = hashlib.sha256(pdf_2_pages).hexdigest()
        assert expected_sha256 != hashlib.sha256(b"").hexdigest()

        transport = ASGITransport(app=app)
        with patch.object(settings, "UPLOAD_DIR", tmp_dir):
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # Upload tender + document and verify exact SHA-256
                t_res = await client.post(
                    "/api/v1/tenders/upload",
                    data={"title": "Phase 2.0B Async Tender"},
                    files={"file": ("nit_async.pdf", pdf_2_pages, "application/pdf")},
                    headers=headers_a,
                )
                assert t_res.status_code == 201
                tender_id = t_res.json()["id"]

                docs_res = await client.get(f"/api/v1/tenders/{tender_id}/documents", headers=headers_a)
                assert docs_res.status_code == 200
                doc_id = docs_res.json()[0]["id"]
                assert docs_res.json()[0]["sha256_hash"] == expected_sha256

                # Clear any leftover QUEUED/RUNNING jobs from prior runs for deterministic race testing
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        update(TenderProcessingJob)
                        .where(TenderProcessingJob.status.in_(["QUEUED", "RUNNING"]))
                        .values(status="FAILED")
                    )
                    await s.commit()

                # 1. Enqueue processing -> 202 Accepted; duplicate enqueue coalesces
                p1 = await client.post(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/process",
                    headers=headers_a,
                )
                assert p1.status_code == 202
                job_id = p1.json()["id"]
                assert p1.json()["status"] == "QUEUED"
                assert "worker_id" not in p1.json()

                p2 = await client.post(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/process",
                    headers=headers_a,
                )
                assert p2.status_code == 202
                assert p2.json()["id"] == job_id

                # 2. Unauthorized enqueue & cross-tenant job/page retrieval
                assert (
                    await client.post(
                        f"/api/v1/tenders/{tender_id}/documents/{doc_id}/process",
                        headers=auditor_headers,
                    )
                ).status_code == 403
                assert (
                    await client.get(f"/api/v1/tenders/{tender_id}/jobs/{job_id}", headers=headers_b)
                ).status_code in (403, 404)
                assert (
                    await client.get(
                        f"/api/v1/tenders/{tender_id}/documents/{doc_id}/pages",
                        headers=headers_b,
                    )
                ).status_code in (403, 404)

                # 3. Atomic concurrent claim: two workers race, only ONE claims
                async def _claim(wid: str):
                    async with AsyncSessionLocal() as s:
                        return await claim_next_job(s, wid)

                c1, c2 = await asyncio.gather(_claim("worker-race-1"), _claim("worker-race-2"))
                winners = [c for c in (c1, c2) if c is not None]
                assert len(winners) == 1
                winner_worker = "worker-race-1" if c1 is not None else "worker-race-2"

                # 4. Execute claimed job and verify persisted pages + READY status
                outcome = await execute_claimed_job(winners[0], winner_worker)
                assert outcome == "SUCCEEDED"

                j_status = await client.get(f"/api/v1/tenders/{tender_id}/jobs/{job_id}", headers=headers_a)
                assert j_status.status_code == 200
                assert j_status.json()["status"] == "SUCCEEDED"
                assert j_status.json()["progress_pct"] == 100

                pages_res = await client.get(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/pages?limit=1&offset=0",
                    headers=headers_a,
                )
                assert pages_res.status_code == 200
                assert pages_res.json()["total"] == 2
                assert pages_res.json()["items"][0]["extraction_method"] == "DIGITAL_TEXT"

                page2_res = await client.get(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/pages?limit=1&offset=1",
                    headers=headers_a,
                )
                assert page2_res.json()["items"][0]["extraction_method"] == "EMPTY_SCANNED"

                # 5. Failed reprocessing (e.g., page limit exceeded) preserves prior READY pages
                with patch.object(settings, "MAX_TENDER_PDF_PAGES", 1):
                    re_res = await client.post(
                        f"/api/v1/tenders/{tender_id}/documents/{doc_id}/process",
                        headers=headers_a,
                    )
                    assert re_res.status_code == 202
                    re_job_id = re_res.json()["id"]
                    async with AsyncSessionLocal() as s:
                        claimed = await claim_next_job(s, "worker-limit")
                    assert str(claimed) == re_job_id
                    fail_outcome = await execute_claimed_job(claimed, "worker-limit")
                    assert fail_outcome == "FAILED"

                    # Prior 2 pages remain intact!
                    kept_pages = await client.get(
                        f"/api/v1/tenders/{tender_id}/documents/{doc_id}/pages",
                        headers=headers_a,
                    )
                    assert kept_pages.json()["total"] == 2

                # 6. Retry endpoint & audit/authorization checks
                assert (
                    await client.post(
                        f"/api/v1/tenders/{tender_id}/jobs/{re_job_id}/retry",
                        headers=auditor_headers,
                    )
                ).status_code == 403
                retry_ok = await client.post(
                    f"/api/v1/tenders/{tender_id}/jobs/{re_job_id}/retry",
                    headers=headers_a,
                )
                assert retry_ok.status_code == 202
                assert retry_ok.json()["status"] == "QUEUED"
                assert retry_ok.json()["retry_count"] == 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_phase2_0b_lease_recovery_scanned_ocr_and_integrity_failures():
    await init_db()
    tmp_dir = tempfile.mkdtemp(prefix="bidguard_2_0b_rec_")
    try:
        async with AsyncSessionLocal() as db:
            _, _, headers_a = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            await db.commit()

        pdf_1 = _make_pdf_bytes(["Short"])  # < 10 words -> triggers OCR path
        transport = ASGITransport(app=app)
        with patch.object(settings, "UPLOAD_DIR", tmp_dir):
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                t_res = await client.post(
                    "/api/v1/tenders/upload",
                    data={"title": "OCR & Lease Recovery Tender"},
                    files={"file": ("scan.pdf", pdf_1, "application/pdf")},
                    headers=headers_a,
                )
                tender_id = t_res.json()["id"]
                doc_id = (await client.get(f"/api/v1/tenders/{tender_id}/documents", headers=headers_a)).json()[0]["id"]

                p_res = await client.post(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/process",
                    headers=headers_a,
                )
                job_id = uuid.UUID(p_res.json()["id"])

                # Simulate crashed worker with expired lease (clear any prior test's queued/running jobs first)
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        update(TenderProcessingJob)
                        .where(
                            TenderProcessingJob.status.in_(["QUEUED", "RUNNING"]),
                            TenderProcessingJob.id != job_id,
                        )
                        .values(status="FAILED")
                    )
                    await s.commit()
                    claimed = await claim_next_job(s, "crashed-worker")
                    assert claimed == job_id
                    await s.execute(
                        update(TenderProcessingJob)
                        .where(TenderProcessingJob.id == job_id)
                        .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=60))
                    )
                    await s.commit()

                async with AsyncSessionLocal() as s:
                    recovered = await recover_expired_leases(s)
                    assert recovered >= 1

                # Verify job was re-queued with retry_count=1 and LEASE_EXPIRED note
                j_check = await client.get(f"/api/v1/tenders/{tender_id}/jobs/{job_id}", headers=headers_a)
                assert j_check.json()["status"] == "QUEUED"
                assert j_check.json()["retry_count"] == 1

                # Claim & execute with mocked OCR engine (OCR_PROCESSED)
                class _MockOCR:
                    def ocr_page_image(self, image_bytes, page_number=1):
                        return OCRResult(
                            text="Scanned Bid Clause Requiring ISO 9001 Certification",
                            mean_confidence=0.92,
                            is_success=True,
                        )

                async with AsyncSessionLocal() as s:
                    claimed2 = await claim_next_job(s, "healthy-worker")
                with patch("app.services.pdf_extractor.get_ocr_engine", return_value=_MockOCR()):
                    res_exec = await execute_claimed_job(claimed2, "healthy-worker")
                assert res_exec == "SUCCEEDED"

                pages_res = await client.get(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/pages",
                    headers=headers_a,
                )
                assert pages_res.json()["items"][0]["extraction_method"] == "OCR_PROCESSED"

                # SHA-256 mismatch failure check
                async with AsyncSessionLocal() as s:
                    doc_obj = (
                        await s.execute(select(TenderDocument).where(TenderDocument.id == uuid.UUID(doc_id)))
                    ).scalar_one()
                    Path(doc_obj.storage_path).write_bytes(b"%PDF-1.4\ntampered")

                p_tamper = await client.post(
                    f"/api/v1/tenders/{tender_id}/documents/{doc_id}/process",
                    headers=headers_a,
                )
                tamper_job_id = uuid.UUID(p_tamper.json()["id"])
                async with AsyncSessionLocal() as s:
                    claimed_t = await claim_next_job(s, "integrity-worker")
                assert claimed_t == tamper_job_id
                fail_res = await execute_claimed_job(tamper_job_id, "integrity-worker")
                assert fail_res == "FAILED"
                j_tamper = await client.get(f"/api/v1/tenders/{tender_id}/jobs/{tamper_job_id}", headers=headers_a)
                assert j_tamper.json()["error_code"] == "INTEGRITY_SIZE_MISMATCH"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_phase2_0b_postgres_rls_jobs_and_pages_under_bidguard_app():
    if "sqlite" in settings.DATABASE_URL:
        pytest.skip("PostgreSQL-only RLS verification")

    app_url = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"
    engine = create_async_engine(app_url, pool_size=1, max_overflow=0)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    t_a, t_b = str(uuid.uuid4()), str(uuid.uuid4())
    d_a, d_b = str(uuid.uuid4()), str(uuid.uuid4())
    j_a, j_b = str(uuid.uuid4()), str(uuid.uuid4())
    p_a, p_b = str(uuid.uuid4()), str(uuid.uuid4())

    try:
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for oid in (org_a, org_b):
                slug = f"rls2b-{oid[:8]}"
                await s.execute(
                    text("INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) VALUES (:id, :n, :s, true, now(), now())"),
                    {"id": oid, "n": slug, "s": slug},
                )
            for tid, oid in [(t_a, org_a), (t_b, org_b)]:
                await s.execute(
                    text("INSERT INTO tenders (id, organization_id, title, total_pages, extraction_status, next_clause_seq, created_at, updated_at) VALUES (:id, :oid, 'RLS', 1, 'UPLOADED', '{}', now(), now())"),
                    {"id": tid, "oid": oid},
                )
            for did, tid, h in [(d_a, t_a, "c" * 64), (d_b, t_b, "d" * 64)]:
                await s.execute(
                    text("INSERT INTO tender_documents (id, tender_id, document_role, original_filename, storage_path, file_size_bytes, sha256_hash, total_pages, processing_status, created_at, updated_at) VALUES (:id, :tid, 'PRIMARY_NIT', 'd.pdf', '/tmp/d.pdf', 10, :h, 1, 'UPLOADED', now(), now())"),
                    {"id": did, "tid": tid, "h": h},
                )
            for jid, tid, did in [(j_a, t_a, d_a), (j_b, t_b, d_b)]:
                await s.execute(
                    text("INSERT INTO tender_processing_jobs (id, tender_id, tender_document_id, job_type, status, idempotency_key, retry_count, max_retries, progress_pct, current_stage, created_at, updated_at) VALUES (:id, :tid, :did, 'PAGE_EXTRACTION', 'QUEUED', :k, 0, 3, 0, 'QUEUED', now(), now())"),
                    {"id": jid, "tid": tid, "did": did, "k": f"PAGE_EXTRACTION:{did}"},
                )
            for pid, did in [(p_a, d_a), (p_b, d_b)]:
                await s.execute(
                    text("INSERT INTO tender_document_pages (id, tender_document_id, page_number, extracted_text, word_count, extraction_method, extraction_status, created_at, updated_at) VALUES (:id, :did, 1, 'hello', 1, 'DIGITAL_TEXT', 'SUCCEEDED', now(), now())"),
                    {"id": pid, "did": did},
                )
            await s.commit()

        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_a})
            assert (await s.execute(text("SELECT id::text FROM tender_processing_jobs"))).scalars().all() == [j_a]
            assert (await s.execute(text("SELECT id::text FROM tender_document_pages"))).scalars().all() == [p_a]
            await s.commit()

        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_b})
            assert (await s.execute(text("SELECT id::text FROM tender_processing_jobs"))).scalars().all() == [j_b]
            assert (await s.execute(text("SELECT id::text FROM tender_document_pages"))).scalars().all() == [p_b]
            await s.commit()
    finally:
        await engine.dispose()
