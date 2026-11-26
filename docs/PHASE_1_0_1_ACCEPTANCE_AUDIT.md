# BIDGUARD AI — PHASE 1.0.1
## INDEPENDENT ENTERPRISE FOUNDATION ACCEPTANCE AUDIT

**Audit Date**: 2026-11-25  
**Auditor Role**: Independent Principal Software Architect & Application Security Auditor  
**Target Repository**: `harshilsetty/BidGuard-AI`  
**Audit Scope**: Read-only verification of Phase 1.0 implementation prior to Phase 1.1 authorization  

---

## 1. Executive Verdict

### **VERDICT: REJECTED — Critical remediation required before Phase 1.1.**

Phase 1.0 successfully introduced core database models (`Organization`, `User`, `Role`, `Permission`, `RefreshToken`, `AuditLog`), Argon2id password hashing, JWT issuance/refresh rotation endpoints, and an initial audit endpoint (`GET /api/v1/audit/logs`). However, independent verification of the actual source code, database schema, and execution paths uncovered **four P0 critical blockers** and **five P1 high-risk blockers** that invalidate the Phase 1.0 security and multi-tenancy claims:

1. **P0 — Unauthenticated & Cross-Tenant Bypass**: Every endpoint in `bidders.py`, `statutory.py`, and `verification_intelligence.py`, 10 of 11 endpoints in `evaluations.py`, and all 8 endpoints in `tenders.py` (via `get_optional_user` returning `None`) allow unauthenticated callers to bypass tenant isolation and RBAC checks completely—reading, creating, modifying, and overriding data across all organizations.
2. **P0 — Missing RBAC Enforcement**: Only `GET /api/v1/audit/logs` uses `require_permission()`. Authenticated `BIDDER` and `AUDITOR` users can upload tenders, extract/edit/delete clauses, run evaluations, and mutate bidder records within their organization.
3. **P0 — Absent Database-Level Isolation**: PostgreSQL Row-Level Security (RLS) is absent, and SQLite `tenders.organization_id` has no database-level foreign key constraint (`PRAGMA foreign_key_list(tenders)` is empty).
4. **P0 — `EmbeddingService` Runtime `NameError` & Incomplete NVIDIA Contract**: `backend/app/services/embedding_service.py` references `os.environ.get(...)` without `import os`, `AUTH_DEV_MODE=True` silently permits `StubEmbeddingProvider` by default, and `NvidiaEmbeddingProvider` omits `input_type="passage"` / `"query"` required for `nvidia/nemotron-3.5-embed-1b`.

Phase 1.1 frontend authentication integration **must not proceed** until P0 and P1 blockers are remediated.

---

## 2. Repository Integrity

| Attribute | Observed Value |
|---|---|
| **Current Branch** | `main` |
| **Current HEAD Commit SHA** | `96b040bf03bba17fe7400c95b57e3907bdd0cd82` (`first commit`) |
| **Phase 1.0 Starting Baseline** | `96b040bf03bba17fe7400c95b57e3907bdd0cd82` |
| **Phase 0.6/0.7 Documented SHA** | `96b040b8a21f7eef71fbcf7564d39fb4a491ef2f` — **Not found in Git object store** (`fatal: git cat-file: could not get object info`). Shares the 7-char prefix `96b040b`; this is a reporting/transcription discrepancy in earlier documentation rather than a distinct commit. |
| **Golden Demo Fixtures** | `data/sample_tenders/tender_gem_2026_b_8912450.json` and `backend/seed_golden_demo.py` have **empty diff** against `HEAD` (unchanged). |

### Uncommitted Working-Tree Changes
- **Modified (8 files)**:
  - `backend/app/api/router.py`
  - `backend/app/api/v1/evaluations.py`
  - `backend/app/api/v1/tenders.py`
  - `backend/app/core/config.py`
  - `backend/app/models/__init__.py`
  - `backend/app/models/audit.py`
  - `backend/app/models/tender.py`
  - `backend/app/services/embedding_service.py`
