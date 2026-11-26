# Phase 2.0B.1: Background Worker Security, RLS & Reliability Acceptance Audit

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Audit Scope:** Audit-only verification of Phase 2.0B (`tender_processing_worker.py`, `main.py`, `database.py`, `0008_tender_jobs_and_pages`, PostgreSQL RLS under `bidguard_app`, concurrency/fencing/lease/shutdown). No application code, migrations, RLS policies, privileges, or Golden Demo fixtures were modified.

---

## 1. Repository Safety & Baseline State

- **Branch / HEAD:** `main` at `96b040bf03bba17fe7400c95b57e3907bdd0cd82`.
- **Working Tree:** Preserved all uncommitted Phase 1.x, 2.0A, and 2.0B changes intact (`git status --short` recorded 90+ modified/added/untracked files across `backend/`, `frontend/`, `docs/`, and `scripts/`).
- **Golden Demo:** Unmodified (`test_golden_demo_frozen_regression.py` verified).

---

## 2. Cross-Tenant Worker Execution & PostgreSQL RLS Investigation

### 2.1 Inspected Components
- `backend/app/services/tender_processing_worker.py`
- `backend/app/main.py` (`lifespan`, lines 18–27)
- `backend/app/core/database.py` (engine/pool configuration, lines 16–45)
- `backend/alembic/versions/0008_tender_processing_jobs_and_pages.py` (RLS policies, lines 74–108)
- `backend/app/api/deps.py` (lines 114–122) & `backend/app/services/auth_service.py` (lines 33–41)

### 2.2 PostgreSQL Role, Policy & Pool Evidence

Queried directly on PostgreSQL 16:
- **Roles (`pg_roles`):**
  - `postgres`: `rolsuper=True, rolbypassrls=True, rolcanlogin=True`
  - `bidguard_app`: `rolsuper=False, rolbypassrls=False, rolcanlogin=True`
- **Privileges on `bidguard_fresh_test` (`information_schema.table_privileges` for `bidguard_app`):**
  - `SELECT`, `INSERT`, `UPDATE`, `DELETE` on `tenders`, `tender_documents`, `tender_processing_jobs`, `tender_document_pages`.
