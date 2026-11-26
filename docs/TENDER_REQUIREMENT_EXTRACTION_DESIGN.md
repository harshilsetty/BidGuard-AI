# TenderLens Requirement Extraction Design (Phase 2.0C)

## 1. End-to-End Architecture

```
TenderDocumentPage (extraction_status='SUCCEEDED')
        │  [bounded 3-page sliding windows, stride=2]
        ▼
TenderRequirementExtractionService
  ├── Untrusted-data prompt framing + 10-category JSON schema
  ├── NvidiaClient.chat() (outside DB transactions, timeout + bounded retry)
  ├── Strict Pydantic validation + enum normalization
  ├── Deterministic source-quote check (verify_source_text_presence)
  ├── Conservative deduplication across overlapping windows
  └── Draft persistence -> TenderRequirement (review_status = DRAFT / NEEDS_REVIEW)
```

---

## 2. Prompt-Injection Resistance & Grounding Controls

1. **Data-Only Framing:** Page text is wrapped in explicit `=== PAGE X START ===` / `=== PAGE X END ===` delimiters with system instructions directing the model to ignore any directives embedded in document text.
2. **Untrusted Identifiers:** Model-returned `tender_id`, `document_id`, or arbitrary IDs are ignored; `tender_id`, `source_document_id`, and `processing_job_id` are derived strictly from the authorized job context.
3. **Schema & Enum Validation:** Malformed JSON or invalid field types are rejected cleanly. Unknown categories normalize to `UNCLASSIFIED` + `NEEDS_REVIEW`; invalid obligation statuses normalize to `UNCLEAR` + `NEEDS_REVIEW`.
4. **Source Quotation Verification:** Each candidate `source_text` is checked with `verify_source_text_presence(source_text, window)`.
   - If verified on a page in the window, `source_page_number` is anchored to that exact verified page.
   - If the quote cannot be verified verbatim (e.g., minor OCR/whitespace drift or ungrounded phrasing), the requirement is either rejected (if empty/fabricated) or flagged `NEEDS_REVIEW` with lowered confidence (`<= 0.45`) and `source_quote_verified = false` rather than silently treated as high-confidence grounded fact.

---

## 3. Asynchronous Job Integration

- Reuses `tender_processing_jobs` with `job_type = 'REQUIREMENT_EXTRACTION'`.
- **Prerequisite:** `TenderDocument.processing_status == 'READY'` and at least one persisted `TenderDocumentPage` exists; otherwise `/extract-requirements` returns `409 Conflict`.
- **Versioning & Idempotency:**
  - `idempotency_key = f"REQUIREMENT_EXTRACTION:{document_id}:v{extraction_version}"`.
  - Duplicate active requests (`QUEUED`, `RUNNING`, `RETRY_WAIT`) coalesce to the existing job (`202 Accepted`).
  - Re-extraction (`reextract=true` or next version) computes `next_version = max(existing_version) + 1`, preserving prior `CONFIRMED` / `REJECTED` requirements.
- **Fencing & RLS:** Executes through `TenderProcessingWorkerManager` with the exact `ownership_generation` fencing and `bidguard_app` `FORCE ROW LEVEL SECURITY` guarantees from Phase 2.0B.2.

---

## 4. Database Schema (`tender_requirements`)

- `id` (UUID PK), `tender_id` (FK `tenders.id`), `source_document_id` (FK `tender_documents.id`), `processing_job_id` (FK `tender_processing_jobs.id`), `requirement_code` (e.g. `FIN-01`), `extraction_version` (Integer, default 1).
- `source_page_number` (Integer), `source_page_range` (String(32), nullable), `source_section` (String(200), nullable).
- `source_text` (Text), `source_quote_verified` (Boolean), `normalized_statement` (Text), `explanatory_interpretation` (Text).
- `primary_category` (String(32)), `secondary_categories` (JSON list), `requirement_type` (String(50)), `mandatory_status` (String(20)).
- Evidence fields: `expected_document_or_evidence` (Text, nullable), `expected_action_by_bidder` (Text, nullable), `numeric_value` (String(64), nullable), `unit` (String(64), nullable), `currency` (String(16), nullable), `period_or_validity` (String(128), nullable), `conditions_and_exceptions` (Text, nullable).
- Metadata: `extraction_method` (String(50)), `model_provider` (String(64)), `model_version` (String(128)), `extraction_confidence` (Float), `review_status` (String(32), default `'DRAFT'`).
- `FORCE ROW LEVEL SECURITY` policy `tenant_isolation_tender_requirements` matching `tenders.organization_id`.
