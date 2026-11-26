# Phase 2.0B.2 Implementation Report: Stale-Worker Fencing & Job Ownership Integrity Remediation

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Remediated Defect:** Phase 2.0B.1 **P1** — Stale-worker ownership overwrite  
**Verdict:** **ACCEPTED — READY FOR PHASE 2.0C (PENDING AUTHORIZATION)**

---

## 1. Original Defect Reproduction & Root Cause

During Phase 2.0B.1 (`audit_20b1.py`), the following sequence reproduced a **P1** state-corruption defect:
1. Worker 1 (`stale-worker-1`) claimed a queued job.
2. Worker 1's lease expired and `recover_expired_leases` re-queued the job.
3. Worker 2 (`healthy-worker-2`) reclaimed and completed the job (`status='SUCCEEDED'`, `TenderDocument.processing_status='READY'`).
4. Worker 1 subsequently executed `_handle_job_failure(...)`, overwriting the `SUCCEEDED` job back to `QUEUED` (`error_code='EXTRACTION_ERROR'`) and reverting `TenderDocument.processing_status` to `QUEUED`.

**Root Cause:**
- `TenderProcessingJob` lacked a monotonic `ownership_generation` fencing token.
- `_handle_job_failure` queried by `id` alone without verifying `status == 'RUNNING'`, `worker_id`, or `ownership_generation`.
- `execute_claimed_job` steps 5 & 6 (`_persist_pages_idempotently` and `update(TenderDocument)`), `_heartbeat_loop`, and `CancelledError` release did not enforce atomic `(status == 'RUNNING', worker_id, ownership_generation)` fencing.

---

## 2. Ownership & Fencing Design

### 2.1 Schema & Migration (`0009_job_ownership_generation`)
- **Model (`backend/app/models/tender.py`):** Added `ownership_generation = Column(Integer, default=0, nullable=False)` to `TenderProcessingJob`.
- **Migration (`backend/alembic/versions/0009_job_ownership_generation.py`):** Additive forward migration (`revision = '0009_job_ownership_generation'`, `down_revision = '0008_tender_jobs_and_pages'`) adding `ownership_generation INTEGER NOT NULL DEFAULT 0`. Applied to both `gem_compliance` and `bidguard_fresh_test`.
- **Rollback:** `alembic downgrade 0008_tender_jobs_and_pages` cleanly drops the column without affecting historical migrations or RLS policies.

### 2.2 Monotonic Generation Transitions (`backend/app/services/tender_processing_worker.py`)
- `claim_next_job_fenced(db, worker_id)` (and backward-compatible `claim_next_job`) atomically increments `ownership_generation = ownership_generation + 1` on every claim (`FOR UPDATE SKIP LOCKED` on PostgreSQL; conditional `UPDATE` on SQLite).
- `recover_expired_leases(db)` locks expired `RUNNING` rows (`FOR UPDATE SKIP LOCKED` on PostgreSQL) and increments `ownership_generation = ownership_generation + 1`, immediately invalidating any stale holder before another worker even claims the job.
- Graceful shutdown release (`CancelledError`) and failure transitions (`_handle_job_failure`) also increment `ownership_generation` when releasing/terminating ownership.

---

## 3. Guarded Write Boundaries

Every worker write path in `backend/app/services/tender_processing_worker.py` now gates on `(id == job_id, status == 'RUNNING', worker_id == worker_id, ownership_generation == expected_gen)`:

