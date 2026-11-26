# TenderLens — Data Model & API Specification (Phase 2.0)

---

## 1. Proposed Forward Schema Extensions (Alembic `0007+`)

### 1.1 `tender_documents`
- `id` (UUID PK), `tender_id` (FK `tenders.id` CASCADE, indexed)
- `document_role` (`PRIMARY_NIT` | `TECHNICAL_SPEC` | `BOQ` | `CORRIGENDUM` | `ANNEXURE`)
- `original_filename` (String 255, sanitized), `storage_path` (String 1000)
- `file_size_bytes` (BigInt), `sha256_hash` (String 64, indexed)
- `total_pages` (Integer), `processing_status` (`UPLOADED` | `QUEUED` | `PROCESSING` | `READY` | `FAILED`)
- `created_at`, `updated_at`

### 1.2 `tender_document_pages`
- `id` (UUID PK), `tender_document_id` (FK `tender_documents.id` CASCADE, indexed)
- `page_number` (Integer), `section_heading` (String 300, nullable)
- `extracted_text` (Text), `word_count` (Integer)
- `extraction_method` (`DIGITAL_TEXT` | `OCR_PROCESSED` | `OCR_LOW_CONFIDENCE` | `OCR_FAILED` | `EMPTY_SCANNED`)
- `ocr_confidence` (Numeric 4,3, nullable)

### 1.3 `tender_processing_jobs`
- `id` (UUID PK), `tender_id` (FK `tenders.id` CASCADE), `tender_document_id` (FK `tender_documents.id` CASCADE, nullable)
- `job_type` (`PAGE_EXTRACTION` | `REQUIREMENT_EXTRACTION` | `CONFLICT_ANALYSIS`)
- `status` (`QUEUED` | `RUNNING` | `SUCCEEDED` | `FAILED`)
- `idempotency_key` (String 128, unique)
- `retry_count` (Integer, default 0), `max_retries` (Integer, default 3)
- `progress_pct` (Integer, default 0), `error_message` (Text, nullable)
- `started_at`, `completed_at`, `created_at`

### 1.4 `tender_clauses` (Additive Columns Preserving Golden Demo)
- `source_document_id` (FK `tender_documents.id` SET NULL, nullable)
- `page_end` (Integer, nullable), `section_heading` (String 300, nullable)
- `obligation` (`MANDATORY` | `OPTIONAL` | `UNCLEAR`, default `MANDATORY`)
- `normalized_interpretation` (Text, nullable)
- `extraction_confidence` (Numeric 4,3, nullable)
- `provenance_verified` (Boolean, default True)
- `verification_status` (`DRAFT` | `CONFIRMED` | `REJECTED` | `NEEDS_REVIEW` | `SUPERSEDED`, default `DRAFT`)
- `rejection_reason` (Text, nullable), `reviewed_by_user_id` (UUID FK `users.id` SET NULL, nullable), `reviewed_at` (DateTime TZ, nullable)

### 1.5 `tender_requirement_evidences` & `tender_requirement_conflicts`
- `tender_requirement_evidences`: `id`, `clause_id` (FK `tender_clauses.id`), `expected_document_type`, `description`, `evidence_state` (`EXPECTED` | `UPLOADED` | `EXTRACTED` | `VERIFIED` | `MISSING` | `CONTRADICTORY` | `AWAITING_REVIEW`).
- `tender_requirement_conflicts`: `id`, `tender_id`, `primary_clause_id`, `conflicting_clause_id`, `conflict_type` (`CORRIGENDUM_OVERRIDE` | `VALUE_CONTRADICTION` | `TIMELINE_MISMATCH`), `resolution_status` (`OPEN` | `RESOLVED_KEEP_PRIMARY` | `RESOLVED_KEEP_CORRIGENDUM`), `resolution_note`.

---

## 2. API Endpoint Specifications (All Tenant-Scoped via `get_authorized_tender`)

| Endpoint | Method | Permission | Purpose |
|---|---|---|---|
| `/api/v1/tenders/{id}/documents` | `POST` | `tender:update` | Upload NIT/BoQ/Corrigendum PDF with size/MIME/hash validation |
| `/api/v1/tenders/{id}/documents` | `GET` | `tender:read` | List uploaded tender documents and page extraction statuses |
| `/api/v1/tenders/{id}/documents/{doc_id}/pages/{page_num}` | `GET` | `tender:read` | Retrieve extracted page text & provenance metadata for side-by-side viewer |
| `/api/v1/tenders/{id}/extract` | `POST` | `tender:update` | Enqueue async extraction job (`202 Accepted` + `job_id`) |
| `/api/v1/tenders/{id}/jobs/{job_id}` | `GET` | `tender:read` | Poll background job status, progress, and retry/error details |
| `/api/v1/tenders/{id}/clauses/{clause_id}/review` | `POST` | `tender:update` | Confirm, edit, or reject requirement with audit trail |
| `/api/v1/tenders/{id}/readiness` | `GET` | `tender:read` | Return 4-part deterministic Bid Readiness profile, milestones, checklist, and conflicts |
| `/api/v1/tenders/{id}/conflicts/{conflict_id}/resolve` | `POST` | `tender:update` | Resolve corrigendum or cross-document contradiction |
