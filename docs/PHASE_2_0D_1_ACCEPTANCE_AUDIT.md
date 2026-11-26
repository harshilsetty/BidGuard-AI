# Phase 2.0D.1 Independent Acceptance Audit: Provenance, Conflict Detection & Evidence Mapping

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**HEAD:** `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`  
**Audit Mode:** Strictly read-only (no application, migration, RLS, privilege, test, or Golden Demo changes)

---

## 1. Executive Verdict

**VERDICT: CONDITIONAL PASS**

- **Phase 2.0D Core:** Provenance verification, scope-aware cross-document conflict & `POTENTIAL_AMENDMENT` detection, source-grounded expected evidence mapping, `bidguard_app` `FORCE ROW LEVEL SECURITY` (reads and cross-tenant writes blocked), connection-pool GUC isolation, Phase 2.0B.2 `ownership_generation` fencing, and Golden Demo frozen regressions are **verified and passing**.
- **Why Conditional (Not Unconditional Pass):**
  1. **Pre-existing Phase 1.0/1.2 P2 Product Defect (`audit_logs` immutability vs `remove_member`):** On `bidguard_fresh_test`, `test_member_management_safeguards_and_cross_tenant_isolation` fails because `OrganizationService.remove_member` (`DELETE FROM users`) fires `ON DELETE SET NULL` on `audit_logs.user_id`, which `0005_audit_immutability`'s `trg_audit_logs_immutable` rejects (`UPDATE operations are forbidden`). On `gem_compliance`, `trg_audit_logs_immutable` is missing (`AUDIT_TRIGGERS: []`).
  2. **Test Contention on `gem_compliance`:** Running `test_phase2_0b_async_processing.py` against `gem_compliance` while Uvicorn (`PID 34200` / reload child `PID 29792`) is active causes `worker-29792-3515fa33` to claim test jobs first.
  3. **Targeted Test Coverage Gaps:** Human-decision preservation (`CONFIRMED`/`DISMISSED`/`RESOLVED`/`REJECTED`) across re-runs and `NEEDS_REVIEW` mapping status are verified by code inspection rather than direct test assertions in `test_phase2_0d_provenance_conflicts_evidence.py`.

---

## 2. Repository & Database Baseline

- **Branch / HEAD:** `main` at `ceff33f08cdb214b0281f3c7fd03df4bb12c8c19`.
- **Alembic Head:** `0011_prov_conflicts_evidence (head)` on both `gem_compliance` and `bidguard_fresh_test`.
- **PostgreSQL Roles (`pg_roles`):**
  - `postgres`: `rolsuper=True, rolbypassrls=True`
  - `bidguard_app`: `rolsuper=False, rolbypassrls=False`
- **Phase 2.0D Tables (`pg_class`):**
  - `tender_requirement_sources`: `relrowsecurity=True, relforcerowsecurity=True`
  - `tender_requirement_conflicts`: `relrowsecurity=True, relforcerowsecurity=True`
  - `tender_requirement_evidence`: `relrowsecurity=True, relforcerowsecurity=True`
- **Live Processes:**
  - `PID 34200`: `"C:\Python313\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` (started `12:59:42 AM`)
  - `PID 29792`: Uvicorn `--multiprocessing-fork` child (spawned `1:08:39 AM`)

---

## 3. Investigation of All Three Full-Suite Failures

### 3.1 Two Failures on `gem_compliance` (`test_phase2_0b_async_processing.py`)
- **Failing Tests & Tracebacks:**
  - `test_phase2_0b_job_lifecycle_pages_retry_and_security:134` -> `assert len(winners) == 1` (`AssertionError: assert 0 == 1`)
  - `test_phase2_0b_lease_recovery_scanned_ocr_and_integrity_failures:291` -> `assert claimed_t == tamper_job_id` (`AssertionError: assert None == UUID('a5c80d58-...')`)
- **Causal Evidence:**
  - `pg_stat_activity` confirmed active connections on `gem_compliance`.
  - Querying `tender_processing_jobs` on `gem_compliance` showed `worker_id = 'worker-29792-3515fa33'` (matching Uvicorn child `PID 29792`) had claimed **4** jobs.
  - Because `test_phase2_0b_async_processing.py` enqueues `QUEUED` jobs via HTTP (`worker_manager.notify()`) and then manually calls `claim_next_job()`, the live Uvicorn polling worker on `gem_compliance` claimed those `QUEUED` rows before the test's `claim_next_job()` call.