- **Untracked (20 entries)**:
  - `backend/alembic.ini`, `backend/alembic/` (`env.py`, `0001_initial_baseline.py`, `0002_enterprise_foundation.py`)
  - `backend/app/api/deps.py`, `backend/app/api/v1/audit.py`, `backend/app/api/v1/auth.py`
  - `backend/app/core/security.py`
  - `backend/app/models/auth.py`, `organization.py`, `rbac.py`, `user.py`
  - `backend/app/schemas/audit.py`, `auth.py`
  - `backend/app/services/audit_service.py`, `auth_service.py`, `rbac_service.py`
  - `backend/test_enterprise_audit.py`, `test_enterprise_auth.py`, `test_enterprise_tenant_rbac.py`, `test_golden_demo_frozen_regression.py`
  - `docs/PHASE_1_0_ENTERPRISE_FOUNDATION_REPORT.md`

---

## 3. Database and Migration Findings

### SQLite Verification (Observed on `backend/gem_compliance.db`)
- **Alembic State**: `alembic_version` = `0002_enterprise_foundation`. All 28 tables (baseline + enterprise + mock sources) exist; `tenders` has `organization_id` column and index `ix_tenders_organization_id`.
- **Adoption Safety**: `alembic stamp 0001_initial_baseline && alembic upgrade head` was non-destructive for existing data because `0002_enterprise_foundation.py` checks `if '<table_name>' not in existing_tables` and `if 'organization_id' not in tender_cols`. Historical Golden Demo records were preserved.
- **Note on `tenders` row count**: `backend/gem_compliance.db` currently contains **9 tenders** (up from 5) because `test_phase6_scoring_and_ranking.py::test_tender_isolation` writes directly to `backend/gem_compliance.db` when run from `backend/`.

### PostgreSQL Verification
- **Environment Status**: PostgreSQL 16 (`localhost:5432`) is **not running** in this environment (`pg_5432_open: False`). Live PostgreSQL migrations, `pgvector`, and RLS were **not** executed.

### Migration Defects Identified
1. **[P1] Incomplete `0001_initial_baseline.py` for Fresh Databases**: `0001_initial_baseline.py` creates only 7 tables (`tenders`, `tender_clauses`, `bidders`, `bid_documents`, `document_chunks`, `compliance_evaluations`, `recommendation_audit_records`). It **omits** `statutory_verification_records` and all 11 `mock_*_records` tables (`mock_gstn_records`, etc.). A fresh DB provisioned solely via `alembic upgrade head` will fail at runtime when statutory or mock-source queries execute.
2. **[P1] Vector Column Type Mismatch in `0001_initial_baseline.py`**: Line 115 defines `document_chunks.embedding` as `postgresql.ARRAY(sa.Float())` on PostgreSQL, whereas `DocumentChunk` (`backend/app/models/chunk.py:21`) defines `Vector(dim=settings.EMBEDDING_DIM)` (`vector(2048)`).
3. **[P1] Broken `downgrade()` in `0002_enterprise_foundation.py`**: Line 190 unconditionally calls `op.drop_constraint('fk_tenders_organization_id', 'tenders', type_='foreignkey')`. Because `upgrade()` skips creating this FK on SQLite (line 185: `if bind.dialect.name == 'postgresql':`) and SQLite requires batch mode to drop constraints, `alembic downgrade` crashes on SQLite.
4. **[P0] Missing SQLite FK on `tenders.organization_id`**: `PRAGMA foreign_key_list(tenders)` returned `[]`. SQLite has no referential integrity check on `tenders.organization_id`.

---

## 4. Tenant-Isolation Findings (CRITICAL)

Adding a nullable `organization_id` column to `tenders` is **insufficient** under the current implementation because (a) unauthenticated requests are permitted on tender/bidder/evaluation routes, (b) child routers do not check `tender.organization_id` at all, and (c) there is no database-level isolation.

### Entity Ownership & Enforcement Matrix

