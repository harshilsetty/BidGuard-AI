# TenderLens — Technical Architecture Specification (Phase 2.0)

**Architecture Style:** Modular Monolith (FastAPI + PostgreSQL 16 + `pgvector` + Next.js 15)  
**Design Constraint:** No microservices, Kafka, Redis/Celery clusters, or Kubernetes required for Phase 2.0.

---

## 1. Asynchronous Document Processing Architecture

### 1.1 Option Comparison (Smallest Reliable Fit)
| Option | Pros | Cons | Decision |
|---|---|---|---|
| **Synchronous HTTP Request (Current)** | Zero setup | Times out on >20 page PDFs; no retry/progress | **Rejected (`GAP-02`)** |
| **PostgreSQL-Backed Async Job Table + In-Process `asyncio` Worker (`BackgroundTasks` + DB lock)** | Zero new infra; persistent state (`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`); idempotent; survives client disconnect | Single-node concurrency (sufficient for modular monolith; clean upgrade path to worker process later) | **Selected** |
| **External Celery/Redis/RabbitMQ** | Multi-node scaling | Heavyweight infra; violates Phase 2.0 minimal-infra rule | **Deferred** |

### 1.2 Job Lifecycle & State Transitions
`QUEUED` -> `EXTRACTING_PAGES` -> `EXTRACTING_REQUIREMENTS` -> `VERIFYING_PROVENANCE` -> `SUCCEEDED` | `FAILED` (with `retry_count`, `max_retries=3`, `error_code`, `error_message`, `idempotency_key`).

---

## 2. Document Processing Pipeline

1. **Upload & Validation (`POST /api/v1/tenders/{id}/documents`):**
   - Enforce `require_permission("tender:update")` (or `tender:create` on `/tenders/upload`) and `get_authorized_tender`.
   - Sanitize filename (`os.path.basename` + UUID prefix), enforce `MAX_UPLOAD_SIZE_MB` (streaming chunk limit -> `413`), verify `%PDF-` magic header (`422`), compute SHA-256 `file_hash` for duplicate detection (`409` or idempotent return).
   - Store file under `UPLOAD_DIR/{organization_id}/{tender_id}/{doc_uuid}.pdf` (tenant-partitioned path).
2. **Page Extraction (`pdf_extractor.py`):**
   - Persist per-page records in `tender_document_pages` (`page_number`, `text`, `extraction_method`, `ocr_confidence`, `section_hint`).
   - Run CPU-bound PyMuPDF / PaddleOCR work in `asyncio.to_thread(...)` so the FastAPI event loop stays responsive.
3. **Structured Requirement Extraction (`clause_extractor.py`):**
   - 3-page sliding windows (`stride=2`) with cross-page overlap deduplication.
   - Support tabular extraction hints (Markdown/pipe-delimited tables from PyMuPDF blocks) and corrigendum comparison against prior documents in the same tender.
   - Strict Pydantic schema validation (`LLMExtractionBatch`) + deterministic provenance verification (`verify_source_text_presence`). Unverified quotes are never silently dropped or fabricated — they are flagged `NEEDS_REVIEW` with `provenance_verified=False`.
4. **Human Review & Confirmation:**
   - Officers filter by category, obligation, `NEEDS_REVIEW`, or `OCR_LOW_CONFIDENCE`, inspect source page text side-by-side, edit/confirm/reject, and record immutable `AuditLog` entries.
5. **Bid Readiness Aggregation:**
   - Deterministic SQL/service aggregation over `tender_document_pages`, `tender_clauses`, and `tender_requirement_conflicts` — zero LLM calls in readiness math.

---

## 3. Tenant Isolation, RBAC & Migration Strategy

- All new tables (`tender_documents`, `tender_document_pages`, `tender_processing_jobs`, `tender_requirement_evidences`, `tender_requirement_conflicts`) link to `tenders.id` and enforce PostgreSQL `FORCE ROW LEVEL SECURITY` via `EXISTS (SELECT 1 FROM tenders t WHERE t.id = ... AND t.organization_id = app.current_org_id)`.
- Forward Alembic migrations (`0007+`) only; `0001`–`0006` remain untouched.
- Golden Demo (`GEM/2026/B/8912450`) uses existing `tenders` + `tender_clauses` rows with `organization_id=NULL` and remains 100% compatible.
