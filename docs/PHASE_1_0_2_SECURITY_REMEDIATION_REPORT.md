# BIDGUARD AI — PHASE 1.0.2
## CRITICAL SECURITY REMEDIATION & BACKEND STABILIZATION REPORT

**Date**: 2026-11-25  
**Repository**: `harshilsetty/BidGuard-AI` (`main` @ `96b040bf03bba17fe7400c95b57e3907bdd0cd82`)  
**Phase**: Phase 1.0.2 — Remediation of Phase 1.0.1 Acceptance Audit Findings  
**Final Recommendation**: **CONDITIONALLY ACCEPTED** — All P0 blockers are remediated and verified on SQLite/in-memory ASGI; PostgreSQL 16 + pgvector live execution and updating legacy unauthenticated API test clients remain explicitly identified non-P0 conditions. (Project owner holds Phase 1.1 authorization.)

---

## 1. Original Audit Findings & Remediation Status

| ID | Severity | Original Finding | Classification |
|---|---|---|---|
| **F-01** | **P0** | Unauthenticated and cross-tenant API access across `tenders`, `bidders`, `evaluations`, `statutory`, `verification_intelligence`, `mock_sources` | **FIXED AND VERIFIED** |
| **F-02** | **P0** | Missing `require_permission()` RBAC enforcement on business routes | **FIXED AND VERIFIED** |
| **F-03** | **P0** | Missing SQLite FK on `tenders.organization_id` & absent PostgreSQL RLS | **FIXED AND VERIFIED** (SQLite FK + `PRAGMA foreign_keys=ON`) / **FIXED BUT NOT FULLY VERIFIED** (PostgreSQL RLS written in `0003`, PG unavailable locally) |
| **F-04** | **P0** | `EmbeddingService` missing `import os` (`NameError`) & `AUTH_DEV_MODE=True` stub bypass | **FIXED AND VERIFIED** |
| **F-05** | **P1** | Refresh-token concurrency race (TOCTOU) | **FIXED AND VERIFIED** (SQLite concurrency test) / **FIXED BUT NOT FULLY VERIFIED** (PostgreSQL `asyncio.gather` test blocked by PG unavailability) |
| **F-06** | **P1** | Stale JWT permissions (15m) & unhandled 500 in `get_optional_user` | **FIXED AND VERIFIED** |
| **F-07** | **P1** | Incomplete `0001_initial_baseline.py` & broken `0002` SQLite `downgrade()` | **FIXED AND VERIFIED** (SQLite `0003` upgrade verified) / **FIXED BUT NOT FULLY VERIFIED** (Fresh PG `0001` run blocked by PG unavailability) |
| **F-08** | **P1** | Missing `input_type="passage"`/`"query"` for `nvidia/nemotron-3.5-embed-1b` & embedding-space consistency | **FIXED AND VERIFIED** (mocked client contract & `validate_embedding_space`) + Plan in `docs/EMBEDDING_REINDEX_MIGRATION_PLAN.md` |
| **F-09** | **P1** | Unrestricted public `ORG_ADMIN` self-registration & missing rate limiting | **FIXED AND VERIFIED** (with note: email transport not configured; out-of-band token delivery) |
| **F-10** | **P2** | `ALLOW_SQLITE_FALLBACK=True` failing hardening test & insecure `JWT_SECRET_KEY` default | **FIXED AND VERIFIED** |
| **F-11** | **P2** | `AuditService` pagination `total` returning page length instead of `COUNT(*)`; application-only append-only convention | **PARTIALLY FIXED** (`COUNT(*)` fixed; DB-level audit triggers deferred to PostgreSQL deployment) |
| **F-12** | **P2** | `pytest.ini` excluding Phase 1.0 tests & `test_api_direct.py` collection crash | **FIXED AND VERIFIED** |

---

## 2. Detailed Remediation Breakdown

