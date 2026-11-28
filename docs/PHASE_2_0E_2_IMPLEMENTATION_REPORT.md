# Phase 2.0E.2 Implementation Report — Human Review Integrity Remediation

**Repository:** `harshilsetty/BidGuard-AI` (`main` @ `2c3a9b1abbf0a752a7ca69f973525f06956b9d38`)  
**Audit Addressed:** `docs/PHASE_2_0E_1_ACCEPTANCE_AUDIT.md`  
**Schema Changes:** None required (reused existing `0013_human_review_decisions` schema).

---

## 1. Finding-by-Finding Remediation Summary

### P1-1 — Review-Queue Route Shadowing (**FIXED**)
- **Root Cause:** `tenders.py` mounted `GET /{tender_id}/review-queue` before `verification_intelligence.py` in `router.py`, shadowing Phase 8.4 `OfficerReviewQueueResponse`.
- **Fix:** Renamed TenderLens endpoint in `backend/app/api/v1/tenders.py` to `GET /{tender_id}/tenderlens-review-queue` and aligned `fetchTenderLensReviewQueue` in `frontend/src/lib/api-client.ts` and `backend/test_phase2_0e_human_review.py`. Phase 8.4 `GET /api/v1/tenders/{tender_id}/review-queue` remains intact.

### P1-2 & P2-2 — Source-Version Integrity & Review Invalidation (**FIXED**)
- **Root Cause:** `verify_and_get_provenance` set `SOURCE_CHANGED` without invalidating previously `CONFIRMED`/`REJECTED` requirements, conflicts, or evidence mappings; `tender_processing_worker.py` did not capture/verify `source_document_sha256` at extraction time.
- **Fix:**
  - `backend/app/services/tender_processing_worker.py`: verifies stored file SHA-256 against DB `sha256_hash` at extraction start and before finalizing (raising `SOURCE_CHANGED_DURING_EXTRACTION` if mutated mid-run), populates `source_document_sha256` on newly extracted `TenderRequirement` rows, and invalidates older-hash reviewed requirements.
  - `backend/app/services/review_service.py`: added atomic, idempotent `TenderReviewService.invalidate_for_source_change(...)` transitioning stale `CONFIRMED`/`REJECTED`/`NEEDS_CLARIFICATION`/`DISMISSED`/`RESOLVED` requirements, conflicts, and evidence mappings to `NEEDS_REVIEW`, incrementing `review_version`, and appending `SOURCE_INVALIDATED` `ReviewDecision` + `AuditLog` entries while preserving all historical decisions.
  - Wired into `requirement_provenance_service.py`, `requirement_conflict_service.py` (when underlying conflict material changes), and `requirement_evidence_service.py` (when requirement passage changes).

### P2-1 — Reviewer Assignment Authorization (**FIXED**)
- **Root Cause:** `TenderReviewService.assign_reviewer` checked active org membership without checking `evaluation:override` permission.
- **Fix:** `backend/app/services/review_service.py` now loads live `UserRole -> Role -> RolePermission -> Permission` relations for the assignee and rejects targets lacking `evaluation:override` (or `SUPER_ADMIN`) with `403 Forbidden`.

### P3-1 — Frontend Reviewer Assignment UI (**FIXED**)
- **Fix:** Added `assignTenderReviewer` in `frontend/src/lib/api-client.ts` and compact reviewer display + eligible-reviewer selector + `Assign`/`Reassign` controls in `frontend/src/components/TenderReviewWorkspace.tsx`, gated by `hasPermission("user:manage")`, with `submittingId` double-submit protection and workspace refresh after mutation.

---

## 2. Exact Files Changed / Added
- Backend: `backend/app/api/v1/tenders.py`, `backend/app/services/review_service.py`, `backend/app/services/requirement_provenance_service.py`, `backend/app/services/requirement_conflict_service.py`, `backend/app/services/requirement_evidence_service.py`, `backend/app/services/tender_processing_worker.py`, `backend/test_phase2_0e_human_review.py`, `backend/test_phase2_0e_2_remediation.py`.
- Frontend: `frontend/src/lib/api-client.ts`, `frontend/src/components/TenderReviewWorkspace.tsx`.
- Docs: `docs/PHASE_2_0E_2_BASELINE_AND_CHANGE_PLAN.md`, `docs/REVIEW_QUEUE_ROUTE_CONTRACT.md`, `docs/SOURCE_VERSION_AND_REVIEW_INVALIDATION_DESIGN.md`, `docs/REVIEWER_ASSIGNMENT_AUTHORIZATION_DESIGN.md`, `docs/PHASE_2_0E_2_EVALUATION.md`, `docs/PHASE_2_0E_2_IMPLEMENTATION_REPORT.md`.

---

## 3. Known Limitations & Remaining Risks
- Frontend assignment UI was verified via TypeScript (`0` errors), unit tests (`13 passed`), and Next.js production build; interactive browser E2E testing of `TenderReviewWorkspace.tsx` was not executed.
- All changes remain uncommitted in the working tree awaiting Phase 2.0E.3 independent acceptance audit.
