# Phase 2.0C Baseline & Change Plan: Tender Requirement Intelligence

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Previous Accepted Phase:** Phase 2.0B.2 — Stale-Worker Fencing & Job Ownership Integrity Remediation  
**Scope:** Structured requirement extraction, 10-category taxonomy classification, requirement normalization, asynchronous job integration, APIs, frontend workspace, and honest quality evaluation.

---

## 1. Baseline Audit

### 1.1 Existing Capabilities
- **Multi-Document & Page Pipeline (Phase 2.0A–2.0B.2):**
  - `TenderDocument` stores tenant-isolated PDFs with SHA-256 verification.
  - `TenderDocumentPage` persists page-level digital/OCR text, `word_count`, `extraction_method`, `ocr_confidence`, and `extraction_status` (`SUCCEEDED`, `EMPTY`, `FAILED`).
  - `TenderProcessingJob` provides PostgreSQL-backed `FOR UPDATE SKIP LOCKED` claiming, `ownership_generation` fencing, lease/heartbeat/recovery, and `FORCE ROW LEVEL SECURITY` under `bidguard_app`.
- **Legacy Clause Extraction (`clause_extractor.py` & `TenderClause`):**
  - `TenderClause` (`tender_clauses`) supports 5 categories (`TECHNICAL`, `FINANCIAL`, `STATUTORY`, `EXPERIENCE`, `DELIVERY_SLA`), `is_mandatory: Boolean`, `is_confirmed: Boolean`, and `ComplianceEvaluation` FK.
  - `clause_extractor.py` provides `build_page_windows`, `format_window_text`, and conservative `verify_source_text_presence` token-sequence provenance checking.
  - `nvidia_client.py` (`get_nvidia_client()`) wraps `AsyncOpenAI` against `settings.NVIDIA_BASE_URL` / `settings.NVIDIA_MODEL` (`openai/gpt-oss-20b`, `NVIDIA_API_KEY` configured).
- **Sample Fixtures:**
  - `backend/sample_data/sample_gem_tender.pdf`: 4-page digital GeM tender (`DIGITAL_TEXT`, 258 total words across 4 pages) containing statutory, turnover, server technical specs, past experience, certifications, OEM authorization, delivery schedule, liquidated damages, and payment terms.
  - Golden Demo fixtures & tests (`test_golden_demo_frozen_regression.py`) rely on `TenderClause` and `ComplianceEvaluation`.

### 1.2 Missing Capabilities
- No 10-category + `UNCLASSIFIED` TenderLens taxonomy (`ELIG`, `TECH`, `FIN`, `STAT`, `EXP`, `DOC`, `DEL`, `SUB`, `DATE`, `PREF`).
- No `TenderRequirement` data model capturing: `source_document_id`, `source_page_number`, `source_page_range`, `source_section`, `normalized_statement`, `explanatory_interpretation`, `requirement_type`, `mandatory_status` (`MANDATORY | OPTIONAL | UNCLEAR`), evidence expectations (`expected_document_or_evidence`, `expected_action_by_bidder`, `numeric_value`, `unit`, `currency`, `period_or_validity`, `conditions_and_exceptions`), `extraction_confidence`, `review_status` (`DRAFT | CONFIRMED | REJECTED | NEEDS_REVIEW | SUPERSEDED`), `extraction_version`, and `processing_job_id`.
- No asynchronous `REQUIREMENT_EXTRACTION` job execution or API endpoints (`/extract-requirements`, `/requirement-jobs/{job_id}`, `/requirements`, `/requirements/{requirement_id}`).
- No TenderLens Requirements Intelligence UI panel in the frontend tender workspace.

### 1.3 Compatibility Decision: Dedicated `TenderRequirement` vs Mutating `TenderClause`
- **Decision:** Add a dedicated `TenderRequirement` (`tender_requirements`) ORM model and `TenderRequirementExtractionService`, rather than altering `TenderClause` (`tender_clauses`).
- **Rationale:** `TenderClause` is coupled to `ComplianceEvaluation` and the frozen Golden Demo regression tests. A dedicated `TenderRequirement` table preserves 100% Golden Demo stability while cleanly supporting the full 10-category schema, `extraction_version` separation, `NEEDS_REVIEW` / `UNCLASSIFIED` states, and `FORCE ROW LEVEL SECURITY`.
- **Reused Infrastructure:** Reuses `TenderProcessingJob` (`job_type = 'REQUIREMENT_EXTRACTION'`, `idempotency_key = f'REQUIREMENT_EXTRACTION:{document_id}:v{version}'`), `TenderDocumentPage`, `get_nvidia_client()`, and `build_page_windows` / `verify_source_text_presence`.

