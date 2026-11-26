# BidGuard AI — Authoritative Role-Permission Matrix

**Source of Truth:**
- `backend/app/services/rbac_service.py` (`SYSTEM_ROLES`, `SYSTEM_PERMISSIONS`, `ROLE_PERMISSIONS_MAP`)
- `backend/app/api/deps.py` (`require_permission`, `get_current_active_user`, `SUPER_ADMIN` platform bypass)
- `backend/app/api/v1/*.py` (FastAPI route-level `Depends(...)` enforcement)

> **Security Invariant:** Frontend permission checks govern navigation, route UX, and action-button visibility only. The backend remains the final authority for every operation and tenant boundary (enforced via live DB `UserRole`/`RolePermission` resolution + PostgreSQL RLS).

---

## 1. System Roles

| Role | Scope | Description |
|---|---|---|
| `SUPER_ADMIN` | `PLATFORM` | Platform-level administrator with full cross-tenant governance (`require_permission` grants all permissions). |
| `ORG_ADMIN` | `ORGANIZATION` | Organization administrator managing users, roles, settings, and procurement workflows within their org. |
| `PROCUREMENT_OFFICER` | `ORGANIZATION` | Procurement officer managing tenders, evaluations, and compliance reviews within their org. |
| `AUDITOR` | `ORGANIZATION` | Read-only auditor with verification, evaluation, and audit-log inspection access within their org. |
| `BIDDER` | `ORGANIZATION` | Bidder representative with restricted read access to tenders and evaluations (`tender:read`, `evaluation:read`). |

---

## 2. Permission-to-Role Matrix (`ROLE_PERMISSIONS_MAP`)

| Permission | `SUPER_ADMIN` | `ORG_ADMIN` | `PROCUREMENT_OFFICER` | `AUDITOR` | `BIDDER` |
|---|---|---|---|---|---|
| `organization:read` | Yes | Yes | Yes | Yes | No |
| `organization:update` | Yes | Yes | No | No | No |
| `user:invite` | Yes | Yes | No | No | No |
| `user:manage` | Yes | Yes | No | No | No |
| `tender:create` | Yes | Yes | Yes | No | No |
| `tender:read` | Yes | Yes | Yes | Yes | Yes |
| `tender:update` | Yes | Yes | Yes | No | No |
| `tender:delete` | Yes | No | No | No | No |
| `document:upload` | Yes | Yes | Yes | No | No |
| `document:download` | Yes | Yes | Yes | Yes | No |
| `evaluation:run` | Yes | Yes | Yes | No | No |
| `evaluation:read` | Yes | Yes | Yes | Yes | Yes |
| `evaluation:override` | Yes | Yes | Yes | No | No |
| `audit:read` | Yes | Yes | Yes | Yes | No |
| `audit:export` | Yes | Yes | No | Yes | No |

---

## 3. Backend API Endpoint Enforcement

| Endpoint | Method | Enforced Dependency / Permission |
|---|---|---|
| `/api/v1/health`, `/api/v1/health/nvidia` | `GET` | Public |
| `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/logout` | `POST` | Public / HttpOnly cookie |
| `/api/v1/auth/invitations/validate`, `/api/v1/auth/invitations/accept` | `GET` / `POST` | Public (token-bound, rate-limited) |
| `/api/v1/auth/me` | `GET` | `get_current_active_user` |
| `/api/v1/auth/invitations` | `POST` | `require_permission("user:invite")` |
| `/api/v1/organizations/me`, `/api/v1/organizations/roles`, `/api/v1/organizations/me/members` | `GET` | `require_permission("organization:read")` |
| `/api/v1/organizations/me` | `PUT` | `require_permission("organization:update")` |
| `/api/v1/organizations/me/members/{id}/role`, `/status`, `DELETE` | `PUT` / `DELETE` | `require_permission("user:manage")` |
| `/api/v1/organizations/me/invitations*` | `GET` / `POST` | `require_permission("user:invite")` |
| `/api/v1/audit/logs` | `GET` | `require_permission("audit:read")` |
| `/api/v1/tenders`, `/api/v1/tenders/{id}`, `/api/v1/tenders/{id}/clauses` | `GET` | `require_permission("tender:read")` |
| `/api/v1/tenders/upload` | `POST` | `require_permission("tender:create")` |
| `/api/v1/tenders/{id}/extract`, `/clauses*`, `/confirm` | `POST` / `PUT` / `DELETE` | `require_permission("tender:update")` |
| `/api/v1/tenders/{id}/bidders`, `/bidders/{bidder_id}` | `GET` | `require_permission("tender:read")` |
| `/api/v1/tenders/{id}/bidders`, `/bidders/demo` | `POST` | `require_permission("document:upload")` |
| `/api/v1/tenders/{id}/bidders/{bidder_id}` | `DELETE` | `require_permission("tender:delete")` |
| `/api/v1/tenders/{id}/evaluations/run`, `/statutory/verify`, `/recommendation` (POST) | `POST` | `require_permission("evaluation:run")` |
| `/api/v1/tenders/{id}/evaluations/matrix`, `/score`, `/ranking`, `/statutory/status`, `/review-queue`, `/verification-summary`, `/verification-history` | `GET` | `require_permission("evaluation:read")` |
| `/api/v1/tenders/{id}/evaluations/{eval_id}/override`, `/bidders/{bidder_id}/review` | `POST` | `require_permission("evaluation:override")` |
| `/api/v1/tenders/{id}/bidders/{bidder_id}/audit` | `GET` | `require_permission("audit:read")` |
| `/api/v1/mock-sources*` | `GET` | `get_current_active_user` |

---

## 4. Frontend Route & Action Mapping

| Frontend Route | Required Permission(s) | Allowed Roles |
|---|---|---|
| `/login`, `/invite/accept` | Public | Anonymous & Authenticated |
| `/` (Role-Aware Workspace & Tenders) | Authenticated (`tender:read` for all 5 roles) | All 5 roles (rendered workspace adapts to live permissions) |
| `/tenders/new` | `tender:create` | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER` |
| `/tenders/[id]/clauses` | `tender:read` (`tender:update` to edit/confirm) | All 5 roles (read-only for `AUDITOR`, `BIDDER`) |
| `/tenders/[id]/bidders` | `tender:read` (`document:upload` to add) | All 5 roles (read-only for `AUDITOR`, `BIDDER`) |
| `/tenders/[id]/compliance` | `evaluation:read` (`evaluation:run`/`override` to mutate) | All 5 roles (read-only for `AUDITOR`, `BIDDER`) |
| `/organization` | `organization:read` | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER`, `AUDITOR` |
| `/audit` | `audit:read` | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER`, `AUDITOR` |
| `/mock-data` | Authenticated (`get_current_active_user`) | All 5 roles |

---

## 5. Observed Backend Boundaries & Gaps (Documented, Not Altered)

- **Dedicated `BIDDER` submission/profile endpoint:** Not yet implemented (`BIDDER` currently holds `tender:read` + `evaluation:read`; no `/my-bids` bidder-scoped endpoint exists yet).
- **Dedicated `SUPER_ADMIN` cross-tenant org directory endpoint:** Not yet implemented (`/api/v1/organizations/me` scopes to `current_user.organization_id`; platform-wide org listing is a future module).
- **`audit:export` & `tender:delete`:** Defined in `SYSTEM_PERMISSIONS`; `tender:delete` is enforced on `DELETE /bidders/{bidder_id}`, while `audit:export` does not yet have a dedicated export endpoint.
