# Review State Transitions & Optimistic Concurrency (Phase 2.0E)

## 1. Allowed State Transitions

### 1.1 `REQUIREMENT` (`TenderRequirement.review_status`)
- From `DRAFT`, `NEEDS_REVIEW`, `NEEDS_CLARIFICATION` -> `CONFIRMED` (`CONFIRM`), `REJECTED` (`REJECT`), `NEEDS_CLARIFICATION` (`REQUEST_CLARIFICATION`).
- From `CONFIRMED`, `REJECTED` -> `NEEDS_REVIEW` (`REOPEN`, requires rationale).
- **Source Change Invalidation:** If `provenance_status == 'SOURCE_CHANGED'`, `CONFIRM` is blocked (`409 Conflict`) until reopened/re-verified.

### 1.2 `CONFLICT` (`TenderRequirementConflict.status`)
- From `DETECTED`, `NEEDS_REVIEW` -> `CONFIRMED` (`CONFIRM`), `DISMISSED` (`DISMISS`), `RESOLVED` (`RESOLVE`).
- From `CONFIRMED` -> `RESOLVED` (`RESOLVE`), `DISMISSED` (`DISMISS`), `NEEDS_REVIEW` (`REOPEN`).
- From `DISMISSED`, `RESOLVED` -> `NEEDS_REVIEW` (`REOPEN`, requires rationale).

### 1.3 `EVIDENCE` (`TenderRequirementEvidence.mapping_status`)
- From `SUGGESTED`, `NEEDS_REVIEW` -> `CONFIRMED` (`CONFIRM`), `REJECTED` (`REJECT`).
- From `CONFIRMED`, `REJECTED` -> `NEEDS_REVIEW` (`REOPEN`, requires rationale).

---

## 2. Optimistic Concurrency (`review_version`)

- Every reviewable object has `review_version INTEGER NOT NULL DEFAULT 1`.
- Mutations require `expected_version` and execute an atomic `UPDATE ... WHERE id = :id AND tender_id = :tender_id AND review_version = :expected_version` incrementing `review_version = review_version + 1`.
- If `rowcount == 0`, the transaction rolls back (no `ReviewDecision` or `AuditLog` written) and returns `409 Conflict`.
