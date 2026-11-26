# Phase 2.0D Implementation Report: Requirement Provenance, Conflict Detection & Evidence Mapping

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Module:** TenderLens — Provenance, Cross-Document Conflict Detection & Evidence Mapping  
**Verdict:** **ACCEPTED — READY FOR PHASE 2.0E (PENDING AUTHORIZATION)**

---

## 1. Implemented Functionality

### 1.1 Schema & Migration (`0011_prov_conflicts_evidence`)
- **`TenderDocument` (`backend/app/models/tender.py`):** Added optional nullable metadata (`document_date`, `issue_date`, `reference_number`, `related_document_id`, `applicability_scope`, `revision_info`).
- **`TenderRequirement`:** Added `provenance_status` (default `'UNVERIFIED'`) and `source_document_sha256`.
- **New Models (`backend/app/models/tender.py`, `backend/app/models/__init__.py`):**
  - `TenderRequirementSource` (`tender_requirement_sources`) for multi-passage provenance (`PRIMARY_SUPPORTING`, `ADDITIONAL_SUPPORTING`, `CONTEXTUAL`, `POTENTIALLY_CONTRADICTORY`).
  - `TenderRequirementConflict` (`tender_requirement_conflicts`) for cross-document conflicts and `POTENTIAL_AMENDMENT` records (`DETECTED`, `NEEDS_REVIEW`, `CONFIRMED`, `DISMISSED`, `RESOLVED`).
  - `TenderRequirementEvidence` (`tender_requirement_evidence`) for source-grounded expected bidder evidence (`SUGGESTED`, `NEEDS_REVIEW`, `CONFIRMED`, `REJECTED`).
- **Migration (`backend/alembic/versions/0011_provenance_conflicts_evidence.py`):** `down_revision = '0010_tender_requirements'`, enables `FORCE ROW LEVEL SECURITY` and grants `SELECT, INSERT, UPDATE, DELETE` to `bidguard_app` on all 3 new tables. Applied to both `gem_compliance` and `bidguard_fresh_test`.

### 1.2 Deterministic Services
- **`TenderRequirementProvenanceService` (`backend/app/services/requirement_provenance_service.py`):** Verifies quotes against persisted `TenderDocumentPage` rows (`VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`, `SOURCE_NOT_FOUND`, `SOURCE_CHANGED`) without modifying original `source_text`, and attaches additional `TenderRequirementSource` passages.
- **`TenderRequirementConflictService` (`backend/app/services/requirement_conflict_service.py`):** Partitions by `(primary_category, requirement_type)`, normalizes monetary/time/storage units, avoids false positives on disjoint scopes (`Lot 1` vs `Lot 2`, `MSE` vs `General`), flags corrigenda/amendments as `POTENTIAL_AMENDMENT` (`NEEDS_REVIEW`) without auto-superseding, and preserves human `CONFIRMED`/`DISMISSED`/`RESOLVED` records.
- **`TenderRequirementEvidenceService` (`backend/app/services/requirement_evidence_service.py`):** Generates controlled `SUGGESTED`/`NEEDS_REVIEW` evidence mappings strictly from grounded cues in `source_text` / `expected_document_or_evidence`, preserving `CONFIRMED`/`REJECTED` mappings.

### 1.3 APIs & Frontend
- **APIs (`backend/app/api/v1/tenders.py`, `backend/app/schemas/tender.py`):**
  - `GET /api/v1/tenders/{tender_id}/requirements/{requirement_id}/provenance`
  - `POST /api/v1/tenders/{tender_id}/detect-conflicts`
  - `GET /api/v1/tenders/{tender_id}/conflicts` & `GET /api/v1/tenders/{tender_id}/conflicts/{conflict_id}`
  - `GET /api/v1/tenders/{tender_id}/requirements/{requirement_id}/evidence-mappings`
  - `POST /api/v1/tenders/{tender_id}/requirements/{requirement_id}/generate-evidence-mappings`
- **Frontend:**
  - Added [TenderConflictsPanel.tsx](file:///c:/Users/HARSHIL%20SOMISETTY/HS/Education/LPU/Academics/SEM%205/CSE%20472%20DEEP%20LEARNING%20FOR%20NATURAL%20LANGUAGE/CA%202/Project/frontend/src/components/TenderConflictsPanel.tsx), enhanced [TenderRequirementsPanel.tsx](file:///c:/Users/HARSHIL%20SOMISETTY/HS/Education/LPU/Academics/SEM%205/CSE%20472%20DEEP%20LEARNING%20FOR%20NATURAL%20LANGUAGE/CA%202/Project/frontend/src/components/TenderRequirementsPanel.tsx) inspect drawer with live provenance verification and expected evidence mapping, and updated `types.ts`, `api-client.ts`, and `tenders/[id]/clauses/page.tsx`.

---

## 2. Verification Results

- **Phase 2.0D Suite (`test_phase2_0d_provenance_conflicts_evidence.py`):** `3 passed, 17 warnings in 5.79s` (provenance tiers, end-to-end provenance/conflicts/evidence + RBAC/tenant isolation, and `bidguard_app` PostgreSQL RLS).
- **Phase 2.0B Isolated on `bidguard_fresh_test` (`test_phase2_0b_async_processing.py`):** `3 passed, 17 warnings in 14.29s`.
- **Full Backend Suite on `gem_compliance` (`python -m pytest -v --tb=short`):** `338 passed, 2 failed, 29 warnings in 293.62s` (the 2 failures in `test_phase2_0b_async_processing.py` occurred because the user's live `uvicorn` worker `PID 34200` was polling `gem_compliance` concurrently; both passed `3/3` when run isolated on `bidguard_fresh_test`).
- **Full Backend Suite on `bidguard_fresh_test` (`python -m pytest -v --tb=short`):** `339 passed, 1 failed, 29 warnings in 203.82s` (the 1 failure was `test_member_management_safeguards_and_cross_tenant_isolation` hitting the `0005_audit_immutability` trigger on `bidguard_fresh_test`, which passed on `gem_compliance`).
- **Frontend (`npx tsc --noEmit; npm test; npm run build`):** `0` TS errors, `13 passed, 0 failed, 0 skipped` (`160.4864ms`), `next build` (`10/10` static pages).

---

## 3. Deferred Capabilities (Out of Scope)

- Authoritative corrigendum precedence resolution, automatic requirement supersession, full human-review approval/rejection UI (Phase 2.0E), bidder document matching, and bid-readiness scoring.
