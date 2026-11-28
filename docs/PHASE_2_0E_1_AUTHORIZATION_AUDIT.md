# Phase 2.0E.1 Authorization & RBAC Audit

**Inspected Sources:** `backend/app/api/v1/tenders.py`, `backend/app/api/router.py`, `backend/app/api/v1/verification_intelligence.py`, `backend/app/api/deps.py`, `backend/app/services/rbac_service.py`, `backend/app/services/organization_service.py`, `backend/app/services/review_service.py`.

---

## 1. Endpoint-by-Endpoint Authorization Matrix

| Endpoint | Dependency | Required Permission | Tenant Check | Roles Allowed |
|---|---|---|---|---|
| `GET /api/v1/tenders/{tender_id}/review-queue` | `require_permission("audit:read")` | `audit:read` | `get_authorized_tender` (404 cross-tenant) | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER`, `AUDITOR` (`BIDDER` -> 403) |
| `GET /api/v1/tenders/{tender_id}/review-workload` | `require_permission("audit:read")` | `audit:read` | `get_authorized_tender` (404 cross-tenant) | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER`, `AUDITOR` (`BIDDER` -> 403) |
| `POST /api/v1/tenders/{tender_id}/review-decisions` | `require_permission("evaluation:override")` | `evaluation:override` | `get_authorized_tender` (404 cross-tenant) | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER` (`AUDITOR`/`BIDDER` -> 403) |
| `POST /api/v1/tenders/{tender_id}/review-assignments` | `require_permission("user:manage")` | `user:manage` | `get_authorized_tender` (404 cross-tenant) | `SUPER_ADMIN`, `ORG_ADMIN` (`PROCUREMENT_OFFICER`/`AUDITOR`/`BIDDER` -> 403) |
| `GET /api/v1/tenders/{tender_id}/review-history` | `require_permission("audit:read")` | `audit:read` | `get_authorized_tender` (404 cross-tenant) | `SUPER_ADMIN`, `ORG_ADMIN`, `PROCUREMENT_OFFICER`, `AUDITOR` (`BIDDER` -> 403) |

---

## 2. Findings

### Finding P1-1: Route Shadowing on `GET /api/v1/tenders/{tender_id}/review-queue`
- In `backend/app/api/router.py`, `tenders_router` (line 20) is mounted before `verification_intelligence_router` (line 25).
- Both routers define `GET /tenders/{tender_id}/review-queue` under `/v1`.
- Empirical probe confirmed `GET /api/v1/tenders/{tid}/review-queue` returns TenderLens keys (`['items', 'limit', 'offset', 'tender_id', 'total']`), completely shadowing Phase 8.4 `OfficerReviewQueueResponse` (which `frontend/src/lib/api-client.ts:631` `fetchTenderReviewQueue` still calls).

### Finding P2-1: `assign_reviewer` Does Not Validate Assignee Reviewer Permissions
- `TenderReviewService.assign_reviewer` (`review_service.py:208-222`) checks `User.id == assignee_user_id`, `User.organization_id == tender.organization_id`, and `User.is_active == True`, **but does not verify that the assignee holds `evaluation:override`**.
- An admin can assign a `BIDDER` or `AUDITOR` to `assigned_reviewer_id`. Note: the assignee still cannot submit decisions because `POST /review-decisions` enforces `require_permission("evaluation:override")`, so assignment does not escalate privileges.

### Account-Lifecycle & Member Removal Check
- `User` (`backend/app/models/user.py:15-20`) has a single `organization_id` FK (1-to-1 user-to-organization model; multi-organization membership for a single `User` row does not exist in the current schema).
- `OrganizationService.remove_member` (`organization_service.py:417-425`) deletes `UserRole`, revokes `RefreshToken`, anonymizes email to `removed-{id}@removed.local`, and sets `is_active = False`.
- Empirical probe confirmed that a removed member using an unexpired JWT access token is immediately rejected with `403 Forbidden: User account is deactivated.` because `get_current_user` (`deps.py:94`) checks live `user.is_active` and live `UserRole` permissions.
- `assigned_reviewer_id` has `ForeignKey("users.id", ondelete="SET NULL")`; because `remove_member` soft-deactivates rather than deleting `users`, existing assignments to a removed member remain until reassigned (low-impact metadata artifact).
