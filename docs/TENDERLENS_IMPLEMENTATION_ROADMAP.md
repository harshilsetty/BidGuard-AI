# TenderLens — Phased Implementation Roadmap (Phase 2.0A–2.0H)

**Golden Demo Guarantee:** All work packages preserve `GEM/2026/B/8912450` fixtures and frozen regression tests (`test_golden_demo_frozen_regression.py`) without modification.

---

| Package | Objective | Dependencies | Backend / DB Scope | Frontend Scope | Acceptance Criteria |
|---|---|---|---|---|---|
| **2.0A — Upload Security & Multi-Doc Foundation** | Remediate `GAP-01`; support NIT, BoQ, Corrigendum PDFs | Phase 1.4 | `0007` migration (`tender_documents`, `tender_document_pages`, RLS); size/magic-byte/basename validation; `sha256_hash` | Multi-doc upload UI + validation error states | Oversized/non-PDF/traversal rejected (`413`/`422`); cross-tenant upload blocked (`404`/`403`) |
| **2.0B — Async Document Processing** | Remediate `GAP-02`; non-blocking extraction with retries | 2.0A | `tender_processing_jobs` table + `BackgroundTasks` worker + `GET /jobs/{job_id}` polling + `asyncio.to_thread` PDF/OCR | Live job progress indicator + retry action on `FAILED` | `POST /extract` returns `202` immediately; duplicate clicks coalesce; failures retry cleanly |
| **2.0C — Requirement Extraction & Classification** | Expand taxonomy (`ELIG`, `DOC`, `SUB`, `DATE`, `PREF`), tables, section hints | 2.0B | `tender_clauses` additive columns; updated `clause_extractor.py` schema + cross-page dedup | Category & obligation filter chips | All 10 requirement categories extracted with validated schemas |
| **2.0D — Provenance, Conflicts & Evidence Mapping** | Page-level provenance + corrigendum conflicts + expected evidence | 2.0C | `tender_requirement_evidences` & `tender_requirement_conflicts` tables + `verify_source_text_presence` flagging | Unverified provenance badges + conflict alerts | Zero invented quotes; unverified items flagged `NEEDS_REVIEW` |
| **2.0E — Human Review & Confirmation** | Side-by-side source page viewer + confirm/edit/reject + audit | 2.0D | `POST /clauses/{id}/review` + `AuditLog` events | Side-by-side source page text + `tender:update` action gating | `AUDITOR`/`BIDDER` read-only (`403` on mutate); every review audited |
| **2.0F — TenderLens Workspace** | Cohesive Tender Intelligence Workspace using `WorkspacePrimitives` | 2.0E | Read endpoints for docs, pages, clauses, conflicts | Unified `/tenders/[id]` workspace tabs | Responsive, keyboard-accessible, RBAC-aware |
| **2.0G — Bid Readiness Assessment** | Transparent 4-part readiness model + dates + checklist | 2.0E | `GET /tenders/{id}/readiness` deterministic service | Readiness breakdown + submission checklist + important dates | 4 separate metrics; zero opaque/fabricated percentages |
| **2.0H — Integration, Regression & Acceptance** | End-to-end verification across all roles & Golden Demo | 2.0A–2.0G | Full `pytest` + PG RLS + Golden Demo regression | `tsc` + `npm test` + `npm run build` | 100% pass across all suites; Golden Demo unchanged |