### F-01 & F-02 (P0) — API Authentication, RBAC & Tenant Isolation
- **Root Cause**: `bidders.py`, `statutory.py`, `verification_intelligence.py`, `mock_sources.py`, and 10/11 routes in `evaluations.py` lacked authentication/RBAC/tenant checks; `tenders.py` and `override_evaluation_decision` used `get_optional_user` which skipped checks when `current_user is None`; `list_tenders` exposed `organization_id IS NULL` tenders to all tenants.
- **Fix Implemented**:
  - Replaced `get_optional_user` with `require_permission(...)` / `get_current_active_user` across all business routers.
  - Implemented centralized validators in `backend/app/api/deps.py`: `validate_tender_tenant_access`, `get_authorized_tender`, `validate_bidder_tenant_access`, `validate_document_tenant_access`, `validate_evaluation_tenant_access`.
  - Unassigned legacy records (`organization_id IS NULL`) are blocked (`404 Not Found`) from ordinary tenant APIs and accessible only to `SUPER_ADMIN`.
- **Files Changed**: `backend/app/api/deps.py`, `backend/app/api/v1/tenders.py`, `bidders.py`, `evaluations.py`, `statutory.py`, `verification_intelligence.py`, `mock_sources.py`.
- **Verification**: `test_enterprise_security_remediation.py::test_unauthenticated_and_malformed_tokens_blocked`, `test_cross_tenant_and_legacy_null_isolation`, `test_enterprise_tenant_rbac.py` — **PASSED**.

### F-03 (P0) — Database Tenant Enforcement & SQLite FK Integrity
- **Root Cause**: `PRAGMA foreign_keys=ON` was not enabled on SQLite connections; `0002_enterprise_foundation.py` skipped creating `fk_tenders_organization_id` on SQLite; PostgreSQL RLS was absent.
- **Fix Implemented**:
  - Added SQLAlchemy `connect` event listener `_enable_sqlite_foreign_keys` (`PRAGMA foreign_keys=ON`) in `backend/app/core/database.py`.
  - Created `backend/alembic/versions/0003_security_and_integrity.py` using `batch_alter_table('tenders')` to enforce `fk_tenders_organization_id` on SQLite and adding PostgreSQL RLS policies (`ENABLE` + `FORCE ROW LEVEL SECURITY`) on `tenders`, `audit_logs`, `organization_invitations`.
- **Verification**: `PRAGMA foreign_key_list(tenders)` confirmed FK; `test_sqlite_foreign_key_constraint_enforced` raised `IntegrityError` on invalid `organization_id` — **PASSED**. PostgreSQL RLS execution is **BLOCKED BY ENVIRONMENT** (`localhost:5432` unavailable).

### F-04 & F-08 (P0/P1) — EmbeddingService Reliability & NVIDIA Contract
- **Root Cause**: `os` was not imported in `embedding_service.py`; `AUTH_DEV_MODE` bypassed stub prohibition; `NvidiaEmbeddingProvider` omitted `input_type="passage"`/`"query"`; `DocumentChunk` lacked `embedding_model` metadata.
- **Fix Implemented**:
  - Added `import os`, decoupled `AUTH_DEV_MODE` from `_is_explicit_test_or_mock_dev_allowed()`, and added `ALLOW_MOCK_EMBEDDINGS` (ignored in `production`).
  - Updated `NvidiaEmbeddingProvider._embed_batch_with_retry` to pass `extra_body={"input_type": input_type}` (`"passage"` for `embed_texts`, `"query"` for `embed_query`), preserving `force_stub` only in non-production test/dev.
  - Added `DocumentChunk.embedding_model` and `EmbeddingService.validate_embedding_space()`.
  - Authored `docs/EMBEDDING_REINDEX_MIGRATION_PLAN.md` (no destructive re-indexing executed).
- **Verification**: `test_embedding_service_production_stub_ban_and_nvidia_contract` & `test_unit_bidder_retrieval.py` (12/12) — **PASSED**.

