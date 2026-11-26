# Phase 2.0C Implementation Report: Tender Requirement Intelligence

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Module:** TenderLens — Structured Extraction, Classification & Requirement Normalization  
**Verdict:** **ACCEPTED — READY FOR PHASE 2.0D (PENDING AUTHORIZATION)**

---

## 1. Implemented Functionality

### 1.1 Data Model & Migration (`0010_tender_requirements`)
- **`TenderRequirement` (`backend/app/models/tender.py`, `backend/app/models/__init__.py`):**
  - Captures `tender_id`, `source_document_id`, `processing_job_id`, `requirement_code`, `extraction_version`, `source_page_number`, `source_page_range`, `source_section`, `source_text`, `source_quote_verified`, `normalized_statement`, `explanatory_interpretation`, `primary_category` (`ELIG`, `TECH`, `FIN`, `STAT`, `EXP`, `DOC`, `DEL`, `SUB`, `DATE`, `PREF`, `UNCLASSIFIED`), `secondary_categories`, `requirement_type` (13 controlled types), `mandatory_status` (`MANDATORY | OPTIONAL | UNCLEAR`), evidence expectations (`expected_document_or_evidence`, `expected_action_by_bidder`, `numeric_value`, `unit`, `currency`, `period_or_validity`, `conditions_and_exceptions`), `extraction_method`, `model_provider`, `model_version`, `extraction_confidence`, and `review_status` (`DRAFT | CONFIRMED | REJECTED | NEEDS_REVIEW | SUPERSEDED`).
- **Migration (`backend/alembic/versions/0010_tender_requirements.py`):**
  - `down_revision = '0009_job_ownership_generation'`
  - Adds `extracted_count` and `extraction_version` to `tender_processing_jobs`.
  - Creates `tender_requirements` with indexes, `FORCE ROW LEVEL SECURITY` (`tenant_isolation_tender_requirements`), and `bidguard_app` grants. Applied to both `gem_compliance` and `bidguard_fresh_test`.

### 1.2 Extraction Engine & Asynchronous Worker Integration
- **`TenderRequirementExtractionService` (`backend/app/services/requirement_extractor.py`):**
  - Consumes persisted `TenderDocumentPage` rows in 3-page sliding windows (`stride=2`).
  - Treats tender text strictly as untrusted data, validates JSON against `CandidateRequirementSchema`, ignores model-supplied IDs, normalizes unknown categories/statuses to `UNCLASSIFIED`/`UNCLEAR` + `NEEDS_REVIEW`, verifies verbatim quotations via `verify_source_text_presence` (downgrading unverified quotes to `NEEDS_REVIEW` with `confidence <= 0.45`), and conservatively deduplicates overlapping windows.
  - Fails explicitly (`RequirementExtractionProviderError`) on provider timeout/unavailability/invalid JSON rather than silently succeeding.
- **Worker Integration (`backend/app/services/tender_processing_worker.py`):**
  - Routes `job_type == "REQUIREMENT_EXTRACTION"` through `TenderProcessingWorkerManager` with full Phase 2.0B.2 `ownership_generation` fencing, `PAGE_EXTRACTION` `READY` prerequisite, LLM calls outside DB transactions, and re-extraction preservation of existing `CONFIRMED` and `REJECTED` requirements.

### 1.3 APIs & Frontend
- **Backend APIs (`backend/app/api/v1/tenders.py`, `backend/app/schemas/tender.py`):**
  - `POST /api/v1/tenders/{tender_id}/documents/{document_id}/extract-requirements` (`202 Accepted`, `tender:update`)
  - `GET /api/v1/tenders/{tender_id}/requirement-jobs/{job_id}` (`tender:read`)
  - `GET /api/v1/tenders/{tender_id}/requirements` (paginated + `primary_category`, `mandatory_status`, `review_status`, `source_document_id`, `extraction_version` filters, `tender:read`)
  - `GET /api/v1/tenders/{tender_id}/requirements/{requirement_id}` (`tender:read`)
- **Frontend (`frontend/src/components/TenderRequirementsPanel.tsx`, `frontend/src/app/tenders/[id]/clauses/page.tsx`, `frontend/src/lib/types.ts`, `frontend/src/lib/api-client.ts`):**
  - Permission-aware extraction trigger, bounded job polling, draft/`NEEDS_REVIEW` counts, 10-category + obligation + review filters, and expandable source quotation/evidence inspection in the BidGuard design palette.

---

## 2. Tested Functionality & Verification Results

- **Phase 2.0C Requirements Suite (`cd backend; python -m pytest test_phase2_0c_requirements.py -v --tb=short`):**
  - `3 passed, 14 warnings in 7.63s` (schema validation, prompt-injection defense, unverified quote downgrade, async `202` + `409` precondition, coalescing, `v2` re-extraction preserving `CONFIRMED`, cross-tenant denial, and `bidguard_app` PostgreSQL RLS).
- **Complete Backend Suite (`cd backend; python -m pytest -v --tb=short`):**
  - **`337 passed, 26 warnings in 286.02s (0:04:46)`** (`0` failed, `0` errors, `0` skipped), including Phase 2.0A, 2.0B, 2.0B.2 fencing, 2.0C, enterprise auth/RBAC/RLS, and Golden Demo frozen regression.
- **Frontend Verification (`cd frontend; npx tsc --noEmit; npm test; npm run build`):**
  - `npx tsc --noEmit`: `0` errors.
  - `npm test`: `13 passed, 0 failed, 0 skipped` in `113.0131ms`.
  - `npm run build`: `10/10` static pages generated cleanly.

---

## 3. Preliminary Evaluation, Untested Assumptions & Limitations

- **Live LLM Provider Probe (`docs/TENDER_REQUIREMENT_EXTRACTION_EVALUATION.md`):**
  - Configured `settings.NVIDIA_MODEL = "openai/gpt-oss-20b"` returned HTTP `410 Gone` (`end of life on 2026-11-18T08:00:00Z`); alternate `"google/gemma-3-12b-it"` returned `404 Not Found` on the configured NIM account.
  - `TenderRequirementExtractionService` failed safely (`RequirementExtractionProviderError`). Live LLM Precision/Recall remain **unmeasured** until an active NIM chat model is configured.
- **Deferred Capabilities (Out of Scope):**
  - Corrigendum conflict detection, cross-document supersession, evidence mapping, bidder matching, bid-readiness scoring, and full human-review workflow (Phase 2.0D / 2.0E).
