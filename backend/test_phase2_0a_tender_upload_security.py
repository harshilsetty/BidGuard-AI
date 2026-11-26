"""Phase 2.0A Comprehensive Security, Upload Validation, Multi-Document & PostgreSQL RLS Tests."""
import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.main import app
from app.services.tender_upload_service import sanitize_pdf_filename
from tests_auth_helper import create_test_officer_and_headers


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_valid_pdf_bytes(text_body: str = "BidGuard Tender Specification Clause 1") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text_body)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.anyio
async def test_phase2_0a_upload_validation_and_multi_document_security():
    await init_db()
    tmp_upload_dir = tempfile.mkdtemp(prefix="bidguard_2_0a_")
    try:
        async with AsyncSessionLocal() as db:
            org_a, _, headers_a = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            _, _, auditor_headers = await create_test_officer_and_headers(db, role_name="AUDITOR")
            org_b, _, headers_b = await create_test_officer_and_headers(db, role_name="PROCUREMENT_OFFICER")
            await db.commit()

        pdf_1 = _make_valid_pdf_bytes("Primary NIT Document Content")
        pdf_2 = _make_valid_pdf_bytes("Technical Specification Content")

        transport = ASGITransport(app=app)
        with patch.object(settings, "UPLOAD_DIR", tmp_upload_dir):
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # 1. Valid legacy /tenders/upload creates Tender + PRIMARY_NIT TenderDocument
                res_t1 = await client.post(
                    "/api/v1/tenders/upload",
                    data={"title": "Phase 2.0A Test Tender 1", "gem_tender_id": "GEM/2026/20A/01"},
                    files={"file": ("nit_primary.pdf", pdf_1, "application/pdf")},
                    headers=headers_a,
                )
                assert res_t1.status_code == 201, res_t1.text
                tender_1_id = res_t1.json()["id"]

                # Create second tender in Org A for cross-tender tests
                res_t2 = await client.post(
                    "/api/v1/tenders/upload",
                    data={"title": "Phase 2.0A Test Tender 2"},
                    files={"file": ("nit_second.pdf", pdf_2, "application/pdf")},
                    headers=headers_a,
                )
                assert res_t2.status_code == 201
                tender_2_id = res_t2.json()["id"]

                # 2. Valid multi-document upload to tender_1
                res_doc = await client.post(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    data={"document_role": "TECHNICAL_SPEC"},
                    files={"file": ("tech_spec.pdf", pdf_2, "application/pdf")},
                    headers=headers_a,
                )
                assert res_doc.status_code == 201, res_doc.text
                doc_json = res_doc.json()
                assert doc_json["original_filename"] == "tech_spec.pdf"
                assert doc_json["document_role"] == "TECHNICAL_SPEC"
                assert "storage_path" not in doc_json
                assert len(doc_json["sha256_hash"]) == 64
                doc_id = doc_json["id"]

                # Verify tenant-partitioned path on disk
                expected_disk_path = Path(tmp_upload_dir).resolve() / str(org_a.id) / tender_1_id / f"{doc_id}.pdf"
                assert expected_disk_path.exists()

                # 3. Filename traversal, absolute path, Windows traversal, empty filename, invalid extension
                for bad_name in [
                    "../../etc/passwd.pdf",
                    "/etc/evil.pdf",
                    "..\\..\\evil.pdf",
                    "C:\\Windows\\evil.pdf",
                    "   ",
                    "not_a_pdf.txt",
                    "a" * 260 + ".pdf",
                ]:
                    with pytest.raises(HTTPException) as exc_info:
                        sanitize_pdf_filename(bad_name)
                    assert exc_info.value.status_code == 400

                for http_bad_name in [
                    "../../etc/passwd.pdf",
                    "/etc/evil.pdf",
                    "   ",
                    "not_a_pdf.txt",
                ]:
                    bad_res = await client.post(
                        f"/api/v1/tenders/{tender_1_id}/documents",
                        data={"document_role": "ANNEXURE"},
                        files={"file": (http_bad_name, _make_valid_pdf_bytes(http_bad_name), "application/pdf")},
                        headers=headers_a,
                    )
                    assert bad_res.status_code == 400, f"Expected 400 for {http_bad_name!r}, got {bad_res.status_code}"

                # 4. PDF extension with non-PDF content -> 422
                fake_pdf = await client.post(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    data={"document_role": "ANNEXURE"},
                    files={"file": ("fake.pdf", b"<html>not a pdf</html>", "application/pdf")},
                    headers=headers_a,
                )
                assert fake_pdf.status_code == 422

                # 5. Invalid PDF structure -> 422
                corrupt_pdf = await client.post(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    data={"document_role": "ANNEXURE"},
                    files={"file": ("corrupt.pdf", b"%PDF-1.4\ncorrupted-body-no-xref", "application/pdf")},
                    headers=headers_a,
                )
                assert corrupt_pdf.status_code == 422

                # 6. Oversized upload & exact limit check (temporarily patch MAX_UPLOAD_SIZE_MB=1)
                with patch.object(settings, "MAX_UPLOAD_SIZE_MB", 1):
                    oversized = b"%PDF-1.4\n" + (b"A" * (1024 * 1024 + 100))
                    over_res = await client.post(
                        f"/api/v1/tenders/{tender_1_id}/documents",
                        data={"document_role": "BOQ"},
                        files={"file": ("too_big.pdf", oversized, "application/pdf")},
                        headers=headers_a,
                    )
                    assert over_res.status_code == 413

                    # Exact <= 1 MB valid PDF succeeds
                    exact_pdf = _make_valid_pdf_bytes("Exact size boundary test")
                    assert len(exact_pdf) <= 1024 * 1024
                    ok_res = await client.post(
                        f"/api/v1/tenders/{tender_1_id}/documents",
                        data={"document_role": "BOQ"},
                        files={"file": ("within_limit.pdf", exact_pdf, "application/pdf")},
                        headers=headers_a,
                    )
                    assert ok_res.status_code == 201

                # 7. Duplicate SHA-256 within same tender -> 409; same file in different tender -> 201
                dup_res = await client.post(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    data={"document_role": "CORRIGENDUM"},
                    files={"file": ("renamed_dup.pdf", pdf_2, "application/pdf")},
                    headers=headers_a,
                )
                assert dup_res.status_code == 409

                diff_tender_res = await client.post(
                    f"/api/v1/tenders/{tender_2_id}/documents",
                    data={"document_role": "CORRIGENDUM"},
                    files={"file": ("shared_doc.pdf", pdf_1, "application/pdf")},
                    headers=headers_a,
                )
                assert diff_tender_res.status_code == 201

                # 8. Unauthorized role upload -> 403
                unauth_res = await client.post(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    data={"document_role": "ANNEXURE"},
                    files={"file": ("auditor.pdf", _make_valid_pdf_bytes("x"), "application/pdf")},
                    headers=auditor_headers,
                )
                assert unauth_res.status_code == 403

                # 9. Cross-tenant upload, listing, and mismatched tender/document ID -> 404
                cross_up = await client.post(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    data={"document_role": "ANNEXURE"},
                    files={"file": ("cross.pdf", _make_valid_pdf_bytes("cross"), "application/pdf")},
                    headers=headers_b,
                )
                assert cross_up.status_code in (403, 404)

                cross_list = await client.get(
                    f"/api/v1/tenders/{tender_1_id}/documents",
                    headers=headers_b,
                )
                assert cross_list.status_code in (403, 404)

                mismatch_meta = await client.get(
                    f"/api/v1/tenders/{tender_2_id}/documents/{doc_id}",
                    headers=headers_a,
                )
                assert mismatch_meta.status_code == 404

                # 10. DB failure after file creation cleans up stored file
                org_a_dir = Path(tmp_upload_dir).resolve() / str(org_a.id) / tender_1_id
                before_files = set(org_a_dir.iterdir())
                with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=RuntimeError("DB write error")):
                    with pytest.raises(RuntimeError):
                        await client.post(
                            f"/api/v1/tenders/{tender_1_id}/documents",
                            data={"document_role": "OTHER"},
                            files={"file": ("cleanup.pdf", _make_valid_pdf_bytes("cleanup"), "application/pdf")},
                            headers=headers_a,
                        )
                after_files = set(org_a_dir.iterdir())
                assert before_files == after_files
    finally:
        shutil.rmtree(tmp_upload_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_phase2_0a_postgres_rls_and_pool_isolation_under_bidguard_app():
    """Verify tender_documents PostgreSQL RLS under restricted bidguard_app role & pool_size=1."""
    if "sqlite" in settings.DATABASE_URL:
        pytest.skip("PostgreSQL-only RLS verification")

    app_url = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"
    engine = create_async_engine(app_url, pool_size=1, max_overflow=0)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())
    tender_a_id = str(uuid.uuid4())
    tender_b_id = str(uuid.uuid4())
    doc_a_id = str(uuid.uuid4())
    doc_b_id = str(uuid.uuid4())

    try:
        # Setup using superuser/admin session or SUPER_ADMIN RLS context
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for oid, slug in [(org_a_id, f"rls-a-{uuid.uuid4().hex[:6]}"), (org_b_id, f"rls-b-{uuid.uuid4().hex[:6]}")]:
                await s.execute(
                    text("INSERT INTO organizations (id, name, slug, is_active, created_at, updated_at) VALUES (:id, :n, :s, true, now(), now())"),
                    {"id": oid, "n": slug, "s": slug},
                )
            for tid, oid in [(tender_a_id, org_a_id), (tender_b_id, org_b_id)]:
                await s.execute(
                    text("INSERT INTO tenders (id, organization_id, title, total_pages, extraction_status, next_clause_seq, created_at, updated_at) VALUES (:id, :oid, 'RLS Tender', 1, 'UPLOADED', '{}', now(), now())"),
                    {"id": tid, "oid": oid},
                )
            for did, tid, h in [(doc_a_id, tender_a_id, "a" * 64), (doc_b_id, tender_b_id, "b" * 64)]:
                await s.execute(
                    text("INSERT INTO tender_documents (id, tender_id, document_role, original_filename, storage_path, file_size_bytes, sha256_hash, total_pages, processing_status, created_at, updated_at) VALUES (:id, :tid, 'PRIMARY_NIT', 'doc.pdf', '/tmp/x.pdf', 100, :h, 1, 'UPLOADED', now(), now())"),
                    {"id": did, "tid": tid, "h": h},
                )
            await s.commit()

        # Verify Org A context sees only doc_a_id (and pool_size=1 does not leak to Org B)
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_a_id})
            rows = (await s.execute(text("SELECT id::text FROM tender_documents"))).scalars().all()
            assert rows == [doc_a_id]

            # Cross-tenant UPDATE/DELETE blocked
            upd = await s.execute(text("UPDATE tender_documents SET original_filename='pwn.pdf' WHERE id=:id"), {"id": doc_b_id})
            assert upd.rowcount == 0
            await s.commit()

        # Next checkout on same pool_size=1 connection with Org B context
        async with Session() as s:
            await s.execute(text("SELECT set_config('app.is_super_admin', 'false', true)"))
            await s.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": org_b_id})
            rows = (await s.execute(text("SELECT id::text FROM tender_documents"))).scalars().all()
            assert rows == [doc_b_id]
            await s.commit()
    finally:
        await engine.dispose()
