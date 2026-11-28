# Phase 2.0E.2 Baseline and Change Plan

**Baseline Branch / HEAD:** `main` @ `2c3a9b1abbf0a752a7ca69f973525f06956b9d38`  
**Audit Baseline:** `docs/PHASE_2_0E_1_ACCEPTANCE_AUDIT.md` (Verdict: FAIL)  
**Database Revisions:** `gem_compliance` and `bidguard_fresh_test` both at `0013_human_review_decisions` (no schema migration required; existing columns `review_version`, `review_status`, `provenance_status`, `source_document_sha256`, `assigned_reviewer_id`, and `review_decisions` are sufficient).

---

## Planned Changes (Strictly Scoped to P1-1, P1-2, P2-1, P2-2, P3-1)
1. **P1-1 (Route Shadowing):** Rename TenderLens review-queue route in `backend/app/api/v1/tenders.py` from `/{tender_id}/review-queue` to `/{tender_id}/tenderlens-review-queue` and align `frontend/src/lib/api-client.ts` (`fetchTenderLensReviewQueue`) and `backend/test_phase2_0e_human_review.py`. Phase 8.4 `GET /api/v1/tenders/{tender_id}/review-queue` in `verification_intelligence.py` remains untouched.
2. **P1-2 & P2-2 (Source-Version Integrity & Invalidation):**
   - In `backend/app/services/tender_processing_worker.py`, verify the stored document SHA-256 against the actual file (when present on disk) at extraction start and again before publishing requirements, persist `source_document_sha256` on newly extracted `TenderRequirement` rows, abort publishing if the source changed mid-extraction, and trigger source-version invalidation if a document's SHA-256 changed.
   - In `backend/app/services/review_service.py` (`invalidate_for_source_change`), `requirement_provenance_service.py`, `requirement_conflict_service.py`, and `requirement_evidence_service.py`: when a source SHA-256 changes or `provenance_status == "SOURCE_CHANGED"`, preserve all historical `ReviewDecision` rows, atomically transition previously reviewed (`CONFIRMED`, `REJECTED`, `NEEDS_CLARIFICATION`, `DISMISSED`, `RESOLVED`) requirements, dependent conflicts, and evidence mappings to `NEEDS_REVIEW`, increment `review_version`, and record a single idempotent `SOURCE_INVALIDATED` `ReviewDecision` + `AuditLog` entry.
3. **P2-1 (Reviewer Assignment Authorization):** In `TenderReviewService.assign_reviewer`, load the assignee's live `UserRole -> Role -> RolePermission -> Permission` relations and require `evaluation:override` (or `SUPER_ADMIN`), rejecting unauthorized/inactive/cross-tenant targets with `403`/`404`.
4. **P3-1 (Frontend Reviewer Assignment UI):** Add `assignTenderReviewer` to `frontend/src/lib/api-client.ts` and integrate compact reviewer display, eligible-reviewer selector, and assignment/reassignment controls in `frontend/src/components/TenderReviewWorkspace.tsx` gated by `hasPermission("user:manage")`.