---

## 2. Proposed Implementation Changes

1. **Migration (`0010_tender_requirements.py`):**
   - `down_revision = '0009_job_ownership_generation'`
   - Create `tender_requirements` table with indexes on `tender_id`, `source_document_id`, `processing_job_id`, `primary_category`, `mandatory_status`, `review_status`, and `extraction_version`.
   - Add `extracted_count` (`INTEGER NOT NULL DEFAULT 0`) and `extraction_version` (`INTEGER NOT NULL DEFAULT 1`) nullable/defaulted metadata columns on `tender_processing_jobs` (or store in `TenderProcessingJob`).
   - Enable `FORCE ROW LEVEL SECURITY` on `tender_requirements` scoped via `tenders.organization_id` and grant `SELECT, INSERT, UPDATE, DELETE` to `bidguard_app` (if role exists).
2. **Backend Service (`backend/app/services/requirement_extractor.py`):**
   - `TenderRequirementExtractionService` with strict prompt-injection defense, bounded windowing, schema validation, deterministic source-quote verification, conservative deduplication, and draft-only persistence.
3. **Worker Integration (`backend/app/services/tender_processing_worker.py`):**
   - Route `job.job_type == 'REQUIREMENT_EXTRACTION'` cleanly while preserving all Phase 2.0B.2 `ownership_generation` fencing, `PAGE_EXTRACTION` readiness prerequisite, and bounded LLM calls outside DB transactions.
4. **APIs (`backend/app/api/v1/tenders.py` & `backend/app/schemas/tender.py`):**
   - `POST /api/v1/tenders/{tender_id}/documents/{document_id}/extract-requirements` (`202`)
   - `GET /api/v1/tenders/{tender_id}/requirement-jobs/{job_id}`
   - `GET /api/v1/tenders/{tender_id}/requirements` (paginated + filters)
   - `GET /api/v1/tenders/{tender_id}/requirements/{requirement_id}`
5. **Frontend (`frontend/src/components/TenderRequirementsPanel.tsx` & `tenders/[id]/clauses/page.tsx`):**
   - Add extraction trigger, job status polling, draft count, 10-category + mandatory/review filters, and source quotation/interpretation inspection using the BidGuard palette.

---

## 3. Security & Reliability Risks

- **Prompt Injection:** Untrusted tender text could contain adversarial instructions. Mitigated by strict system prompt isolation, Pydantic schema validation, rejecting model-supplied IDs/document IDs (always derived from DB context), and deterministic `verify_source_text_presence` against persisted `TenderDocumentPage` text.
- **Provider Unavailability / Silent Success:** Network/timeout errors must transition the job through `_handle_job_failure` (fenced) rather than marking extraction `SUCCEEDED` with 0 requirements.
- **Re-Extraction Safety:** Re-extracting under a new `extraction_version` must not overwrite existing `CONFIRMED` or `REJECTED` requirements.

---

## 4. Test & Evaluation Strategy

- Unit/integration tests for valid/invalid JSON, schema errors, unknown categories, ambiguous/optional vs mandatory, AND/OR conditions, numeric units, multi-requirement paragraphs, window boundaries, prompt injection, provider timeouts/unavailability, duplicate/concurrent jobs, fencing, and `bidguard_app` RLS.
- Honest evaluation protocol & preliminary measurement on manually reviewed `sample_gem_tender.pdf` pages (`docs/TENDER_REQUIREMENT_EXTRACTION_EVALUATION.md`).
- Full backend `pytest` suite + frontend `tsc --noEmit`, `npm test`, `npm run build`.

---

## 5. Out of Scope

Corrigendum conflict detection, cross-document supersession, full evidence mapping, bidder document matching, bid-readiness scoring, statutory verification, automatic eligibility decisions, full human approval workflow (Phase 2.0E), and external brokers.
