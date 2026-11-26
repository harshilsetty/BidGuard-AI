# Phase 2.0B.2 Baseline & Change Plan: Stale-Worker Fencing & Job Ownership Integrity Remediation

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Target Defect:** Phase 2.0B.1 **P1** — Missing stale-worker ownership fencing in `tender_processing_worker.py`  
**Scope:** Strictly targeted reliability remediation (no Phase 2.0C features, no UI/frontend changes unless needed, no Golden Demo changes, no commit/push/tag).

---

## 1. Baseline Repository State

- **Branch / HEAD:** `main` at `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`.
- **Existing Uncommitted / Staged Work:**
  - Staged (`A`/`M`): Phase 1.2–2.0B backend (`0006`–`0008`, `tenders.py`, `tender_processing_worker.py`, `tender_upload_service.py`, tests), frontend (`TenderDocumentsPanel.tsx`, `api-client.ts`, `types.ts`, `auth.test.ts`), and `docs/`.
  - Untracked (`??`): `docs/PHASE_2_0B_1_RELIABILITY_AND_CONCURRENCY_RESULTS.md`, `docs/PHASE_2_0B_1_WORKER_RLS_ACCEPTANCE_AUDIT.md`.
- **Golden Demo & Existing Migrations:** Preserved intact; `0008_tender_jobs_and_pages` is untouched.

---

## 2. Root-Cause Confirmation

In Phase 2.0B.1 (`audit_20b1.py`), the following sequence was reproducibly executed against PostgreSQL 16 (`bidguard_fresh_test`):
1. Worker 1 (`stale-worker-1`) claims a `QUEUED` job.
2. Worker 1's `lease_expires_at` elapses (`recover_expired_leases` re-queues the job).
3. Worker 2 (`healthy-worker-2`) reclaims and completes the job (`status='SUCCEEDED'`, `TenderDocument.processing_status='READY'`).
4. Worker 1 subsequently executes `_handle_job_failure(job_id, doc_id, "EXTRACTION_ERROR", ..., retryable=True)`.
5. **Observed Defect:** `STALE_FENCING_TEST: w2=SUCCEEDED, stale_fail_ret=RETRY_QUEUED, job_status_after=QUEUED, job_error=EXTRACTION_ERROR, doc_status_after=QUEUED`.

**Root Causes in `backend/app/services/tender_processing_worker.py`:**
1. No monotonic `ownership_generation` fencing token exists on `TenderProcessingJob` (`worker_id` alone is insufficient if the same worker process re-claims a job after recovery or shutdown).
2. `_handle_job_failure` loads `TenderProcessingJob` by `id` alone without checking `status == 'RUNNING'`, `worker_id`, or `ownership_generation`, overwriting `SUCCEEDED` jobs and `TenderDocument.processing_status`.
3. `execute_claimed_job` steps 5 & 6 call `_persist_pages_idempotently` and `update(TenderDocument)` without verifying active ownership `(status='RUNNING', worker_id, ownership_generation)` in the same transaction.
4. `_heartbeat_loop` does not verify `ownership_generation` or stop on 0-row conditional update (`rowcount == 0`).
5. `CancelledError` shutdown release does not verify `ownership_generation`.

---

## 3. Change Plan

1. **Additive Migration (`0009_job_ownership_generation.py`):**
   - `down_revision = '0008_tender_jobs_and_pages'`
   - Add `ownership_generation INTEGER NOT NULL DEFAULT 0` to `tender_processing_jobs`.
2. **ORM Model (`backend/app/models/tender.py`):**
   - Add `ownership_generation = Column(Integer, default=0, nullable=False)` to `TenderProcessingJob`.
3. **Worker Fencing (`backend/app/services/tender_processing_worker.py`):**
   - `claim_next_job` returns `(job_id, ownership_generation)` (or helper preserves compatibility where needed — update callers cleanly) and atomically increments `ownership_generation = ownership_generation + 1`.
   - `recover_expired_leases` atomically increments `ownership_generation = ownership_generation + 1` when re-queuing/failing expired `RUNNING` jobs, ensuring any stale holder of the previous generation is immediately fenced out even before a new worker claims.
   - Fence `_heartbeat_loop`, `execute_claimed_job` (steps 3, 5, 6, `CancelledError`), and `_handle_job_failure` on `(id == job_id, status == 'RUNNING', worker_id == worker_id, ownership_generation == generation)`.
   - Return explicit `"OWNERSHIP_LOST"` outcome and log a structured ownership-lost warning without mutating job, document, or page rows.
4. **Adversarial Regression Tests (`backend/test_phase2_0b_async_processing.py`):**
   - Update existing calls to `claim_next_job` / `execute_claimed_job` if signatures change, and add all 10 required adversarial fencing tests under `bidguard_app`.
5. **Full Regression & Report:**
   - Run targeted suites + full backend `pytest` suite and write `docs/PHASE_2_0B_2_IMPLEMENTATION_REPORT.md`.