| Entity | Tenant Ownership Mechanism | Query-Level Enforcement | Database Enforcement | Verified |
|---|---|---|---|---|
| `Organization` | Root tenant (`id`) | None (no org CRUD endpoints) | PK/unique `slug` | Partial |
| `Tender` | Direct `organization_id` (nullable) | **Bypassed** when `current_user is None` (`get_optional_user`) or `organization_id IS NULL` | **None** on SQLite (no FK); **No RLS** on PostgreSQL | **FAIL (P0)** |
| `Bidder` | Indirect via `tender_id -> tenders.organization_id` | **None** (`bidders.py` has no auth or tenant check) | FK to `tenders` only; **No RLS** | **FAIL (P0)** |
| `BidDocument` | Indirect via `bidder_id -> bidders -> tenders` | **None** (`bidders.py` has no auth or tenant check) | FK to `bidders` only; **No RLS** | **FAIL (P0)** |
| `DocumentChunk` | Indirect via `bidder_id -> bidders -> tenders` | **None** in `bidders.py` / `evaluations.py` endpoints | FK to `bidders`/`bid_documents` only; **No RLS** | **FAIL (P0)** |
| `ComplianceEvaluation` | Indirect via `clause_id`/`bidder_id` -> `tenders` | **Partial**: Only `override_evaluation_decision` checks `parent_tender.organization_id`, and **skips check if unauthenticated** (`if current_user`) | FK only; **No RLS** | **FAIL (P0)** |
| `StatutoryVerificationRecord` | Indirect via `tender_id` / `bidder_id` | **None** (`statutory.py` allows querying any `tender_id` or `bidder_id` unauthenticated) | None; **No RLS** | **FAIL (P0)** |
| `RecommendationAuditRecord` | Indirect via `tender_id` / `bidder_id` | **None** (`evaluations.py` recommendation/review/audit routes have no auth or tenant check) | FK only; **No RLS** | **FAIL (P0)** |
| `AuditLog` | Direct `organization_id` (nullable) | Enforced in `GET /api/v1/audit/logs` via `AuditService.get_organization_audit_logs` | FK (`SET NULL`); **No RLS** | **PASS** (API query) |
| Uploaded Files | Disk path in `UPLOAD_DIR` (`tender_<uuid>_...`, `bid_<uuid>_...`) | No file download endpoint exists; upload routes allow anonymous/unscoped uploads | Filesystem only | **FAIL (P0)** |

### Adversarial Access Paths Confirmed in Source Code
- **Direct & Nested Resource Access**: An unauthenticated caller or cross-tenant user can call `GET /api/v1/tenders/{tender_id}/bidders`, `GET .../bidders/{bidder_id}/evidence-fusion`, `GET .../evaluations/matrix`, `GET .../ranking`, `GET /api/v1/statutory/status?tender_id=<id>`, and `GET /api/v1/tenders/{id}/review-queue` for **any** organization's tender.
- **Unauthenticated Evaluation Override**: In `backend/app/api/v1/evaluations.py:481-539`, `override_evaluation_decision` uses `get_optional_user` and wraps both permission check (line 499) and tenant check (line 532) inside `if current_user:`. Omitting the `Authorization` header completely bypasses both RBAC and tenant isolation.
- **Unauthenticated Tender Upload & Listing Leak**: Omitting `Authorization` on `POST /api/v1/tenders/upload` creates a tender with `organization_id=None`, which `GET /api/v1/tenders` then exposes to **all** organizations via `or_(Tender.organization_id == current_user.organization_id, Tender.organization_id.is_(None))`.
- **PostgreSQL RLS**: Explicitly **absent**. Application-level checks (even once fixed) are not backed by database-level Row-Level Security.

---

## 5. Authentication and Session Security Findings

### Verified Controls
- **Argon2id**: `PasswordHasher(time_cost=2, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)` in `backend/app/core/security.py:15-21`, with constant-time `verify()`.
- **JWT Claims & Validation**: `HS256`, 15-minute access TTL, validates `exp`, `sub`, `org_id`, `type == "access"`, `jti`, `iss`, `aud`.
- **Refresh Tokens**: 48-byte `secrets.token_urlsafe`, stored as SHA-256 hash (`hash_token`), 7-day TTL, `HttpOnly` cookie (`path="/api/v1/auth"`, `samesite="lax"`), family tracking (`token_family_id`) with reuse revocation, and logout revocation.
- **Inactive Users/Orgs**: Checked in `get_current_user` and `authenticate_user` (`403 Forbidden`).

