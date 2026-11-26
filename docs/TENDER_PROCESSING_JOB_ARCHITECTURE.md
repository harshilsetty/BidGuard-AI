# Tender Processing Job Architecture (Phase 2.0B)

**Module:** `backend/app/services/tender_processing_worker.py`  
**Database Revision:** `0008_tender_jobs_and_pages` (`tender_processing_jobs`, `tender_document_pages`)

---

## 1. Architecture Decision

BidGuard uses a **PostgreSQL-backed persistent job table (`tender_processing_jobs`) paired with an application-managed `asyncio` worker loop (`TenderProcessingWorkerManager`)** started and stopped in FastAPI `lifespan` (`backend/app/main.py`).

- **Why not FastAPI `BackgroundTasks` alone?** Request-scoped `BackgroundTasks` disappear on process restart and have no lease/heartbeat, retry budget, or concurrent-worker lock.
- **Why not Redis/Celery/Kafka?** Violates Phase 2.0's minimal modular-monolith infrastructure boundary.
- **Role of `worker_manager.notify()`:** Wakes the polling loop immediately on `POST /process` or `POST /retry`, while PostgreSQL remains the durable source of truth.

---

## 2. Atomic Claiming, Heartbeat & Lease Recovery

- **PostgreSQL Claiming (`claim_next_job`):** Executes `SELECT ... FROM tender_processing_jobs WHERE status = 'QUEUED' ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1` inside a short transaction, transitions to `RUNNING`, assigns `worker_id` + `lease_expires_at` (`120s`), and sets `TenderDocument.processing_status = 'PROCESSING'`.
- **Heartbeat (`_heartbeat_loop`):** Extends `lease_expires_at` every `15s` in a short independent transaction while `extract_pages_from_pdf` runs in `asyncio.to_thread()` bounded by `asyncio.Semaphore(JOB_MAX_CONCURRENT_WORKERS=2)`.
- **Crash / Restart Recovery (`recover_expired_leases`):** Runs on startup and every poll tick. Expired `RUNNING` jobs with `retry_count < max_retries` increment `retry_count` and return to `QUEUED`; exhausted jobs transition to `FAILED`.
- **Graceful Shutdown:** `worker_manager.stop()` cancels active tasks; `CancelledError` releases `RUNNING` jobs cleanly back to `QUEUED`.

---

## 3. State Machine & Stage Mapping

- **Job States:** `QUEUED` -> `RUNNING` -> `SUCCEEDED` | `FAILED` (with `RETRY_WAIT`/`QUEUED` re-queue path).
- **Document Sync:** `QUEUED -> QUEUED`, `RUNNING/RETRY_WAIT -> PROCESSING`, `SUCCEEDED -> READY`, `FAILED -> FAILED`.
- **Page Persistence:** `TenderDocumentPage` enforces `UNIQUE (tender_document_id, page_number)` and upserts idempotently; failed reprocessing attempts **never** wipe previously succeeded `READY` pages.