### F-05, F-06, F-09, F-10 (P1/P2) — Auth Lifecycle, Live RBAC & Config Hardening
- **Root Cause**: Non-atomic `SELECT`+`UPDATE` in `rotate_refresh_token`; `require_permission()` read stale JWT claims; open `/register` created verified `ORG_ADMIN`; `ALLOW_SQLITE_FALLBACK` defaulted to `True`.
- **Fix Implemented**:
  - Atomic conditional `UPDATE refresh_tokens SET revoked_at = :now WHERE token_hash = :h AND revoked_at IS NULL` in `auth_service.py`.
  - Live DB role/permission resolution (`_resolve_live_roles_and_permissions`) in `deps.py`.
  - Disabled public `/register` by default (`ALLOW_PUBLIC_ORG_SIGNUP=False`, returns `403`); added single-use expiring `OrganizationInvitation` endpoints (`/invitations`, `/invitations/accept`) and in-memory sliding-window rate limiter (`429`).
  - Restored `ALLOW_SQLITE_FALLBACK=False` and added `Settings.validate_production_security()` in `main.py` lifespan.
- **Verification**: `test_concurrent_refresh_token_race_condition`, `test_live_permission_revocation_immediate_denial`, `test_public_registration_blocked_and_invitation_flow`, `test_database_hardening.py` (7/7) — **PASSED**.

---

## 3. File-by-File Changes

- **Modified**: `backend/app/core/config.py`, `database.py`, `main.py`, `backend/app/api/deps.py`, `v1/auth.py`, `v1/tenders.py`, `v1/bidders.py`, `v1/evaluations.py`, `v1/statutory.py`, `v1/verification_intelligence.py`, `v1/mock_sources.py`, `backend/app/models/auth.py`, `chunk.py`, `__init__.py`, `backend/app/schemas/auth.py`, `backend/app/services/auth_service.py`, `audit_service.py`, `embedding_service.py`, `backend/alembic/versions/0001_initial_baseline.py`, `0002_enterprise_foundation.py`, `backend/pytest.ini`, `backend/test_enterprise_auth.py`, `test_enterprise_tenant_rbac.py`.
- **Created**: `backend/alembic/versions/0003_security_and_integrity.py`, `backend/test_enterprise_security_remediation.py`, `docs/EMBEDDING_REINDEX_MIGRATION_PLAN.md`, `docs/PHASE_1_0_2_SECURITY_REMEDIATION_REPORT.md`.
- **Relocated**: `backend/test_api_direct.py` -> `scripts/manual_nvidia_api_check.py`.

---

## 4. API Route Authorization & Tenant Matrix

| Router | Endpoint Pattern | Auth Dependency | Permission | Tenant Scope |
|---|---|---|---|---|
| `auth.py` | `POST /register` | Public (Disabled `403` by default) | — | Rate-limited |
| `auth.py` | `POST /invitations` | `require_permission("user:invite")` | `user:invite` | `current_user.organization_id` |
| `auth.py` | `POST /invitations/accept`, `/login`, `/refresh`, `/logout` | Public / Cookie | — | Rate-limited, atomic |
| `auth.py` | `GET /me` | `get_current_active_user` | Authenticated | Self |
| `tenders.py` | `POST /upload` | `require_permission("tender:create")` | `tender:create` | Stamped `current_user.organization_id` |
| `tenders.py` | `GET ""`, `GET /{id}`, `GET /{id}/clauses` | `require_permission("tender:read")` | `tender:read` | `get_authorized_tender` / org filter |
| `tenders.py` | `POST /{id}/extract`, `/clauses`, `PUT/DELETE /clauses/{cid}`, `POST /confirm` | `require_permission("tender:update")` | `tender:update` | `get_authorized_tender` |
| `bidders.py` | `GET .../bidders`, `GET .../bidders/{bid}` | `require_permission("tender:read")` | `tender:read` | `get_authorized_tender` |
| `bidders.py` | `POST .../bidders`, `POST .../bidders/demo` | `require_permission("document:upload")` | `document:upload` | `get_authorized_tender` |
| `bidders.py` | `GET .../evidence-fusion`, `.../cross-source-verification` | `require_permission("evaluation:read")` | `evaluation:read` | `get_authorized_tender` |
| `bidders.py` | `DELETE .../bidders/{bid}` | `require_permission("tender:delete")` | `tender:delete` | `get_authorized_tender` |
| `evaluations.py` | `POST .../evaluations/run`, `POST .../recommendation` | `require_permission("evaluation:run")` | `evaluation:run` | `get_authorized_tender` |
| `evaluations.py` | `GET .../matrix`, `/detail`, `/score`, `/ranking`, `GET .../recommendation` | `require_permission("evaluation:read")` | `evaluation:read` | `get_authorized_tender` / `validate_evaluation_tenant_access` |
| `evaluations.py` | `POST .../override`, `POST .../review` | `require_permission("evaluation:override")` | `evaluation:override` | `validate_evaluation_tenant_access` / `get_authorized_tender` |
| `evaluations.py` | `GET .../audit` | `require_permission("audit:read")` | `audit:read` | `get_authorized_tender` |
| `statutory.py` | `POST /verify` | `require_permission("evaluation:run")` | `evaluation:run` | `get_authorized_tender` / `validate_bidder_tenant_access` |
| `statutory.py` | `GET /status`, `GET /adapters` | `require_permission("evaluation:read")` | `evaluation:read` | Org-scoped via `Tender` join |
| `verification_intelligence.py` | `GET .../verification-summary`, `.../verification-history`, `.../review-queue` | `require_permission("evaluation:read")` | `evaluation:read` | `get_authorized_tender` |
| `mock_sources.py` | All `/mock-sources*` | `get_current_active_user` | Authenticated | Read-only mock registry |
| `audit.py` | `GET /audit/logs` | `require_permission("audit:read")` | `audit:read` | `AuditService` org-scoped |