### Defects Identified
1. **[P1] Concurrent Refresh Race Condition (TOCTOU)**: `AuthService.rotate_refresh_token()` (`backend/app/services/auth_service.py:227-296`) queries `RefreshToken` with a plain `SELECT` without `with_for_update()` or atomic `UPDATE ... WHERE revoked_at IS NULL`. Two concurrent refresh requests presenting the same old token can both observe `revoked_at is None` and both issue valid new tokens.
2. **[P1] Stale Permissions in Access Tokens**: `require_permission()` and `require_role()` (`backend/app/api/deps.py:103-139`) evaluate `token_permissions` and `token_roles` from the JWT payload rather than the live `user.user_roles` loaded from the DB. Revoked roles/permissions remain effective for up to **15 minutes** (access token lifetime).
3. **[P1] Unhandled Exception in `get_optional_user`**: `backend/app/api/deps.py:164` calls `decode_access_token()` outside `try/except`, causing an unhandled **500 Internal Server Error** when an expired or malformed Bearer token is sent to `tenders.py` or `override_evaluation_decision`.
4. **[P1] Public Org-Admin Self-Registration**: `POST /api/v1/auth/register` allows any anonymous internet caller to create an arbitrary organization and receive a pre-verified (`is_verified=True`) `ORG_ADMIN` account with no email verification or rate limiting.
5. **[P2] Hardcoded Insecure JWT Secret Default & Cookie/CORS Settings**: `config.py:48` defaults `JWT_SECRET_KEY` to `"bidguard-insecure-dev-secret-key-change-in-production-min-32-chars"` with no startup guard rejecting it in production. `COOKIE_SECURE` defaults to `False`. `main.py` sets `allow_methods=["*"]` and `allow_headers=["*"]` with `allow_credentials=True`.
6. **[P3] Missing Account Recovery**: No password reset, email verification, or MFA flow exists.

---

## 6. RBAC Findings

### Seeded Role-Permission Matrix (`backend/app/services/rbac_service.py`)

| Permission | `SUPER_ADMIN` | `ORG_ADMIN` | `PROCUREMENT_OFFICER` | `AUDITOR` | `BIDDER` |
|---|:---:|:---:|:---:|:---:|:---:|
| `organization:read` | ✓ | ✓ | ✓ | ✓ | — |
| `organization:update` | ✓ | ✓ | — | — | — |
| `user:invite` | ✓ | ✓ | — | — | — |
| `user:manage` | ✓ | ✓ | — | — | — |
| `tender:create` | ✓ | ✓ | ✓ | — | — |
| `tender:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `tender:update` | ✓ | ✓ | ✓ | — | — |
| `tender:delete` | ✓ | ✓ | — | — | — |
| `document:upload` | ✓ | ✓ | ✓ | — | — |
| `document:download` | ✓ | ✓ | ✓ | ✓ | — |
| `evaluation:run` | ✓ | ✓ | ✓ | — | — |
| `evaluation:read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `evaluation:override` | ✓ | — | ✓ | — | — |
| `audit:read` | ✓ | ✓ | — | ✓ | — |
| `audit:export` | ✓ | ✓ | — | ✓ | — |

### Route Enforcement Gaps
- **[P0] Missing `require_permission()` Across Core Business Routers**:
  - `tenders.py` (8 routes): **0 routes** use `require_permission()`. Any authenticated user (including `BIDDER` and `AUDITOR`) or unauthenticated user can upload, extract, add, edit, delete, and confirm tenders/clauses.
  - `bidders.py` (8 routes): **0 routes** use `require_permission()` or auth. A `BIDDER` can read/delete other bidders (`DELETE /tenders/{tender_id}/bidders/{bidder_id}`).
  - `evaluations.py` (11 routes): **10 routes** have no auth/RBAC; only `override_evaluation_decision` checks `evaluation:override`, and only if `current_user` is present.
  - `statutory.py` (`POST /verify`, `GET /status`) & `verification_intelligence.py` (3 routes): **0 routes** use auth/RBAC.
- **[P2] Unimplemented Management & Export Endpoints**: Permissions `organization:read`, `organization:update`, `user:invite`, `user:manage`, and `audit:export` are seeded in `ROLE_PERMISSIONS_MAP`, but no API endpoints exist for organization management, user invitation, role assignment, or audit export.

---

## 7. Audit Log Integrity Findings

