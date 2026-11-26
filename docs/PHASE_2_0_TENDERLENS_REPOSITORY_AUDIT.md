# PHASE 2.0: TENDERLENS REPOSITORY & BASELINE AUDIT

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**Base Commit SHA:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Audit Scope:** Stage A verification of existing tender, PDF/OCR, clause extraction, evidence, scoring, RBAC, and frontend capabilities prior to TenderLens Phase 2.0A.

---

## 1. Confirmed Phase 1.4 P1 Findings (Verified Against Current Source)

| ID | Classification | Code Location | Verified Reality |
|---|---|---|---|
| **GAP-01** | **Confirmed Defect (P1)** | `backend/app/api/v1/tenders.py` (`upload_tender_pdf`, L51–68) | Only checks `file.filename.lower().endswith(".pdf")`. Does **not** sanitize `file.filename` via `os.path.basename()`, does **not** validate `%PDF-` magic bytes, and does **not** enforce `settings.MAX_UPLOAD_SIZE_MB` (50 MB) during `await file.read()`. |
| **GAP-02** | **Confirmed Defect (P1)** | `backend/app/api/v1/tenders.py` (`extract_tender_clauses`, L116–140) | Sets `extraction_status = "EXTRACTING"`, commits, and executes `await extract_clauses_from_tender_pages(...)` synchronously inside the HTTP request lifecycle, risking gateway/client timeouts on large NIT PDFs. |

---

## 2. Capability Classification Matrix

| Capability | Classification | Observed Evidence |
|---|---|---|
| **Enterprise Auth, RBAC & RLS** | **Existing Capability** | In-memory JWT + rotating HttpOnly cookie (`bidguard_refresh_token`), `require_permission(...)`, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` across 13 tables, `trg_audit_logs_immutable`. |
| **Role-Based Frontend Shell** | **Existing Capability** | `AppShell.tsx`, `AuthGate.tsx`, `WorkspacePrimitives.tsx`, `rbac.ts`, `/organization`, `/audit`, `/invite/accept`, `/login`. |
| **Single-PDF Tender Upload** | **Partially Implemented** | `POST /api/v1/tenders/upload` creates 1 `Tender` with single `file_name`/`file_path` (`tenders` table); no multi-document (`NIT` + `BoQ` + `Corrigendum`) child model yet. |
| **Digital + OCR Page Extraction** | **Existing Capability** | `backend/app/services/pdf_extractor.py` uses PyMuPDF (`>=10` alnum words -> `DIGITAL_TEXT`), 200 DPI rasterization, `is_pixmap_blank()`, and PaddleOCR (`OCR_PROCESSED`, `OCR_LOW_CONFIDENCE`, `OCR_FAILED`, `EMPTY_SCANNED`). |
| **LLM Sliding-Window Extraction** | **Existing Capability** | `backend/app/services/clause_extractor.py` processes 3-page windows (`stride=2`), NVIDIA NIM GPT-OSS 20B JSON output, 5 categories (`TECHNICAL`, `FINANCIAL`, `STATUTORY`, `EXPERIENCE`, `DELIVERY_SLA`), `mandatory_status` (`MANDATORY`/`OPTIONAL`/`UNCLEAR`), and `verify_source_text_presence()`. |
| **Human Clause Review & Confirmation** | **Partially Implemented** | `/tenders/[id]/clauses` supports manual add, edit, delete, mandatory toggle, and `POST /confirm`, but lacks `hasPermission("tender:update")` action gating, rejection reason tracking, and side-by-side source PDF/page viewer. |
| **Evidence & Vector Retrieval** | **Existing Capability** | `document_chunks` (`Vector(2048)`), `embedding_service.py` (Nemotron 2048-dim), `evidence_retrieval.py`, `evidence_fusion_service.py`. |
| **Deterministic Scoring & Golden Demo** | **Existing Capability** | `GEM/2026/B/8912450` frozen regression (`100.00 / 53.41 / 47.95` standalone; `90.45 / 40.45 / 34.77` fused). |
| **Corrigenda & Conflict Detection** | **Missing Capability** | No multi-document ingestion, corrigendum override linkage, or cross-document contradiction model for tenders. |
| **Bid Readiness Assessment Engine** | **Missing Capability** | No pre-bid readiness model separating extraction completeness, review progress, evidence expectation coverage, and important dates/checklists. |
| **Async Job Queue & Retry State** | **Missing Capability** | No `tender_processing_jobs` table, idempotency keys, or status polling endpoints. |

---

## 3. Baseline Verification Status

- Frontend: `npx tsc --noEmit` (`0` errors), `npm test` (`11/11` passed), `npm run build` (`10/10` static pages).
- Backend: `326` tests in full suite + `25/25` Phase 1.4 E2E journeys, enterprise security, RLS, and Golden Demo regression passing against PostgreSQL 16.15 + `pgvector` 0.8.6.
- No application code or migrations were modified in Phase 2.0.
