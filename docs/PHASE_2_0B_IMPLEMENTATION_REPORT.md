# Phase 2.0B Implementation Report: Reliable Asynchronous Tender Document Processing

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82` (uncommitted working-tree changes; not committed/pushed)  
**Target Gap Remediated:** `GAP-02` — Synchronous PDF/OCR extraction in the HTTP request lifecycle  
**Verdict:** **ACCEPTED**

---

## 1. Executive Summary

Phase 2.0B eliminates synchronous PDF/OCR extraction from the HTTP request path and introduces a PostgreSQL-backed asynchronous job processing pipeline for TenderLens documents (`TenderDocument` -> `TenderProcessingJob` -> `TenderDocumentPage`).

- Upload and `/process` requests return immediately (`202 Accepted` for job enqueue/retry) without blocking FastAPI event-loop workers.
- A managed background worker (`TenderProcessingWorkerManager`) claims jobs atomically via PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`, enforces lease/heartbeat/expired-lease recovery, executes PyMuPDF + PaddleOCR extraction inside bounded `asyncio.to_thread()` workers (`JOB_MAX_CONCURRENT_WORKERS = 2`), and persists idempotent per-page results in `tender_document_pages`.
- Tenant isolation is enforced end-to-end via `get_authorized_tender` RBAC checks and PostgreSQL `FORCE ROW LEVEL SECURITY` under the non-superuser `bidguard_app` role.
- All **36 backend tests** (including Phase 2.0B async processing, Phase 2.0A upload security, Phase 1.x enterprise auth/RBAC/RLS, and Golden Demo frozen regression) and **13 frontend tests** (`tsc --noEmit`, `npm test`, `next build`) pass with **0 failures**.

---

## 2. Files Modified & Created

### Backend
- `backend/app/core/config.py` — Added `MAX_TENDER_PDF_PAGES=500`, `JOB_LEASE_SECONDS=120`, `JOB_HEARTBEAT_SECONDS=15`, `JOB_POLL_INTERVAL_SECONDS=2.0`, `JOB_MAX_CONCURRENT_WORKERS=2`, `JOB_DEFAULT_MAX_RETRIES=3`.
- `backend/app/models/tender.py` & `backend/app/models/__init__.py` — Added `TenderProcessingJob` and `TenderDocumentPage` ORM models with `UniqueConstraint("tender_document_id", "page_number", name="uq_tender_document_pages_doc_page")`.
- `backend/alembic/versions/0008_tender_processing_jobs_and_pages.py` — Forward Alembic migration (`revision = '0008_tender_jobs_and_pages'`, `down_revision = '0007_tender_documents'`).
- `backend/app/services/tender_processing_worker.py` — Implemented `TenderProcessingWorkerManager`, `claim_next_job`, `recover_expired_leases`, `_heartbeat_loop`, `execute_claimed_job`, `_persist_pages_idempotently`, and `_handle_job_failure`.
- `backend/app/main.py` — Wired `worker_manager.start()` and `worker_manager.stop()` into FastAPI `lifespan`.
- `backend/app/schemas/tender.py` — Added `TenderProcessingJobResponse`, `TenderDocumentPageResponse`, `TenderDocumentPagesListResponse`, and `latest_job` on `TenderDocumentResponse`.
- `backend/app/api/v1/tenders.py` — Added `/documents/{document_id}/process`, `/jobs/{job_id}`, `/jobs/{job_id}/retry`, `/documents/{document_id}/pages`, and offloaded `extract_tender_clauses`'s `extract_pages_from_pdf` call to `asyncio.to_thread()`.
- `backend/test_phase2_0b_async_processing.py` — Added 3 integration, lease-recovery/OCR/integrity, and PostgreSQL RLS verification tests.

### Frontend
- `frontend/src/lib/types.ts` — Added Phase 2.0B job and page TypeScript interfaces.
- `frontend/src/lib/api-client.ts` — Added methods for enqueueing processing, polling job status, retrying failed jobs, and fetching paginated extracted pages.
- `frontend/src/components/TenderDocumentsPanel.tsx` — Integrated async processing trigger, bounded polling, stage/progress indicator, sanitized error display, and authorized retry action.
- `frontend/tests/auth.test.ts` — Added Phase 2.0B client/UI helper assertions.

### Documentation
- `docs/PHASE_2_0B_BASELINE_AND_CHANGE_PLAN.md`
- `docs/TENDER_PROCESSING_JOB_ARCHITECTURE.md`
- `docs/PHASE_2_0B_IMPLEMENTATION_REPORT.md`

---

## 3. Database Migration & PostgreSQL RLS (`0008_tender_jobs_and_pages`)

Migration `0008_tender_jobs_and_pages` (revising `0007_tender_documents`) was applied to both `gem_compliance` and `bidguard_fresh_test`:

- **`tender_processing_jobs`**:
  - Indexes on `tender_id`, `tender_document_id`, `status`, `idempotency_key`, `lease_expires_at`.
  - Partial unique index `uq_active_job_per_doc_type` on `(idempotency_key)` `WHERE status IN ('QUEUED', 'RUNNING', 'RETRY_WAIT')` to prevent duplicate active jobs per document/job type.
  - RLS policy `tenant_isolation_tender_processing_jobs` with `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` scoping access via `tenders.organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid` (or `app.is_super_admin = 'true'`).