| Criterion | Observed Implementation |
|---|---|
| **Classification** | **Application-level append-only convention** (NOT database-enforced immutable, NOT tamper-evident). |
| **ORM / DB Mutability** | `AuditService` only exposes `log_event` and `get_organization_audit_logs`, but no PostgreSQL `REVOKE UPDATE, DELETE` permissions, no DB `BEFORE UPDATE OR DELETE` triggers, and no hash chaining exist. Privileged DB/ORM code can alter or delete `audit_logs`. |
| **Transaction Atomicity** | `EVALUATION_OVERRIDE` (`evaluations.py:546-562`) and `AUTH_*` events (`auth_service.py`) commit in the same transaction as the business mutation. Failed logins commit `AUTH_LOGIN_FAILED` before raising `401`. |
| **Sensitive Data Exposure** | Passwords and tokens are not logged. `diff_json` logs email, `override_reason`, and metadata. |
| **Pagination Count Bug [P2]** | `AuditService.get_organization_audit_logs` (`audit_service.py:79`) returns `len(results)` (current page size, max 100) as `total` instead of `COUNT(*)`. |

---

## 8. Embedding Compatibility Findings

1. **[P0] Missing `import os` in `embedding_service.py`**: Lines 221–222 and 241–242 call `os.environ.get(...)`, but `os` is never imported in `backend/app/services/embedding_service.py`. Instantiating `EmbeddingService()` without an explicit `provider` when `NVIDIA_API_KEY` is unset or raises an error will crash with `NameError: name 'os' is not defined`.
2. **[P0] `AUTH_DEV_MODE=True` Bypasses Production Stub Ban**: Lines 223 & 243 treat `settings.AUTH_DEV_MODE` as a test environment (`is_test_env = ... or settings.AUTH_DEV_MODE`). Because `AUTH_DEV_MODE` defaults to `True` in `config.py:56`, production deployments that do not override it silently fall back to `StubEmbeddingProvider`.
3. **[P1] Missing `input_type` (`passage` vs `query`) for `nvidia/nemotron-3.5-embed-1b`**: Per official NVIDIA NIM documentation, `nvidia/nemotron-3.5-embed-1b` is an **asymmetric** 2048-dim retrieval model requiring `input_type="passage"` for document indexing and `input_type="query"` for search queries; omitting it causes severe retrieval accuracy degradation. `NvidiaEmbeddingProvider._embed_batch_with_retry` (`embedding_service.py:91`) sends only `model` and `input` without `input_type`.
4. **[P1] Model & Embedding-Space Consistency / Re-Indexing**:
   - `config.py:37` specifies `nvidia/nemotron-3.5-embed-1b` (`EMBEDDING_DIM=2048`), while `embedding_service.py:41` docstring references `nvidia/nemotron-3-embed-1b` and existing SQLite chunks may contain `stub-deterministic-2048` vectors.
   - Matching 2048 dimensions does **not** make vectors from `nemotron-3.5-embed-1b`, `nemotron-3-embed-1b`, and `stub-deterministic-2048` compatible. **Full re-indexing of `document_chunks` is required** whenever changing embedding models.
   - No `IEmbeddingProvider` class (named `BaseEmbeddingProvider`) and **no secondary provider** exist.

---

## 9. Golden Demo Reconciliation

Inspected `backend/test_golden_demo_frozen_regression.py` and verified against `backend/gem_compliance.db`:

| Bidder | Raw PASS % | Clause Compliance Ratio `(P + 0.5*R)/11` | Standalone Score (`cross_source_report=None`) | Fused Composite Reference (Phase 0.7) | Protected by Phase 1.0 Frozen Test? |
|---|---:|---:|---:|---:|---|
| **EnterpriseTech Solutions** | 100.00% (11/0/0) | **100.00%** | **100.00** | 90.45 | Compliance Ratio + Standalone Score |
| **Legacy Hardware** | 9.09% (1/9/1) | **13.64%** | **53.41** | 40.45 | Compliance Ratio + Standalone Score |
| **Apex Systems** | 27.27% (3/5/3) | **40.91%** | **47.95** | 34.77 | Compliance Ratio + Standalone Score |

