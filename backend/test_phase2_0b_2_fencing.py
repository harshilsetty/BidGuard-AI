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
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.organization import Organization
from app.models.tender import Tender, TenderDocument, TenderDocumentPage, TenderProcessingJob
from app.services import tender_processing_worker as worker_mod

APP_PG_URL = "postgresql+asyncpg://bidguard_app:bidguard_app_test_pw@127.0.0.1:5432/bidguard_fresh_test"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_pdf(text_content: str, out_path: Path) -> tuple[int, str]:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text_content)
    data = doc.tobytes()
    doc.close()
    out_path.write_bytes(data)
    return len(data), hashlib.sha256(data).hexdigest()


@pytest.mark.anyio
async def test_phase2_0b_2_adversarial_stale_worker_fencing_under_bidguard_app():
    if "sqlite" in settings.DATABASE_URL:
        pytest.skip("PostgreSQL-only bidguard_app RLS and fencing verification")

    app_engine = create_async_engine(APP_PG_URL, pool_size=4, max_overflow=0)
    AppSession = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    tmp_dir = tempfile.mkdtemp(prefix="bidguard_2_0b_2_")

    try:
        # 10. Verify restricted bidguard_app role (no superuser, no BYPASSRLS)
        async with AppSession() as s:
            role_row = (
                await s.execute(
                    text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'bidguard_app'")
                )
            ).one()
            assert role_row == (False, False)

            await worker_mod.set_worker_rls_context(s, is_super_admin=True)
            await s.execute(
                update(TenderProcessingJob)
                .where(TenderProcessingJob.status.in_(["QUEUED", "RUNNING", "RETRY_WAIT"]))
                .values(status="FAILED", error_code="TEST_PRECLEAN")
            )
            await s.commit()

        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        t_a, t_b = uuid.uuid4(), uuid.uuid4()

        with patch.object(settings, "UPLOAD_DIR", tmp_dir), patch.object(
            worker_mod, "AsyncSessionLocal", AppSession
        ):
            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                s.add(Organization(id=org_a, name=f"FenceA-{org_a.hex[:6]}", slug=f"fencea-{org_a.hex[:6]}", is_active=True))
                s.add(Organization(id=org_b, name=f"FenceB-{org_b.hex[:6]}", slug=f"fenceb-{org_b.hex[:6]}", is_active=True))
                await s.flush()
                s.add(Tender(id=t_a, organization_id=org_a, title="Fence Tender A", total_pages=1, extraction_status="UPLOADED", next_clause_seq={}))
                s.add(Tender(id=t_b, organization_id=org_b, title="Fence Tender B", total_pages=1, extraction_status="UPLOADED", next_clause_seq={}))
                await s.commit()

            # --- Scenarios 1, 3, 4: Stale failure after success + stale page/doc protection ---
            d1 = uuid.uuid4()
            j1 = uuid.uuid4()
            pdf1 = Path(tmp_dir) / "doc1.pdf"
            sz1, h1 = _make_pdf("Worker2 authoritative clause text requiring ISO 9001 quality management system and audited turnover.", pdf1)
            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                s.add(TenderDocument(id=d1, tender_id=t_a, document_role="PRIMARY_NIT", original_filename="doc1.pdf", storage_path=str(pdf1), file_size_bytes=sz1, sha256_hash=h1, total_pages=1, processing_status="QUEUED"))
                await s.flush()
                s.add(TenderProcessingJob(id=j1, tender_id=t_a, tender_document_id=d1, job_type="PAGE_EXTRACTION", status="QUEUED", idempotency_key=f"PAGE_EXTRACTION:{d1}", current_stage="QUEUED", progress_pct=0, retry_count=0, max_retries=3))
                await s.commit()

            async with AppSession() as s:
                c_w1 = await worker_mod.claim_next_job_fenced(s, "stale-worker-1")
                assert c_w1 == (j1, 1)
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                await s.execute(
                    update(TenderProcessingJob)
                    .where(TenderProcessingJob.id == j1)
                    .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30))
                )
                await s.commit()

            async with AppSession() as s:
                assert await worker_mod.recover_expired_leases(s) >= 1
                c_w2 = await worker_mod.claim_next_job_fenced(s, "healthy-worker-2")
                assert c_w2 == (j1, 3)  # 1 (w1 claim) -> 2 (recover) -> 3 (w2 claim)
            assert await worker_mod.execute_claimed_job(j1, "healthy-worker-2", ownership_generation=3) == "SUCCEEDED"

            # Stale Worker 1 calls _handle_job_failure with old (worker_id, generation=1)
            stale_fail_res = await worker_mod._handle_job_failure(
                j1, d1, "EXTRACTION_ERROR", "Late stale error", retryable=True,
                worker_id="stale-worker-1", ownership_generation=1,
            )
            assert stale_fail_res == "OWNERSHIP_LOST"

            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, organization_id=org_a, is_super_admin=False)
                j_row = (await s.execute(select(TenderProcessingJob).where(TenderProcessingJob.id == j1))).scalar_one()
                d_row = (await s.execute(select(TenderDocument).where(TenderDocument.id == d1))).scalar_one()
                p_row = (await s.execute(select(TenderDocumentPage).where(TenderDocumentPage.tender_document_id == d1))).scalar_one()
                assert j_row.status == "SUCCEEDED"
                assert j_row.error_code is None
                assert d_row.processing_status == "READY"
                assert "Worker2 authoritative clause text" in p_row.extracted_text

            # --- Scenarios 2, 3, 4, 5: Stale success after reclaim + stale heartbeat + stale page overwrite ---
            d2 = uuid.uuid4()
            j2 = uuid.uuid4()
            pdf2 = Path(tmp_dir) / "doc2.pdf"
            sz2, h2 = _make_pdf("Worker2 final clean page text for tender technical compliance and eligibility.", pdf2)
            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                s.add(TenderDocument(id=d2, tender_id=t_b, document_role="PRIMARY_NIT", original_filename="doc2.pdf", storage_path=str(pdf2), file_size_bytes=sz2, sha256_hash=h2, total_pages=1, processing_status="QUEUED"))
                await s.flush()
                s.add(TenderProcessingJob(id=j2, tender_id=t_b, tender_document_id=d2, job_type="PAGE_EXTRACTION", status="QUEUED", idempotency_key=f"PAGE_EXTRACTION:{d2}", current_stage="QUEUED", progress_pct=0, retry_count=0, max_retries=3))
                await s.commit()

            async with AppSession() as s:
                c2_w1 = await worker_mod.claim_next_job_fenced(s, "slow-worker-1")
                assert c2_w1 == (j2, 1)

            loop = asyncio.get_running_loop()

            async def _reclaim_and_finish_w2():
                # Simulate lease expiring while slow-worker-1 is blocked in extract_pages_from_pdf
                async with AppSession() as inner:
                    await worker_mod.set_worker_rls_context(inner, is_super_admin=True)
                    await inner.execute(
                        update(TenderProcessingJob)
                        .where(TenderProcessingJob.id == j2)
                        .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30))
                    )
                    await inner.commit()
                    await worker_mod.recover_expired_leases(inner)
                    c2_w2 = await worker_mod.claim_next_job_fenced(inner, "fast-worker-2")
                    assert c2_w2 == (j2, 3)
                with patch.object(worker_mod, "extract_pages_from_pdf", return_value=[{"page_number": 1, "text": "Authoritative W2 page", "word_count": 3, "extraction_method": "DIGITAL_TEXT", "ocr_confidence": None}]):
                    assert await worker_mod.execute_claimed_job(j2, "fast-worker-2", ownership_generation=3) == "SUCCEEDED"

            def _sync_reclaim_side_effect(_path):
                fut = asyncio.run_coroutine_threadsafe(_reclaim_and_finish_w2(), loop)
                fut.result(timeout=15)
                return [{"page_number": 1, "text": "STALE W1 OVERWRITE", "word_count": 3, "extraction_method": "DIGITAL_TEXT", "ocr_confidence": None}]

            with patch.object(worker_mod, "extract_pages_from_pdf", side_effect=_sync_reclaim_side_effect):
                stale_exec_res = await worker_mod.execute_claimed_job(j2, "slow-worker-1", ownership_generation=1)
            assert stale_exec_res == "OWNERSHIP_LOST"

            # Stale heartbeat test (Scenario 5)
            stop_hb = asyncio.Event()
            lost_hb = asyncio.Event()
            with patch.object(settings, "JOB_HEARTBEAT_SECONDS", 1):
                await worker_mod._heartbeat_loop(j2, "slow-worker-1", 1, stop_hb, lost_hb)
            assert lost_hb.is_set()

            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, organization_id=org_b, is_super_admin=False)
                p2_row = (await s.execute(select(TenderDocumentPage).where(TenderDocumentPage.tender_document_id == d2))).scalar_one()
                assert p2_row.extracted_text == "Authoritative W2 page"

            # --- Scenarios 6 & 7: Same worker_id with new generation + repeated lease expiry ---
            d3 = uuid.uuid4()
            j3 = uuid.uuid4()
            pdf3 = Path(tmp_dir) / "doc3.pdf"
            sz3, h3 = _make_pdf("Same worker ID generation test requiring valid financial turnover and ISO certification.", pdf3)
            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                s.add(TenderDocument(id=d3, tender_id=t_a, document_role="ANNEXURE", original_filename="doc3.pdf", storage_path=str(pdf3), file_size_bytes=sz3, sha256_hash=h3, total_pages=1, processing_status="QUEUED"))
                await s.flush()
                s.add(TenderProcessingJob(id=j3, tender_id=t_a, tender_document_id=d3, job_type="PAGE_EXTRACTION", status="QUEUED", idempotency_key=f"PAGE_EXTRACTION:{d3}", current_stage="QUEUED", progress_pct=0, retry_count=0, max_retries=5))
                await s.commit()

            # Repeated lease expiry -> generation increments 1 -> 2 -> 3 -> 4 -> 5
            async with AppSession() as s:
                assert await worker_mod.claim_next_job_fenced(s, "same-worker") == (j3, 1)
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                await s.execute(update(TenderProcessingJob).where(TenderProcessingJob.id == j3).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10)))
                await s.commit()
                await worker_mod.recover_expired_leases(s)  # gen -> 2
                assert await worker_mod.claim_next_job_fenced(s, "same-worker") == (j3, 3)
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                await s.execute(update(TenderProcessingJob).where(TenderProcessingJob.id == j3).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10)))
                await s.commit()
                await worker_mod.recover_expired_leases(s)  # gen -> 4
                assert await worker_mod.claim_next_job_fenced(s, "same-worker") == (j3, 5)

            # Old execution with same worker_id="same-worker" but stale generation=1 MUST be fenced out
            assert await worker_mod.execute_claimed_job(j3, "same-worker", ownership_generation=1) == "OWNERSHIP_LOST"
            # Current generation=5 succeeds
            assert await worker_mod.execute_claimed_job(j3, "same-worker", ownership_generation=5) == "SUCCEEDED"

            # --- Scenario 8: Concurrent claims cannot acquire same ownership generation ---
            d4 = uuid.uuid4()
            j4 = uuid.uuid4()
            pdf4 = Path(tmp_dir) / "doc4.pdf"
            sz4, h4 = _make_pdf("Concurrent claim and shutdown race test tender compliance document.", pdf4)
            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                s.add(TenderDocument(id=d4, tender_id=t_a, document_role="ANNEXURE", original_filename="doc4.pdf", storage_path=str(pdf4), file_size_bytes=sz4, sha256_hash=h4, total_pages=1, processing_status="QUEUED"))
                await s.flush()
                s.add(TenderProcessingJob(id=j4, tender_id=t_a, tender_document_id=d4, job_type="PAGE_EXTRACTION", status="QUEUED", idempotency_key=f"PAGE_EXTRACTION:{d4}", current_stage="QUEUED", progress_pct=0, retry_count=0, max_retries=3))
                await s.commit()

            async def _claim_race(wid: str):
                async with AppSession() as s:
                    return await worker_mod.claim_next_job_fenced(s, wid)

            r_a, r_b = await asyncio.gather(_claim_race("racer-a"), _claim_race("racer-b"))
            winners = [r for r in (r_a, r_b) if r is not None]
            assert len(winners) == 1
            assert winners[0] == (j4, 1)
            winner_wid = "racer-a" if r_a is not None else "racer-b"

            # --- Scenario 9: Shutdown race cannot release another manager's reclaimed job ---
            gate_entered = asyncio.Event()
            def _slow_for_cancel(_path):
                loop.call_soon_threadsafe(gate_entered.set)
                import time
                time.sleep(0.5)
                return []

            with patch.object(worker_mod, "extract_pages_from_pdf", side_effect=_slow_for_cancel):
                task_cancel = asyncio.create_task(
                    worker_mod.execute_claimed_job(j4, winner_wid, ownership_generation=1)
                )
                await gate_entered.wait()
                # Another manager reclaims ownership to (new-owner, gen=2) before task_cancel is cancelled
                async with AppSession() as s:
                    await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                    await s.execute(
                        update(TenderProcessingJob)
                        .where(TenderProcessingJob.id == j4)
                        .values(worker_id="new-owner", ownership_generation=2, status="RUNNING")
                    )
                    await s.commit()
                task_cancel.cancel()
                try:
                    await task_cancel
                except asyncio.CancelledError:
                    pass

            async with AppSession() as s:
                await worker_mod.set_worker_rls_context(s, is_super_admin=True)
                j4_row = (await s.execute(select(TenderProcessingJob).where(TenderProcessingJob.id == j4))).scalar_one()
                assert j4_row.status == "RUNNING"
                assert j4_row.worker_id == "new-owner"
                assert j4_row.ownership_generation == 2

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        await app_engine.dispose()
