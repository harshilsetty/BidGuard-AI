# Phase 2.0B.1: Reliability, Concurrency, Test Reconciliation & Benchmark Results

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Audit Mode:** Read-only / non-destructive verification (zero repo code, migration, RLS, privilege, or Golden Demo edits)

---

## 1. Worker Concurrency, Lease Ownership & Fencing Results

| Scenario | Observed Result | Classification |
|---|---|---|
| Competing `claim_next_job` calls on PostgreSQL | `FOR UPDATE SKIP LOCKED` ensures only one worker claims a `QUEUED` job; tested in `test_phase2_0b_job_lifecycle_pages_retry_and_security` and `audit_20b1.py` | **Pass** |
| Expired lease recovery (`recover_expired_leases`) | Expired `RUNNING` job re-queued with `retry_count = 1`, `error_code = 'LEASE_EXPIRED'`; max-retry exhaustion transitions to `FAILED` (`LEASE_EXPIRED_MAX_RETRIES`) | **Pass** |
| **Stale-worker ownership fencing** | `STALE_FENCING_TEST: w2=SUCCEEDED, stale_fail_ret=RETRY_QUEUED, job_status_after=QUEUED, job_error=EXTRACTION_ERROR, doc_status_after=QUEUED`. Stale Worker 1 overwrote Worker 2's completed job and `TenderDocument.processing_status` because `_handle_job_failure` and `execute_claimed_job` steps 5–6 do not gate on `(status = 'RUNNING' AND worker_id = :worker_id)` | **P1 Defect** |
| Repeated enqueue coalescing | Active job (`QUEUED`, `RUNNING`, `RETRY_WAIT`) returns existing job (`202 Accepted`) via `uq_active_job_per_doc_type` | **Pass** |
| Reprocessing after `SUCCEEDED` & idempotent page upsert | `POST .../process` after `SUCCEEDED` creates a new job; `_persist_pages_idempotently` upserts by `(tender_document_id, page_number)`; failed reprocessing preserves prior `READY` pages | **Pass** |

---

## 2. Multi-Instance & Graceful Shutdown Verification

Verified against PostgreSQL 16 (`bidguard_fresh_test`) under `bidguard_app`:

- **Two Concurrent `TenderProcessingWorkerManager` Instances (`wm1`, `wm2`):**
  - Observed IDs: `wm1=worker-26496-80385ef0`, `wm2=worker-26496-bf8f622f`
  - Observed completion: `m1=(SUCCEEDED, worker-26496-80385ef0)`, `m2=(SUCCEEDED, worker-26496-bf8f622f)`
  - Healthy unexpired lease preservation: `healthy_other_node=(RUNNING, other-healthy-node)` remained untouched by `recover_expired_leases`.
- **Graceful Shutdown During Active Extraction (`wm_shut.stop()`):**
  - Interrupting an in-flight `extract_pages_from_pdf` thread via `asyncio.CancelledError` in `execute_claimed_job` released the job cleanly:
    `SHUTDOWN_INTERRUPTED_JOB: status=QUEUED, worker_id=None, lease=None`.
  - Operational caveat: `asyncio` task cancellation does not preempt the underlying OS thread inside `asyncio.to_thread(extract_pages_from_pdf, ...)` until that thread returns; without P1 fencing (Section 1), a still-running thread during non-shutdown lease expiry could race with a new owner.

---

## 3. Test-Suite Reconciliation

### 3.1 Targeted Suites (Phase 2.0B, 2.0A, Enterprise Auth/RBAC/RLS, Golden Demo)
Command (`backend/`):
```powershell
python -m pytest test_phase2_0b_async_processing.py test_phase2_0a_tender_upload_security.py test_phase1_4_e2e_journeys.py test_enterprise_auth.py test_enterprise_tenant_rbac.py test_enterprise_audit.py test_enterprise_security_remediation.py test_enterprise_org_invitations.py test_postgres_rls_and_concurrency.py test_golden_demo_frozen_regression.py test_api_bidders_evaluations.py -v --tb=short
```
- **Observed Result:** `36 passed, 25 warnings in 63.83s (0:01:03)` (`0` failed, `0` skipped):
  - Phase 2.0B (`test_phase2_0b_async_processing.py`): `3 passed`
  - Phase 2.0A (`test_phase2_0a_tender_upload_security.py`): `2 passed`
  - PostgreSQL RLS & Concurrency (`test_postgres_rls_and_concurrency.py`): `2 passed`
  - Auth / RBAC / Audit / Invitations / E2E (`test_phase1_4_e2e_journeys.py`, `test_enterprise_*.py`): `19 passed`
  - Golden Demo Frozen Regression (`test_golden_demo_frozen_regression.py`): `4 passed`
  - Bidders & Evaluations API (`test_api_bidders_evaluations.py`): `6 passed`

### 3.2 Complete Backend Test Suite
Command (`backend/`):
```powershell
python -m pytest -v --tb=short
```
- **Collected:** `333 items`
- **Observed Result:** `333 passed, 25 warnings in 239.60s (0:03:59)` (`0` failed, `0` errors, `0` skipped).

---

## 4. Performance & Operational Benchmarks

| Workload | Pages | Extraction Outcome | Observed Duration | Notes |
|---|---:|---|---|---|
| 2-page digital PDF | 2 | `SUCCEEDED` | enqueue `14.49 ms`, claim `36.02 ms`, execute `136.66 ms` | PostgreSQL 16 (`bidguard_fresh_test`) |
| 25-page digital PDF | 25 | `SUCCEEDED` | `189.35 ms` (claim + execute) | PyMuPDF digital text path |
| 2-page scanned PDF (mocked OCR) | 2 | `SUCCEEDED` (`OCR_PROCESSED`) | `796.29 ms` (claim + execute) | Real `paddleocr` package absent in local Python 3.13 env (`No module named 'paddleocr'`) |

**Configured Resource Limits (`backend/app/core/config.py`):**
- `MAX_TENDER_PDF_PAGES = 500`
- `JOB_MAX_CONCURRENT_WORKERS = 2` (bounded by `asyncio.Semaphore`)
- `JOB_LEASE_SECONDS = 120`, `JOB_HEARTBEAT_SECONDS = 15`, `JOB_POLL_INTERVAL_SECONDS = 2.0`, `JOB_DEFAULT_MAX_RETRIES = 3`

---

## 5. Gate Decision

- **Gate Status:** **HOLD (1 P1 defect identified)** — See `docs/PHASE_2_0B_1_WORKER_RLS_ACCEPTANCE_AUDIT.md` for the P1 stale-worker fencing remediation required before proceeding to Phase 2.0C.