### Findings
- `test_golden_demo_frozen_regression.py` **does** execute `ScoringAndRankingService.calculate_bidder_score()` (not hardcoded output), confirming standalone scores (`100.00`, `53.41`, `47.95`) and Clause Compliance Ratios (`100.00%`, `13.64%`, `40.91%`).
- **[P2] Scope Gap**: Line 130 passes `cross_source_report=None` and line 116 hardcodes `"override_status": None`, so **fused multi-source scores (`90.45, 40.45, 34.77`) are not exercised** by this regression test.

---

## 10. Full Test-Suite Reconciliation

| Category | Count | Details / Observed Evidence |
|---|---:|---|
| **Default Discovery (`pytest --collect-only`)** | **305** + 1 Error | `pytest.ini` pattern: `test_unit_*.py test_api_*.py test_phase*.py test_database_*.py` |
| **Collection Error** | **1** | `test_api_direct.py` fails collection: `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'` |
| **Excluded by `pytest.ini`** | **10 files** | Includes all 4 new Phase 1.0 files (`test_enterprise_auth.py`, `test_enterprise_tenant_rbac.py`, `test_enterprise_audit.py`, `test_golden_demo_frozen_regression.py` = 10 tests) + `test_integration_*`, `test_day2_*`, `test_live_*`, `test_benchmark.py`, etc. |
| **Safe Suites Executed in Audit** | **111** | 59 (Enterprise Auth/RBAC/Audit/Golden + Compliance Unit + Phase 6 Scoring) + 52 (`test_database_hardening.py` + `test_unit_bidder_retrieval.py` + `test_unit_clause_extraction.py` + `test_phase6_mock_sources.py`) |
| **Passed (Observed)** | **110** | 59/59 in Phase 1.0 + Scoring/Compliance run; 51/52 in safe unit/hardening run |
| **Failed (Observed)** | **1** | `test_database_hardening.py::test_allow_sqlite_fallback_defaults_to_false` FAILED (`ALLOW_SQLITE_FALLBACK` is `True` in `config.py:31`) |
| **Not Run / Blocked by Infra** | **~204** | Statutory adapter/orchestrator/PostgreSQL-dependent suites and integration/live-API suites were not run because PostgreSQL 16 (`localhost:5432`) is unavailable and live DB mutations were prohibited. |

---

## 11. Frontend Readiness

Inspected `frontend/src/lib/api-client.ts`, `frontend/src/app/layout.tsx`, and `frontend/next.config.mjs`:
- **Current State**: `api-client.ts` uses plain `fetch()` calls to `API_BASE_URL` (`http://localhost:8000`) with **no** `Authorization: Bearer ...` header injection, **no** `credentials: "include"` for `HttpOnly` refresh cookies, **no** `401`/`403` interceptor or refresh-and-retry logic, **no** login/register UI, **no** protected route middleware, and **no** organization/role context.
- **Smallest Safe Phase 1.1 Integration Architecture**:
  1. Add a centralized `apiFetch()` wrapper in `api-client.ts` holding the short-lived access token **in memory** (not `localStorage`) and sending `credentials: "include"` on `/api/v1/auth/*` calls.
  2. On `401`, trigger a single-flight `POST /api/v1/auth/refresh` call (deduplicated promise) and retry the original request; on refresh failure, redirect to `/login`.
  3. Add React `AuthProvider` hydrated via `POST /api/v1/auth/refresh` -> `GET /api/v1/auth/me` on app boot, exposing `user`, `organization`, `roles`, `permissions`, and `logout()`.
  4. Gate UI controls (upload, clause edit, override, audit log viewer) by `permissions` and redirect unauthenticated users to `/login`.

---

## 12. Critical and High-Risk Defects Summary

