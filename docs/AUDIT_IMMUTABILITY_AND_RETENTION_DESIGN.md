# Audit Immutability & Member-Removal Retention Design (Phase 2.0D.2)

## 1. Append-Only Audit Guarantee

- `audit_logs` is protected at the PostgreSQL engine level by `prevent_audit_log_mutation()` and trigger `trg_audit_logs_immutable` (`BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW`).
- Even superuser (`postgres`) and `bidguard_app` sessions cannot `UPDATE` or `DELETE` historical `audit_logs` rows.
- Migration `0012_audit_immutability_sync` reconciles `gem_compliance` and `bidguard_fresh_test` so both enforce identical trigger functions, triggers, and `FORCE ROW LEVEL SECURITY` on `audit_logs`.

---

## 2. Member-Removal Data-Retention Semantics

In `OrganizationService.remove_member`:
- **Never** execute `DELETE FROM users`, because `audit_logs.user_id` (`ON DELETE SET NULL`) would attempt a forbidden `UPDATE` on `audit_logs` and destroy historical actor attribution.
- Instead:
  1. Record `MEMBER_REMOVED` in `audit_logs`.
  2. Delete all `UserRole` assignments for `target.id`.
  3. Revoke all active `RefreshToken` rows for `target.id`.
  4. Anonymize `target.email = f"removed-{target.id}@removed.local"` (freeing the email for future re-invitation) and set `target.is_active = False`.
- **Result:** Removed members immediately lose all access and sessions, historical `audit_logs.user_id` attribution remains intact and immutable, and `list_members` excludes deactivated/removed accounts cleanly (or marks them inactive).
