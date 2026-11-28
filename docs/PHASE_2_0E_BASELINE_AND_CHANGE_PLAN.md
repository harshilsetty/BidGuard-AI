# Phase 2.0E Baseline & Change Plan: Human Review & Decision Workflows

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `2c3a9b1abbf0a752a7ca69f973525f06956b9d38`  
**Previous Accepted Phase:** Phase 2.0D.2 (`0012_audit_immutability_sync`)

---

## 1. Baseline Inspection

- **Reviewable Models:**
  - `TenderRequirement` (`tender_requirements`): `review_status` (`DRAFT`, `NEEDS_REVIEW`, `CONFIRMED`, `REJECTED`, `SUPERSEDED`).
  - `TenderRequirementConflict` (`tender_requirement_conflicts`): `status` (`DETECTED`, `NEEDS_REVIEW`, `CONFIRMED`, `DISMISSED`, `RESOLVED`), `reviewed_by_user_id`, `reviewed_at`.
  - `TenderRequirementEvidence` (`tender_requirement_evidence`): `mapping_status` (`SUGGESTED`, `NEEDS_REVIEW`, `CONFIRMED`, `REJECTED`).
- **RBAC (`backend/app/services/rbac_service.py`):**
  - `ORG_ADMIN` / `SUPER_ADMIN`: `user:manage`, `evaluation:override`, `tender:read`, `audit:read`.
  - `PROCUREMENT_OFFICER`: `evaluation:override`, `tender:read`, `audit:read`.
  - `AUDITOR`: `tender:read`, `evaluation:read`, `audit:read` (read-only).
  - `BIDDER`: `tender:read`, `evaluation:read` (no `audit:read`).
- **Account-Lifecycle Verification (Section 1 Check):**
  - `User.organization_id` is `NOT NULL` (`backend/app/models/user.py:15-20`), and `User.email` is globally `unique=True`. Each `User` record belongs to exactly one organization, so `OrganizationService.remove_member` deactivating a user cannot affect any membership in another organization. (True multi-org membership per single user record is out of scope for Phase 2.0E.)

---

## 2. Change Plan

1. **Migration `0013_human_review_decisions` (`down_revision = '0012_audit_immutability_sync'`):**
   - Add `review_version` (`INTEGER NOT NULL DEFAULT 1`) and `assigned_reviewer_id` to `tender_requirements`, `tender_requirement_conflicts`, and `tender_requirement_evidence` (plus `last_reviewed_by_user_id`/`last_reviewed_at` on requirements and `reviewed_by_user_id`/`reviewed_at` on evidence).
   - Create append-only `review_decisions` table with `prevent_review_decision_mutation()` + `trg_review_decisions_immutable`, `FORCE ROW LEVEL SECURITY`, and `bidguard_app` privileges.
2. **Service (`backend/app/services/review_service.py`):**
   - Server-side state-transition validation, rationale validation, optimistic concurrency (`WHERE review_version = :expected_version`), atomic `ReviewDecision` + `AuditLog` insertion, assignment/reassignment, reopening, queue filtering, and workload summary.
3. **APIs (`backend/app/api/v1/tenders.py`, `backend/app/schemas/tender.py`):**
   - Consolidated review queue, detail, assignment, decision submission, reopening, immutable history, and workload summary endpoints.
4. **Frontend (`frontend/src/components/TenderReviewWorkspace.tsx`, `tenders/[id]/clauses/page.tsx`):**
   - Consolidated review workspace with summary counts, queue filters, requirement/conflict/evidence review cards, rationale modal/form, optimistic-concurrency error handling, and decision history display.