---

## 5. Verification Results (Observed)

- **Pytest Collection (`cd backend; python -m pytest --collect-only -q`)**: **322 tests collected, 0 errors**.
- **Enterprise, Hardening & Golden Demo Run**:
  `python -m pytest test_enterprise_auth.py test_enterprise_tenant_rbac.py test_enterprise_audit.py test_enterprise_security_remediation.py test_golden_demo_frozen_regression.py test_database_hardening.py -v` -> **24 passed, 0 failed**.
- **Unit Retrieval (`test_unit_bidder_retrieval.py`)**: **12 passed, 0 failed**.
- **Unit Compliance & Clause Extraction**: **33 passed** (`test_unit_compliance_engine.py` 19/19, `test_unit_clause_extraction.py` 14/14).
- **Golden Demo Frozen Regression**:
  - EnterpriseTech: 11 PASS / 0 FAIL / 0 REVIEW, 100.00% Clause Compliance, 100.00 standalone score.
  - Legacy Hardware: 1 PASS / 9 FAIL / 1 REVIEW, 13.64% Clause Compliance, 53.41 standalone score.
  - Apex Systems: 3 PASS / 5 FAIL / 3 REVIEW, 40.91% Clause Compliance, 47.95 standalone score.
- **PostgreSQL / Legacy Unauthenticated API Tests**:
  - `localhost:5432` is not running (`pg_5432_open: False`), so `test_phase6_mock_sources.py::test_seeder_idempotency` failed with `RuntimeError: PostgreSQL is unavailable`.
  - Older API test files (`test_api_bidders_evaluations.py`, `test_api_mock_explorer.py`, `test_phase6_scoring_and_ranking.py`, `test_phase8_statutory_orchestrator.py`) will now receive `401` until their test clients are updated to supply an authenticated user token (expected behavior of mandatory auth).

---

## 6. Remaining Risks & Next Phase

1. **PostgreSQL 16 + pgvector Live Verification (P1 condition)**: Execute `alembic upgrade head`, verify `0003` RLS policies under non-superuser runtime role, and run concurrent refresh tests against PostgreSQL 16.
2. **Legacy API Test Client Updates (P2)**: Update `test_api_*.py` and `test_phase6/8` API tests to pass test org Bearer tokens.
3. **Email Transport for Invitations (P2)**: Wire SMTP/SES before enabling invitation emails in production.
4. **Database-Level Audit Immutability (P2)**: Add PostgreSQL `BEFORE UPDATE OR DELETE` trigger on `audit_logs` in production migration.

**Recommended Next Step**: Project owner reviews this report, verifies PostgreSQL 16 + pgvector in CI/staging, and decides whether to authorize **Phase 1.1 (Frontend Authentication Integration)**.