- **Controlled Confirmation:** When `test_phase2_0b_async_processing.py` ran isolated on `bidguard_fresh_test` (no Uvicorn worker), all `3/3` tests passed in `14.29s`.
- **Classification:** **Test / Environment Contention** (tests using `AsyncSessionLocal` are not safe to run against a database with an active polling `TenderProcessingWorkerManager`).

### 3.2 One Failure on `bidguard_fresh_test` (`test_enterprise_org_invitations.py`)
- **Failing Test:** `test_member_management_safeguards_and_cross_tenant_isolation` (line 348: `DELETE /api/v1/organizations/me/members/{member_a_id}`).
- **Exact Error:** `asyncpg.exceptions.RaiseError: audit_logs is append-only: UPDATE operations are forbidden`.
- **Root Cause & Schema Discrepancy:**
  - `audit_logs.user_id` has foreign key `ON DELETE SET NULL` (`confdeltype = 'n'`) on both DBs.
  - `OrganizationService.remove_member` (`backend/app/services/organization_service.py:415`) executes `await db.delete(target)` (`DELETE FROM users`), which triggers PostgreSQL to cascade `UPDATE audit_logs SET user_id = NULL WHERE user_id = :id`.
  - On `bidguard_fresh_test`, `0005_audit_immutability`'s trigger `trg_audit_logs_immutable` (`tgenabled = 'O'`) is active and rightly blocks the `UPDATE` on `audit_logs`.
  - On `gem_compliance`, `AUDIT_TRIGGERS: []` — `trg_audit_logs_immutable` is absent, masking the bug.
- **Classification:** **Product Defect (Pre-existing Phase 1.0/1.2)** + **Migration/Schema Inconsistency on `gem_compliance`** (unrelated to Phase 2.0D).

---

## 4. Provenance Correctness Assessment

- **Verified (`requirement_provenance_service.py` + `test_phase2_0d_provenance_conflicts_evidence.py`):**
  - Exact match on attributed page -> `VERIFIED`.
  - Mid-word hyphenated line-break (`compre-\nhensive`) or whitespace normalization -> `PARTIALLY_VERIFIED`.
  - Quote found on a different page (`p.2` instead of `p.1`) -> `PARTIALLY_VERIFIED` with `matched_page_number = 2` (never marked `VERIFIED`).
  - Missing page (`p.5`) -> `SOURCE_NOT_FOUND`.
  - Fabricated/ungrounded quote -> `UNVERIFIED`.
  - Document SHA-256 mismatch -> `SOURCE_CHANGED`.
  - Original `source_text` is never rewritten; `TenderRequirementSource` stores additional/contradictory passages separately.
- **Note:** Provenance verifies *textual grounding* against persisted pages, not factual/legal truth of the requirement.

---

## 5. Conflict Detection Assessment

- **Verified (`requirement_conflict_service.py` + `test_phase2_0d_provenance_conflicts_evidence.py`):**
  - Normalizes `Lakhs` / `Crores` / `INR` / `days` / `weeks` / `months` / `years` / `GB` / `TB`.
  - Disjoint scopes (`Lot 1` vs `Lot 2`) are **not** flagged as conflicts (`0` false positives).
  - Corrigendum (`FIN-02`, `INR 8 Crore`) vs NIT (`FIN-01`, `INR 500 Lakhs`) is flagged as `FINANCIAL_MISMATCH` with `relationship_type = 'POTENTIAL_AMENDMENT'` and `status = 'NEEDS_REVIEW'`, preserving both original requirements.
  - Automated detection never sets `CONFIRMED`, `DISMISSED`, or `RESOLVED`; code inspection confirms `CONFIRMED`/`DISMISSED`/`RESOLVED` records are preserved on re-runs.

---

## 6. Evidence Mapping Assessment

- **Verified (`requirement_evidence_service.py` + `test_phase2_0d_provenance_conflicts_evidence.py`):**
  - Grounded cues (`INR 500 Lakhs with audited balance sheets`) produce `AUDITED_FINANCIAL_STATEMENTS` and `TURNOVER_CERTIFICATE` with `mapping_status = 'SUGGESTED'` (never `CONFIRMED`).
  - Ungrounded requirement without evidence cues produces `0` fabricated mappings (`total == 0`).
  - Mappings remain tenant-scoped and RLS-protected.

