# Append-Only Review Decision History Design (Phase 2.0E)

## 1. Dedicated `review_decisions` Model

`ReviewDecision` (`review_decisions`) records every human review, reopening, and assignment event:
- `id` (UUID PK), `organization_id` (UUID FK `organizations.id`), `tender_id` (UUID FK `tenders.id`), `object_type` (`REQUIREMENT | CONFLICT | EVIDENCE`), `object_id` (UUID), `reviewer_user_id` (UUID FK `users.id`), `decision_type`, `previous_status`, `new_status`, `rationale`, `object_version`, `source_document_sha256`, `assigned_to_user_id`, `created_at`, `updated_at`.

## 2. Database-Level Immutability & RLS

- Trigger function `prevent_review_decision_mutation()` + `BEFORE UPDATE OR DELETE` trigger `trg_review_decisions_immutable` reject any mutation with `review_decisions is append-only: % operations are forbidden`.
- `FORCE ROW LEVEL SECURITY` (`tenant_isolation_review_decisions`) enforces tenant isolation under `bidguard_app`.
- Every decision mutation atomically writes both `ReviewDecision` and `AuditLog` in the same DB transaction; failed or stale-version mutations roll back completely.