- **`tender_document_pages`**:
  - Unique constraint `uq_tender_document_pages_doc_page` on `(tender_document_id, page_number)`.
  - RLS policy `tenant_isolation_tender_document_pages` with `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` joining `tender_documents -> tenders` to enforce `organization_id`.

---

## 4. Job Lifecycle, Worker Execution & Concurrency

1. **Enqueue & Coalescing:** Creating a `PAGE_EXTRACTION` job sets `idempotency_key = f"PAGE_EXTRACTION:{document_id}"`. If an active job (`QUEUED`, `RUNNING`, `RETRY_WAIT`) already exists, the existing job is returned (`202 Accepted`) without creating a duplicate.
2. **Atomic Claiming:** `claim_next_job` uses `SELECT ... FROM tender_processing_jobs WHERE status = 'QUEUED' ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1` on PostgreSQL (with a conditional atomic `UPDATE` fallback for SQLite).
3. **Lease, Heartbeat & Recovery:**
   - Claiming sets `lease_expires_at = now + JOB_LEASE_SECONDS` (`120s`).
   - `_heartbeat_loop` extends `lease_expires_at` every `JOB_HEARTBEAT_SECONDS` (`15s`).
   - `recover_expired_leases` transitions expired `RUNNING` jobs back to `QUEUED` (incrementing `retry_count` and setting `error_code = 'LEASE_EXPIRED'`), or terminal `FAILED` if `retry_count >= max_retries`.
4. **Bounded CPU/OCR Offloading:**
   - File root, existence, `file_size_bytes`, SHA-256 hash, and `MAX_TENDER_PDF_PAGES` (`500`) are verified outside any DB transaction (`_verify_file_and_page_count_sync`).
   - `extract_pages_from_pdf` runs inside `asyncio.to_thread()` guarded by `asyncio.Semaphore(settings.JOB_MAX_CONCURRENT_WORKERS)`.
5. **Idempotent Page Persistence & Failure Preservation:**
   - `_persist_pages_idempotently` upserts `TenderDocumentPage` rows by `(tender_document_id, page_number)`.
   - Failed reprocessing preserves previously committed `READY` pages instead of wiping prior extracted content.
   - Non-retryable error codes (`FILE_NOT_FOUND`, `STORAGE_PATH_INVALID`, `INTEGRITY_SIZE_MISMATCH`, `INTEGRITY_HASH_MISMATCH`, `PAGE_LIMIT_EXCEEDED`, `INVALID_PDF`) transition immediately to terminal `FAILED`.

---

## 5. API Contracts

All endpoints enforce `get_authorized_tender` tenant isolation and RBAC:

- `POST /api/v1/tenders/{tender_id}/documents/{document_id}/process` -> `202 Accepted` (`TenderProcessingJobResponse`)
- `GET /api/v1/tenders/{tender_id}/jobs/{job_id}` -> `200 OK` (`TenderProcessingJobResponse`)
- `POST /api/v1/tenders/{tender_id}/jobs/{job_id}/retry` -> `202 Accepted` (`TenderProcessingJobResponse`, transitions terminal `FAILED` job back to `QUEUED` if authorized)
- `GET /api/v1/tenders/{tender_id}/documents/{document_id}/pages` -> `200 OK` (`TenderDocumentPagesListResponse`, paginated)

---

## 6. Performance & Reliability Measurements

Observed benchmark on PostgreSQL 16 (`bidguard_fresh_test`) processing a 2-page digital PDF via `tender_processing_worker`:

| Operation | Observed Duration | Outcome |
|---|---:|---|
| Job enqueue + commit (`TenderProcessingJob`) | `14.49 ms` | `QUEUED` |
| Atomic `claim_next_job` (`FOR UPDATE SKIP LOCKED`) | `36.02 ms` | `RUNNING` |
| `execute_claimed_job` (verify SHA-256/size + PyMuPDF 2 pages + upsert + finalize) | `136.66 ms` | `SUCCEEDED` |

---

## 7. Verification Results

### Backend Suite
Command run in `backend/`:
```powershell
python -m pytest test_phase2_0b_async_processing.py test_phase2_0a_tender_upload_security.py test_phase1_4_e2e_journeys.py test_enterprise_auth.py test_enterprise_tenant_rbac.py test_enterprise_audit.py test_enterprise_security_remediation.py test_enterprise_org_invitations.py test_postgres_rls_and_concurrency.py test_golden_demo_frozen_regression.py test_api_bidders_evaluations.py -v --tb=short
```
**Observed Result:** `36 passed, 25 warnings in 63.83s (0:01:03)` (0 failed, 0 skipped).

### Frontend Suite
Commands run in `frontend/`:
- `npx tsc --noEmit` -> `0` errors.
- `npm test` -> `13 passed, 0 failed, 0 skipped` in `120.3257ms`.
- `npm run build` (`next build`) -> succeeded cleanly (`10/10` static pages generated).

---

## 8. Known Limitations & Out-of-Scope Boundaries

- **Single-Process Worker Pool:** `TenderProcessingWorkerManager` runs inside the FastAPI process (`lifespan`), using PostgreSQL as the durable queue/lease store. Multi-replica horizontal scaling works via `FOR UPDATE SKIP LOCKED`, though externalized worker processes are deferred until needed.
- **Out of Scope (Not Implemented):** Expanded LLM requirement extraction, taxonomy expansion, corrigendum/conflict detection, evidence mapping, and bid readiness scoring (deferred to Phase 2.0C+ pending explicit authorization).
