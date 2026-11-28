# Phase 2.0E.1 Concurrency, Atomicity & History Integrity Audit

**Inspected Sources:** `backend/app/services/review_service.py`, `backend/alembic/versions/0013_human_review_decisions.py`, `backend/test_phase2_0e_human_review.py`.

---

## 1. Optimistic Concurrency Strategy
- `TenderReviewService.submit_decision` and `assign_reviewer` execute an atomic conditional SQL `UPDATE`:
  ```sql
  UPDATE <reviewable_table>
  SET <status_col> = :target_status, review_version = :expected_version + 1, ...
  WHERE id = :object_id AND tender_id = :tender_id AND review_version = :expected_version
  ```
- Under PostgreSQL `READ COMMITTED`, two concurrent transactions targeting the same row acquire a row-level lock on `UPDATE`. The first commits `review_version = expected_version + 1`; the second re-evaluates the `WHERE review_version = expected_version` predicate, observes `res.rowcount == 0`, executes `await db.rollback()`, and raises `409 Conflict`.

### Empirical Scenario Verification (`bidguard_fresh_test`)
- **Scenario A (Sequential stale version, `test_phase2_0e_human_review.py`):** First reviewer succeeds (`200`, `v2 -> v3`); second reviewer with `expected_version=2` receives `409 Conflict`.
- **Scenario B (Concurrent `asyncio.gather`, audit probe):** Two simultaneous `POST /review-decisions` requests on `expected_version=1` returned `[200, 409]`, with exactly 1 `ReviewDecision` row persisted.
- **Scenario C (Duplicate retry, audit probe):** Re-submitting the identical `CONFIRM` request with `expected_version=1` returned `409 Conflict` (`Cannot apply 'CONFIRM' from status 'CONFIRMED' on REQUIREMENT.`), and `ReviewDecision` count remained `1`.
- **Scenario D (Removed member stale JWT, audit probe):** After `OrganizationService.remove_member`, `POST /review-decisions` with the removed user's unexpired JWT returned `403 Forbidden` (`User account is deactivated.`).

---

## 2. Transaction Atomicity & Append-Only History
- **Single-transaction boundary:** In `submit_decision` (`review_service.py:142-187`) and `assign_reviewer` (`review_service.py:239-286`), the conditional `UPDATE`, `ReviewDecision` insert, and `AuditLog` insert all occur on the same `AsyncSession` before a single `await db.commit()`.
- If `res.rowcount != 1`, `await db.rollback()` is executed before any `ReviewDecision` or `AuditLog` is added or committed, preventing partial writes or audit entries for failed decisions.
- **Immutability:** `review_decisions` is protected by PostgreSQL trigger `trg_review_decisions_immutable` (`BEFORE UPDATE OR DELETE`). Verified under `bidguard_app` (`NOSUPERUSER`, `NOBYPASSRLS`) with `app.is_super_admin = 'true'` that both `UPDATE` and `DELETE` fail with `review_decisions is append-only`.