| ID | Severity | Component | Defect Summary |
|---|---|---|---|
| **F-01** | **P0** | `tenders.py`, `bidders.py`, `evaluations.py`, `statutory.py`, `verification_intelligence.py` | Unauthenticated access & cross-tenant data read/write/override bypass via missing auth dependencies and `get_optional_user` returning `None`. |
| **F-02** | **P0** | `tenders.py`, `bidders.py`, `evaluations.py`, `statutory.py`, `verification_intelligence.py` | Missing `require_permission()` RBAC enforcement on all business endpoints except `GET /api/v1/audit/logs`. |
| **F-03** | **P0** | PostgreSQL / SQLite Schema | No PostgreSQL RLS policies; SQLite `tenders.organization_id` has no DB-level FK constraint. |
| **F-04** | **P0** | `embedding_service.py` | Missing `import os` causes `NameError` at runtime; `AUTH_DEV_MODE=True` permits `StubEmbeddingProvider` by default. |
| **F-05** | **P1** | `auth_service.py` | Concurrent refresh token TOCTOU race condition (missing row lock / atomic conditional update). |
| **F-06** | **P1** | `deps.py` | `require_permission()` reads stale JWT `token_permissions` instead of live DB roles; `get_optional_user` throws HTTP 500 on invalid/expired JWT. |
| **F-07** | **P1** | `0001_initial_baseline.py`, `0002_enterprise_foundation.py` | `0001` missing `statutory_verification_records` & `mock_*` tables and uses `ARRAY(Float)` instead of `Vector(2048)`; `0002` `downgrade()` crashes on SQLite. |
| **F-08** | **P1** | `embedding_service.py` | Missing `input_type="passage"`/`"query"` for asymmetric `nvidia/nemotron-3.5-embed-1b`; no re-indexing migration/check. |
| **F-09** | **P1** | `auth.py`, `auth_service.py` | Open public `/register` creates pre-verified `ORG_ADMIN` accounts with no verification or rate limiting. |
| **F-10** | **P2** | `config.py`, `test_database_hardening.py` | `ALLOW_SQLITE_FALLBACK=True` fails hardening test; insecure default `JWT_SECRET_KEY` has no prod startup guard. |
| **F-11** | **P2** | `audit_service.py`, `audit_logs` | Application-only append convention (no DB immutability triggers); pagination `total` returns page length instead of `COUNT(*)`. |
| **F-12** | **P2** | `pytest.ini`, `test_golden_demo_frozen_regression.py` | New enterprise/regression tests excluded from default `pytest` discovery; fused Golden Demo scores (`90.45/40.45/34.77`) not tested. |

---

## 13. Recommended Remediation Order

1. **Lock Down All API Routes (F-01, F-02)**: Replace `get_optional_user` with `get_current_active_user` + `require_permission(...)` across `tenders.py`, `bidders.py`, `evaluations.py`, `statutory.py`, and `verification_intelligence.py`; enforce `validate_tender_tenant_access` on every tender- and bidder-scoped route (removing `if not user: return`).
2. **Fix `EmbeddingService` Runtime Crash & Contract (F-04, F-08)**: Add `import os`, decouple `AUTH_DEV_MODE` from production stub prohibition, pass `input_type="passage"` / `"query"` for `nvidia/nemotron-3.5-embed-1b`, and document/run chunk re-indexing.
3. **Fix Session & Auth Edge Cases (F-05, F-06, F-09, F-10)**: Use atomic `UPDATE ... WHERE revoked_at IS NULL` in `rotate_refresh_token`, catch JWT errors in `get_optional_user` (if retained anywhere), validate live DB permissions or shorten/revoke sessions, add startup guard on `JWT_SECRET_KEY`, and restore `ALLOW_SQLITE_FALLBACK=False` default (overriding via `.env` in dev).
4. **Repair Alembic Migrations & Audit Query (F-03, F-07, F-11)**: Add missing tables and `Vector(2048)` to `0001_initial_baseline.py`, fix `0002` SQLite batch downgrade/FK, add PostgreSQL RLS migration/runbook, and fix `COUNT(*)` in `AuditService.get_organization_audit_logs`.
5. **Reconcile Test Suite & Golden Demo (F-12)**: Update `pytest.ini` to discover `test_enterprise_*.py` and `test_golden_demo_*.py`, add fused-score Golden Demo verification, and run full suite against PostgreSQL 16 + pgvector.

---

## 14. Phase 1.1 Readiness Decision

**Recommendation to Project Owner**: **DO NOT AUTHORIZE Phase 1.1** yet.

Proceeding to frontend authentication integration while `bidders.py`, `evaluations.py`, `statutory.py`, `verification_intelligence.py`, and `tenders.py` permit unauthenticated cross-tenant access and `EmbeddingService` has an `import os` `NameError` would build a UI on top of an insecure and partially broken backend. Complete the remediation items in Section 13, re-verify against PostgreSQL 16 + pgvector, and then authorize Phase 1.1.