- **RLS Policies (`pg_policies`):**
  - `tender_processing_jobs`: `tenant_isolation_tender_processing_jobs` (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`)
  - `tender_document_pages`: `tenant_isolation_tender_document_pages` (`ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`)
  - Policy predicate: `COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true'` OR `t.organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid`.

### 2.3 Audit Questions & Observed Answers

1. **How does the worker discover queued jobs belonging to multiple organizations?**  
   In `claim_next_job()` (`tender_processing_worker.py:205–238`), the worker calls `set_worker_rls_context(db, is_super_admin=True)` before querying `TenderProcessingJob` (`status == 'QUEUED'`). On PostgreSQL, it uses `ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1`.

2. **What RLS context exists when `claim_next_job()` executes?**  
   Transaction-local (`is_local = true`) settings: `app.is_super_admin = 'true'` and `app.current_org_id = ''`.

3. **Can the worker claim jobs if `app.current_org_id` is unset?**  
   **Yes**, when `app.is_super_admin = 'true'` (as set by `claim_next_job`). Conversely, when neither `app.current_org_id` nor `app.is_super_admin = 'true'` is set, RLS denies all rows (`POOL1_INITIAL_GUCS: (None, None) VISIBLE_WITHOUT_SA: 0`).

4. **Can it process jobs from Organization A and Organization B in the same worker lifecycle?**  
   **Yes.** Verified using `bidguard_app` (`rolsuper=False, rolbypassrls=False`) against `bidguard_fresh_test`:
   - `CROSS_TENANT_BIDGUARD_APP: claimed=(1dfb57d3-766e-4bfd-8e5a-2c368de1a926, cac01c9e-571c-4327-80b7-82dafa6db5a7), results=(SUCCEEDED, SUCCEEDED)`
   - Ordinary tenant sessions remained strictly isolated:
     - `TENANT_A_SEES: jobs=[UUID('1dfb57d3-...')], pages=[UUID('7c4f3060-...')]`
     - `TENANT_B_SEES: jobs=[UUID('cac01c9e-...')], pages=[UUID('23fc7146-...')]`

5. **Does the worker establish the correct tenant context before accessing each document and its pages?**  
   **Yes** during normal execution (`execute_claimed_job` lines 413, 428, 439): after loading `org_id = tender.organization_id` in step 1, steps 3, 5, and 6 set `set_worker_rls_context(db, organization_id=org_id, is_super_admin=org_id is None)`. Step 1, `_heartbeat_loop`, `recover_expired_leases`, `CancelledError` release, and `_handle_job_failure` use `is_super_admin=True` because they operate on `TenderProcessingJob` across tenants.

6. **Is tenant context reliably cleared or replaced when a database connection is reused?**  
   **Yes.** All code setting `app.current_org_id` and `app.is_super_admin` (`deps.py:116,120`, `auth_service.py:39`, `tender_processing_worker.py:63,67`) passes `true` as the third argument to `set_config(..., true)`, making it transaction-local (`SET LOCAL`). Verified on a single-connection pool (`pool_size=1, max_overflow=0`): after committing a transaction with `organization_id=org_a`, the next transaction on the same physical connection observed `POOL1_AFTER_COMMIT_GUCS: ('', '')`.

7. **Does the implementation require RLS bypass or elevated database privileges?**  
   **No.** `bidguard_app` has `rolsuper=False` and `rolbypassrls=False`. Cross-tenant job claiming and recovery work solely via the policy's `app.is_super_admin` GUC branch (`set_config('app.is_super_admin', 'true', true)`), without `BYPASSRLS` or superuser privileges.

---

## 3. Findings Register (Classified)

### [P1] Missing Stale-Worker Fencing in `execute_claimed_job` and `_handle_job_failure`
- **Status:** Open (requires fix before Phase 2.0C).
- **Evidence & Source Location:**
  - `backend/app/services/tender_processing_worker.py` lines 434, 441–445, and 518–559.
  - Reproducible test output (`audit_20b1.py`):
    `STALE_FENCING_TEST: w2=SUCCEEDED, stale_fail_ret=RETRY_QUEUED, job_status_after=QUEUED, job_error=EXTRACTION_ERROR, doc_status_after=QUEUED`
- **Reproduction Steps:**
  1. Worker 1 claims `job_id` (`status='RUNNING', worker_id='stale-worker-1'`).
  2. `lease_expires_at` elapses and `recover_expired_leases` re-queues the job.
  3. Worker 2 claims `job_id`, executes `extract_pages_from_pdf`, and completes (`status='SUCCEEDED'`, `TenderDocument.processing_status='READY'`).
  4. Stale Worker 1 (whose blocking `asyncio.to_thread(extract_pages_from_pdf, ...)` or failure path finishes late) calls `_handle_job_failure(job_id, doc_id, ...)` — or reaches steps 5/6 (`_persist_pages_idempotently` / `update(TenderDocument)`).
- **Impact:** `_handle_job_failure` queries `TenderProcessingJob` by `id` alone without checking `status == 'RUNNING' AND worker_id == worker_id`, overwriting Worker 2's `SUCCEEDED` job back to `QUEUED` (`error_code='EXTRACTION_ERROR'`) and reverting `TenderDocument.processing_status` to `QUEUED`. Similarly, `execute_claimed_job` steps 5 & 6 persist `TenderDocumentPage` rows and set `TenderDocument.processing_status = 'READY'` without an atomic ownership check (`status == 'RUNNING' AND worker_id == worker_id`) in the same transaction.
- **Recommended Correction:**
  1. Pass `worker_id` into `_handle_job_failure` and fence the update with `WHERE id = :job_id AND status = 'RUNNING' AND worker_id = :worker_id`; if 0 rows match, abort without modifying `TenderProcessingJob` or `TenderDocument`.
  2. In `execute_claimed_job` steps 5 & 6, issue a conditional `UPDATE tender_processing_jobs ... WHERE id = :job_id AND status = 'RUNNING' AND worker_id = :worker_id` (or `SELECT ... FOR UPDATE` verifying ownership) *before* calling `_persist_pages_idempotently` and updating `TenderDocument`; roll back and return `"STALE_OWNERSHIP_LOST"` if ownership was lost.
- **Required before Phase 2.0C?** **Yes.**

### [P2] `bidguard_app` Table Privileges Missing on Default `gem_compliance` Database
- **Status:** Informational / Operational configuration gap.
- **Evidence:** `information_schema.table_privileges` on `gem_compliance` returned `[]` for `bidguard_app`, whereas `bidguard_fresh_test` had full `SELECT/INSERT/UPDATE/DELETE` grants. Additionally, `settings.DATABASE_URL` defaults to `localhost:5432/gem_compliance` (superuser `postgres`).
- **Impact:** Switching `DATABASE_URL` to `bidguard_app` against `gem_compliance` without running privilege grants would fail; running as `postgres` (`rolbypassrls=True`) bypasses RLS in local dev.
- **Recommended Correction:** Grant `SELECT, INSERT, UPDATE, DELETE` on application tables to `bidguard_app` in target environments and configure runtime `DATABASE_URL` to use `bidguard_app`.
- **Required before Phase 2.0C?** **No.**

### [Informational] `paddleocr` Package Not Installed in Local Python 3.13 Runtime
- **Evidence:** `Failed to load PaddleOCR engine: No module named 'paddleocr'. Fallback to error response.`
- **Impact:** Real scanned PDFs without embedded text fall back to `OCR_FAILED` in this environment unless `paddleocr` is installed; mocked OCR tests pass.
- **Required before Phase 2.0C?** **No** (environment dependency).

---

## 4. Audit Gate Verdict

**CONDITIONAL / BLOCKED ON P1 FENCING FIX:** Cross-tenant background processing under the restricted `bidguard_app` role (`rolsuper=False, rolbypassrls=False`) and transaction-local pool GUC isolation are **verified**, and multi-instance claiming + shutdown recovery work as designed; however, **one P1 defect** (missing stale-worker ownership fencing in `_handle_job_failure` and `execute_claimed_job` steps 5–6) was reproducibly demonstrated and must be remediated before Phase 2.0C.
