# Phase 2.0D Baseline & Change Plan: Provenance, Conflict Detection & Evidence Mapping

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Previous Accepted Phase:** Phase 2.0C — Tender Requirement Intelligence (`0010_tender_requirements`)

---

## 1. Baseline Audit

- **Existing Capabilities:**
  - `TenderDocument` (`PRIMARY_NIT`, `TECHNICAL_SPEC`, `BOQ`, `CORRIGENDUM`, `ANNEXURE`, `OTHER`) with SHA-256 integrity.
  - `TenderDocumentPage` with persisted digital/OCR page text.
  - `TenderProcessingJob` with `ownership_generation` fencing and `FORCE ROW LEVEL SECURITY` under `bidguard_app`.
  - `TenderRequirement` (`tender_requirements`) with 10-category taxonomy, `mandatory_status`, `review_status`, `source_document_id`, `source_page_number`, `source_text`, `source_quote_verified`, and `extraction_version`.
- **Missing Capabilities:**
  - Multi-tier provenance verification (`VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`, `SOURCE_NOT_FOUND`, `SOURCE_CHANGED`, `NEEDS_REVIEW`) and multiple supporting/contextual/contradictory passages (`TenderRequirementSource`).
  - Optional document relationship metadata (`document_date`, `issue_date`, `reference_number`, `related_document_id`, `applicability_scope`, `revision_info`) on `TenderDocument`.
  - Scope-aware cross-document conflict & potential-amendment detection (`TenderRequirementConflictService` + `TenderRequirementConflict`).
  - Source-grounded expected bidder evidence mapping (`TenderRequirementEvidenceService` + `TenderRequirementEvidence`).
- **Live AI Dependency:**
  - Phase 2.0C's configured NVIDIA NIM model (`openai/gpt-oss-20b`) returned `410 Gone`. All Phase 2.0D provenance, conflict detection, and evidence mapping capabilities are designed as **deterministic, source-grounded engines** that operate reliably without requiring an external LLM endpoint.

---

## 2. Migration & Model Plan (`0011_provenance_conflicts_evidence`)

1. **Additive columns on `tender_documents`:** `document_date`, `issue_date`, `reference_number`, `related_document_id` (self-FK `SET NULL`), `applicability_scope`, `revision_info` (all nullable).
2. **Additive columns on `tender_requirements`:** `provenance_status` (default `'UNVERIFIED'`), `source_document_sha256` (nullable).
3. **New table `tender_requirement_sources`:** Multi-passage provenance links (`PRIMARY_SUPPORTING`, `ADDITIONAL_SUPPORTING`, `CONTEXTUAL`, `POTENTIALLY_CONTRADICTORY`).
4. **New table `tender_requirement_conflicts`:** Cross-document conflicts and `POTENTIAL_AMENDMENT` records (`conflict_type`, `severity`, `status`, `relationship_type`, `scope_summary`, `explanation`).
5. **New table `tender_requirement_evidence`:** Expected bidder evidence mappings (`evidence_type`, `expected_document_name`, `evidence_purpose`, `is_mandatory`, `source_passage`, `mapping_method`, `confidence`, `mapping_status`).
6. **PostgreSQL RLS:** `ENABLE` + `FORCE ROW LEVEL SECURITY` on all 3 new tables scoped via `tenders.organization_id`, with `SELECT, INSERT, UPDATE, DELETE` granted to `bidguard_app`.

---

## 3. Execution & Security Strategy

- Bounded deterministic services (no unbounded all-pairs comparisons; partitioned by category/type/subject).
- Preserve all human-reviewed records (`CONFIRMED`, `DISMISSED`, `RESOLVED`, `REJECTED`) during re-runs.
- Enforce `get_authorized_tender`, RBAC (`tender:read` / `tender:update`), and `bidguard_app` RLS.

---

## 4. Out of Scope

Authoritative corrigendum supersession, full human-review workflow (Phase 2.0E), bidder document matching, actual evidence verification, statutory verification, bid-readiness scoring, and external brokers.
