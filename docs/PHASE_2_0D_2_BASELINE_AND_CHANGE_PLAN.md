# Phase 2.0D.2 Baseline & Change Plan: Audit Integrity, DB Consistency & Test Reliability

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `2c3a9b1abbf0a752a7ca69f973525f06956b9d38`  

---

## 1. Baseline Inspection Findings

### 1.1 Organization Member Removal (`OrganizationService.remove_member`)
- `User` (`backend/app/models/user.py`) has `organization_id` (`NOT NULL`, `ForeignKey("organizations.id", ondelete="CASCADE")`), so each user account belongs to one organization.
- `AuditLog` (`backend/app/models/audit.py`) has `user_id` (`ForeignKey("users.id", ondelete="SET NULL")`).
- Previously, `OrganizationService.remove_member` executed `await db.delete(target)`, which caused PostgreSQL to cascade `UPDATE audit_logs SET user_id = NULL`, violating `0005_audit_immutability`'s `trg_audit_logs_immutable` trigger.
- **Semantics:** Removing a member from an organization revokes their `UserRole` records and active `RefreshToken`s, anonymizes `email` (`removed-<id>@removed.local`), and deactivates the user (`is_active = False`) without deleting the `users` row, preserving historical `audit_logs.user_id` attribution and append-only immutability.

### 1.2 Database Schema Drift (`gem_compliance` vs `bidguard_fresh_test`)
Direct inspection of PostgreSQL 16 revealed:
- Both databases report `alembic_version = '0011_prov_conflicts_evidence'`.
- **`bidguard_fresh_test`:** Has `prevent_audit_log_mutation()`, `trg_audit_logs_immutable` (`BEFORE DELETE OR UPDATE ON public.audit_logs`), `audit_logs` RLS `(True, True)`, and `bidguard_app` privileges.
- **`gem_compliance`:** Has `AUDIT_TRIGGERS: []`, `AUDIT_FUNCS: []`, and `AUDIT_RLS: [(False, False)]`, because `gem_compliance` was bootstrapped/stamped before `0004`/`0005` DDL executed against `audit_logs`.

---

## 2. Change Plan

1. **Forward Reconciliation Migration (`0012_audit_immutability_sync`):**
   - `down_revision = '0011_prov_conflicts_evidence'`
   - Idempotently creates/replaces `prevent_audit_log_mutation()`, drops & recreates `trg_audit_logs_immutable` on `audit_logs`, and enables/forces RLS (`tenant_isolation_audit_logs`) on `audit_logs` so `gem_compliance` and `bidguard_fresh_test` have identical audit-integrity enforcement.
2. **Test Isolation (`backend/conftest.py`):**
   - Add a session-scoped safeguard in `backend/conftest.py` (or test guard) that checks `DATABASE_URL` when running `pytest`, refusing accidental execution against `gem_compliance` if a live worker is active unless explicitly overridden, and documenting `bidguard_fresh_test` as the supported isolated test DB.
3. **Regression Coverage (`backend/test_phase2_0d_2_remediation.py`):**
   - Direct `UPDATE`/`DELETE` rejection on `audit_logs` under `bidguard_app` and `postgres`, indirect user-deletion immutability check, repeated member removal & actor attribution preservation.
   - Phase 2.0D human-decision preservation (`CONFIRMED`/`DISMISSED`/`RESOLVED` conflicts and `CONFIRMED`/`REJECTED` evidence mappings), `NEEDS_REVIEW` evidence mapping, and `SOURCE_CHANGED` provenance transition.
4. **Full Verification:** Run all suites against `bidguard_fresh_test` + Golden Demo + frontend checks, and write `PHASE_2_0D_2_EVALUATION.md` and `PHASE_2_0D_2_IMPLEMENTATION_REPORT.md`.