---

## 7. Tenant Isolation & Worker Fencing

- **Cross-Tenant Write Rejection (`bidguard_app`):** Attempting `INSERT INTO tender_requirement_evidence` for Org B's tender while `app.current_org_id = org_a` failed with `ProgrammingError: new row violates row-level security policy`.
- **Pool GUC Reset:** Verified on `pool_size=1, max_overflow=0`: `POOL_GUCS_AFTER_COMMIT: (None, '')`.
- **Worker Fencing:** Phase 2.0D made zero modifications to `tender_processing_worker.py` fencing; `test_phase2_0b_2_fencing.py` passed under `bidguard_app`.

---

## 8. Test Coverage Matrix (`test_phase2_0d_provenance_conflicts_evidence.py`)

| Capability | Positive case | Negative case | Tenant isolation | Human-decision preservation |
|---|---|---|---|---|
| Provenance | Directly tested (`VERIFIED`, `PARTIALLY_VERIFIED`, `TenderRequirementSource`) | Directly tested (`UNVERIFIED`, `SOURCE_NOT_FOUND`, `SOURCE_CHANGED`) | Directly tested (403/404 API + `bidguard_app` RLS) | Verified by code inspection (`source_text` immutable; `0005` unrelated) |
| Conflict detection | Directly tested (`FINANCIAL_MISMATCH`) | Directly tested (disjoint scope `Lot 1` vs `Lot 2` -> 0 conflicts) | Directly tested (`bidguard_app` RLS table + `tender:update` 403) | Verified by code inspection (preserves `CONFIRMED`/`DISMISSED`/`RESOLVED`) |
| Corrigendum handling | Directly tested (`POTENTIAL_AMENDMENT`, `NEEDS_REVIEW`) | Directly tested (original `FIN-01` preserved) | Covered via tender RLS | Verified by code inspection |
| Evidence mapping | Directly tested (`AUDITED_FINANCIAL_STATEMENTS`, `TURNOVER_CERTIFICATE`) | Directly tested (0 fabricated mappings on ungrounded req) | Directly tested (`bidguard_app` RLS read & write rejection) | Verified by code inspection (preserves `CONFIRMED`/`REJECTED`) |

---

## 9. Golden Demo Regression & Controlled Verification Rerun

- **Controlled Run on `bidguard_fresh_test` (`test_golden_demo_frozen_regression.py`, `test_phase2_0b_2_fencing.py`, `test_phase2_0b_async_processing.py`, `test_phase2_0d_provenance_conflicts_evidence.py`):**
  - **`11 passed, 17 warnings in 10.40s`** (`4/4` Golden Demo, `1/1` Phase 2.0B.2 fencing, `3/3` Phase 2.0B async, `3/3` Phase 2.0D).
- **Golden Demo Preserved Outputs:** `100.00` (11P/0F/0R) / `53.41` (1P/9F/1R) / `47.95` (3P/5F/3R) standalone; `90.45` / `40.45` / `34.77` fused.

---

## 10. Ranked Findings & Closure Recommendation

- **[P2] Pre-existing `OrganizationService.remove_member` vs `0005_audit_immutability` Trigger:** Hard-deleting a `User` cascades `ON DELETE SET NULL` onto `audit_logs.user_id`, failing on `bidguard_fresh_test` (and masked on `gem_compliance` where `trg_audit_logs_immutable` is missing). *Recommendation:* Soft-deactivate/anonymize removed users instead of hard `DELETE`, and restore `0005` trigger on `gem_compliance` (separate authorization).
- **[P2] `test_phase2_0b_async_processing.py` Contention with Live Uvicorn Worker:** Unsafe to run against a DB with an active polling worker. *Recommendation:* Run backend tests against an isolated test DB (`bidguard_fresh_test`).
- **[P3] Minor Phase 2.0D Test Gaps:** Add 2–3 assertions for `CONFIRMED`/`DISMISSED`/`REJECTED` preservation across re-runs and `NEEDS_REVIEW` evidence mapping when `source_quote_verified=False`.

**Closure Recommendation:** **Approve Phase 2.0D (`CONDITIONAL PASS`)** — Phase 2.0D introduces no P0/P1 defects and meets all provenance, conflict-detection, evidence-mapping, RLS, and Golden Demo acceptance criteria.