1. **Pre-execution check (`execute_claimed_job` step 1):** Verifies active `(RUNNING, worker_id, ownership_generation)`; otherwise logs `OWNERSHIP_LOST` and returns `"OWNERSHIP_LOST"`.
2. **Heartbeat (`_heartbeat_loop`):** Conditional `UPDATE` with fencing predicate; `rowcount == 0` logs `OWNERSHIP_LOST event=heartbeat_fenced`, sets `ownership_lost_event` and `stop_event`, and exits.
3. **Stage progression (`EXTRACTING_PAGES`, step 3):** Conditional `UPDATE`; `rowcount == 0` aborts before extraction and returns `"OWNERSHIP_LOST"`.
4. **Page persistence (`PERSISTING_PAGES`, step 5):** No DB transaction is held during `asyncio.to_thread(extract_pages_from_pdf, ...)`. Upon return, checks `ownership_lost_event`, opens a short transaction, and verifies `TenderProcessingJob` ownership via conditional `UPDATE` (`rowcount == 1`) *before* calling `_persist_pages_idempotently`; otherwise rolls back and returns `"OWNERSHIP_LOST"`.
5. **Finalization (`SUCCEEDED`, step 6):** Conditional `UPDATE` on `TenderProcessingJob` (`rowcount == 1`) gates `TenderDocument.processing_status = 'READY'` in the same transaction; otherwise rolls back and returns `"OWNERSHIP_LOST"`.
6. **Failure handler (`_handle_job_failure`):** Uses `SELECT ... FOR UPDATE` with `(id == job_id, status == 'RUNNING', worker_id == worker_id, ownership_generation == expected_gen)`. Missing match logs `OWNERSHIP_LOST event=failure_handler_fenced` and returns `"OWNERSHIP_LOST"` without mutating job or document state.
7. **Graceful shutdown (`CancelledError`):** Conditional `UPDATE` with fencing predicate releases only jobs still owned by `(worker_id, expected_gen)`.

---

## 4. Adversarial Fencing & PostgreSQL RLS Verification

Created `backend/test_phase2_0b_2_fencing.py` (`test_phase2_0b_2_adversarial_stale_worker_fencing_under_bidguard_app`) executing **all 10 required adversarial scenarios** against PostgreSQL 16 (`bidguard_fresh_test`) under the restricted `bidguard_app` role (`rolsuper=False, rolbypassrls=False`):

1. Stale failure after Worker 2 `SUCCEEDED` -> returns `"OWNERSHIP_LOST"`; job stays `SUCCEEDED`, document stays `READY`.
2. Stale success after reclaim during `extract_pages_from_pdf` -> returns `"OWNERSHIP_LOST"`.
3. Stale page persistence -> Worker 2's `TenderDocumentPage` text preserved.
4. Stale document status -> `TenderDocument.processing_status` remains `READY`.
5. Stale heartbeat -> `ownership_lost_event.is_set()` triggered; lease untouched.
6. Same `worker_id`, stale `ownership_generation=1` vs current `ownership_generation=5` -> stale execution returns `"OWNERSHIP_LOST"`, current succeeds.
7. Repeated lease expiry -> `ownership_generation` advances monotonically (`1 -> 2 -> 3 -> 4 -> 5`).
8. Concurrent `claim_next_job_fenced` calls -> exactly one winner acquires `(j4, 1)`.
9. Shutdown race (`CancelledError`) -> stopping worker with `(worker_1, gen=1)` cannot release job reclaimed by `("new-owner", gen=2)`.
10. RLS preservation -> verified under `bidguard_app` with `rolsuper=False, rolbypassrls=False`.

---

## 5. Complete Backend Regression Results

- **Targeted Phase 2.0B.2 Fencing Suite (`cd backend; python -m pytest test_phase2_0b_2_fencing.py -v --tb=short`):**
  - `1 passed, 10 warnings in 5.98s`
- **Complete Backend Suite (`cd backend; python -m pytest -v --tb=short`):**
  - **Collected:** `334 items`
  - **Observed Result:** **`334 passed, 25 warnings in 267.35s (0:04:27)`** (`0` failed, `0` errors, `0` skipped), covering:
    - Phase 2.0B.2 stale-worker fencing (`1 passed`)
    - Phase 2.0B async processing (`3 passed`)
    - Phase 2.0A upload security & RLS (`2 passed`)
    - PostgreSQL RLS & concurrency (`2 passed`)
    - Enterprise auth, RBAC, audit, invitations, E2E journeys (`19 passed`)
    - Golden Demo frozen regression (`4 passed`)
    - All API, statutory, scoring, verification, and database hardening suites.
- **Frontend:** No frontend files were modified in Phase 2.0B.2.

---

## 6. Remaining Limitations

- **OS Thread Non-Preemption:** Python's `asyncio` task cancellation cannot preempt a blocking C/PyMuPDF/OCR call already running inside `asyncio.to_thread(...)` until that thread returns; however, `ownership_generation` fencing guarantees any late results or errors from that thread are discarded (`OWNERSHIP_LOST`) and cannot mutate database state.
- **OCR Runtime Dependency:** Local Python 3.13 environment lacks `paddleocr` (`No module named 'paddleocr'`), so real OCR execution relies on `paddleocr` being installed in the target deployment image.
