# PHASE 2.0B: BASELINE & CHANGE PLAN

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**Base Commit SHA:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Alembic Chain:** `0001_initial_baseline` -> ... -> `0007_tender_documents`

---

## 1. Audited Baseline & Phase 2.0A SHA-256 Discrepancy Check

- **Discrepancy Check:** `docs/PHASE_2_0A_IMPLEMENTATION_REPORT.md` used `"e3b0c442..."` as an illustrative placeholder in its JSON example. Inspection of `backend/app/services/tender_upload_service.py::stream_validate_and_store_pdf` confirms that SHA-256 is computed incrementally over every streamed `64 KB` chunk and `0`-byte uploads are explicitly rejected (`422 Unprocessable Entity`), so an empty-file digest can never be persisted. An explicit known-SHA-256 verification test is included in Phase 2.0B.
- **Current `extract_tender_clauses` (`backend/app/api/v1/tenders.py` L256–331):** Runs `extract_pages_from_pdf(pdf_bytes)` synchronously inside the HTTP request lifecycle (`GAP-02`).
- **Existing `pdf_extractor.py`:** PyMuPDF native digital text extraction (`>=10` alnum words -> `DIGITAL_TEXT`), 200 DPI rasterization, `is_pixmap_blank()`, and PaddleOCR (`OCR_PROCESSED`, `OCR_LOW_CONFIDENCE`, `OCR_FAILED`, `EMPTY_SCANNED`).

---

## 2. Planned Phase 2.0B Architecture & Files

1. **Configuration (`backend/app/core/config.py`):**
   - `MAX_TENDER_PDF_PAGES: int = 500`
   - `JOB_LEASE_SECONDS: int = 120`, `JOB_HEARTBEAT_SECONDS: int = 15`, `JOB_POLL_INTERVAL_SECONDS: float = 2.0`, `JOB_MAX_CONCURRENT_WORKERS: int = 2`, `JOB_DEFAULT_MAX_RETRIES: int = 3`.
2. **Data Models & Migration (`backend/app/models/tender.py`, `backend/app/models/__init__.py`, `backend/alembic/versions/0008_tender_processing_jobs_and_pages.py`):**
   - `TenderProcessingJob`: persistent PostgreSQL job queue (`QUEUED` -> `RUNNING` -> `SUCCEEDED` | `RETRY_WAIT` -> `QUEUED` | `FAILED`), lease/heartbeat fields (`worker_id`, `lease_expires_at`, `heartbeat_at`), `idempotency_key`, `retry_count`/`max_retries`, `progress_pct`, `current_stage`.
   - `TenderDocumentPage`: persisted page-level extraction (`tender_document_id`, `page_number`, `extracted_text`, `word_count`, `extraction_method`, `ocr_confidence`, `extraction_status`, unique `(tender_document_id, page_number)`).
   - PostgreSQL `ENABLE` + `FORCE ROW LEVEL SECURITY` on both tables scoped through `tenders.organization_id`.
3. **Worker & Page Processor (`backend/app/services/tender_processing_worker.py`):**
   - Application-managed `asyncio` worker loop started/stopped gracefully in FastAPI `lifespan` (`backend/app/main.py`) + startup stale-lease reconciliation.
   - Atomic job claiming (`SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL, atomic conditional `UPDATE` fallback on SQLite).
   - Reuses `pdf_extractor.py` inside `asyncio.to_thread()` with bounded concurrency (`asyncio.Semaphore(JOB_MAX_CONCURRENT_WORKERS)`), verifies file existence, size, SHA-256, and `MAX_TENDER_PDF_PAGES`, persists pages idempotently without destroying prior `READY` pages on failed reprocessing, and updates `TenderDocument.processing_status`.
4. **APIs (`backend/app/api/v1/tenders.py`, `backend/app/schemas/tender.py`):**
   - `POST /api/v1/tenders/{tender_id}/documents/{document_id}/process` -> `202 Accepted` (idempotent coalescing).
   - `GET /api/v1/tenders/{tender_id}/jobs/{job_id}` (`tender:read`).
   - `GET /api/v1/tenders/{tender_id}/documents/{document_id}/pages` (paginated, `tender:read`).
   - `POST /api/v1/tenders/{tender_id}/jobs/{job_id}/retry` (`tender:update`).
   - Note on legacy `POST /api/v1/tenders/{tender_id}/extract`: offload blocking `extract_pages_from_pdf(pdf_bytes)` to `asyncio.to_thread(...)` so the FastAPI event loop is never blocked by synchronous PDF/OCR extraction in legacy callers.
5. **Frontend (`TenderDocumentsPanel.tsx`, `api-client.ts`, `types.ts`):**
   - Process button, immediate `QUEUED` state, bounded polling (stops on `SUCCEEDED`/`FAILED` and unmount), stage/progress display, sanitized error, and authorized retry button.
