# PHASE 1.2: ORGANIZATION ONBOARDING, INVITATION MANAGEMENT & MEMBERSHIP CONTROL REPORT

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**Base Commit SHA:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Backend Foundation:** Phase 1.0–1.0.3.1 (PostgreSQL 16 + RLS + Argon2id + Rotating Refresh Tokens + Alembic `0006_invitation_revocation`)  
**Frontend Foundation:** Phase 1.1 (In-Memory Access Token + HttpOnly Refresh Cookie + `AuthGate` + `AppShell`)  
**Final Verdict:** **ACCEPTED**

---

## 1. Repository State Before & After

### Before Phase 1.2
- Uncommitted Phase 1.0–1.1 backend and frontend foundation preserved.
- Backend supported `POST /api/v1/auth/invitations` and `POST /api/v1/auth/invitations/accept`, but lacked:
  - `revoked_at` column/migration on `organization_invitations`
  - Pre-acceptance token validation (`GET /api/v1/auth/invitations/validate`)
  - Organization profile retrieval/update, role listing, member directory/role/status/removal, and invitation list/revoke/resend endpoints.
- Frontend lacked `/organization` administration views and `/invite/accept` onboarding flow.

### After Phase 1.2
**Backend Additions & Narrowly Scoped Updates:**
- `backend/app/models/auth.py` — added `revoked_at` to `OrganizationInvitation`.
- `backend/alembic/versions/0006_invitation_revocation.py` — forward migration adding `revoked_at` (`down_revision = '0005_audit_immutability'`).
- `backend/app/schemas/auth.py` — added `InvitationValidateResponse`.
- `backend/app/services/auth_service.py` — added `validate_invitation_token()`, enforced active organization / duplicate pending invitation / existing-user checks in `create_invitation()`, added `_enable_auth_lookup()` + `revoked_at.is_(None)` check in `accept_invitation()`.
- `backend/app/api/v1/auth.py` — added `GET /api/v1/auth/invitations/validate`.
- `backend/app/schemas/organization.py` — schemas for organization overview/update, roles, members, and invitations.
- `backend/app/services/organization_service.py` — `OrganizationService` with tenant isolation, last-admin protection, self-modification blocks, `SUPER_ADMIN` assignment blocks, refresh-token revocation on deactivation, and audit logging.
- `backend/app/api/v1/organizations.py` — `/api/v1/organizations/*` router.
- `backend/app/api/router.py` — mounted `organizations_router` under `/api/v1`.
- `backend/test_enterprise_org_invitations.py` — 3 comprehensive PostgreSQL integration & security tests.

**Frontend Additions & Updates:**
- `frontend/src/lib/types.ts` — added Phase 1.2 organization, role, member, and invitation types.
- `frontend/src/lib/rbac.ts` — added `/invite/accept` to `PUBLIC_ROUTES`, `/organization` route policy (`organization:read`), and `Organization` nav item.
- `frontend/src/lib/api-client.ts` — added organization, member, and invitation API client methods.
- `frontend/src/lib/auth-service.ts` — added `acceptInvitationAndLogin()`.
- `frontend/src/context/AuthContext.tsx` — exposed `acceptInvitation`.
- `frontend/src/components/AuthGate.tsx` — allowed `/invite/accept` without redirecting away if already authenticated.
- `frontend/src/app/organization/page.tsx` — Organization Overview, Organization Profile, Team Members, Invitations, and Role Management UI.
- `frontend/src/app/invite/accept/page.tsx` — dedicated invitation validation & account setup page.
- `frontend/tests/auth.test.ts` — updated RBAC & route tests for `/organization` and `/invite/accept`.
- `frontend/README.md` — documented Phase 1.2 onboarding and invitation setup.

---

## 2. Existing Organization & Invitation Architecture

- **Organization Model (`Organization`):** `id`, `name`, `slug`, `domain`, `is_active`, `created_at`, `updated_at`.
- **Invitation Model (`OrganizationInvitation`):** `id`, `organization_id`, `email`, `role_name`, `token_hash` (SHA-256), `expires_at`, `accepted_at`, `revoked_at`, `invited_by_user_id`, `created_at`, `updated_at`.
- **Public Org Registration:** Remains disabled (`ALLOW_PUBLIC_ORG_SIGNUP = False` -> `403 Forbidden`). Organizations are provisioned via controlled bootstrap/`SUPER_ADMIN` seeding and team members join via single-use invitations.

---

## 3. Backend API Contracts Used

| Endpoint | Method | Permission | Purpose |
|---|---|---|---|
| `/api/v1/organizations/me` | `GET` | `organization:read` | Organization profile + active/total member & pending invitation counts |
| `/api/v1/organizations/me` | `PUT` | `organization:update` | Update editable fields (`name`, `domain`) |
| `/api/v1/organizations/roles` | `GET` | `organization:read` | List system roles, permissions, and org-admin assignability |
| `/api/v1/organizations/me/members` | `GET` | `organization:read` | Server-side search (`q`), `role`, `is_active` filtering, and pagination (`limit`, `offset`) |
| `/api/v1/organizations/me/members/{user_id}/role` | `PUT` | `user:manage` | Update member role (blocks self, `SUPER_ADMIN`, last `ORG_ADMIN` demotion) |
| `/api/v1/organizations/me/members/{user_id}/status` | `PUT` | `user:manage` | Deactivate/reactivate member (blocks self & last `ORG_ADMIN`, revokes refresh tokens) |
| `/api/v1/organizations/me/members/{user_id}` | `DELETE` | `user:manage` | Remove member (blocks self, `SUPER_ADMIN`, last `ORG_ADMIN`) |
| `/api/v1/auth/invitations` | `POST` | `user:invite` | Create single-use 48h invitation (blocks `SUPER_ADMIN`, duplicates, existing users) |
| `/api/v1/organizations/me/invitations` | `GET` | `user:invite` | List invitations with computed status (`PENDING`, `ACCEPTED`, `EXPIRED`, `REVOKED`) |
| `/api/v1/organizations/me/invitations/{id}/revoke` | `POST` | `user:invite` | Revoke pending invitation server-side |
| `/api/v1/organizations/me/invitations/{id}/resend` | `POST` | `user:invite` | Atomically revoke old token and issue fresh single-use invitation |
| `/api/v1/auth/invitations/validate` | `GET` | Public (rate-limited) | Validate token before acceptance without leaking invalid-token org info |
| `/api/v1/auth/invitations/accept` | `POST` | Public (rate-limited) | Atomic single-use claim, user creation, role binding, and token issuance |

---

## 4. Organization Lifecycle

1. **Provisioning:** Controlled bootstrap / `SUPER_ADMIN` creation (public signup disabled).
2. **Profile Management:** `ORG_ADMIN` (`organization:update`) can update `name` and `domain`; `id`, `slug`, `is_active`, and timestamps remain system-managed.
3. **Team Onboarding:** `ORG_ADMIN` (`user:invite`) invites members with permitted organization roles (`ORG_ADMIN`, `PROCUREMENT_OFFICER`, `AUDITOR`, `BIDDER`).
4. **Membership Governance:** `ORG_ADMIN` (`user:manage`) adjusts roles, deactivates/reactivates members, or removes members under backend safeguards.

---

## 5. Invitation Lifecycle

States computed server-side (`compute_invitation_status`):
- **`PENDING`:** `revoked_at IS NULL AND accepted_at IS NULL AND expires_at >= now`
- **`ACCEPTED`:** `accepted_at IS NOT NULL`
- **`REVOKED`:** `revoked_at IS NOT NULL`
- **`EXPIRED`:** `revoked_at IS NULL AND accepted_at IS NULL AND expires_at < now`

Resending an invitation revokes the previous invitation (`revoked_at = now`) in the same transaction before issuing a new single-use token, ensuring at most one active token exists per invitation cycle.

---

## 6. Role-to-Action Matrix

| Action / Capability | `SUPER_ADMIN` | `ORG_ADMIN` | `PROCUREMENT_OFFICER` | `AUDITOR` | `BIDDER` |
|---|---|---|---|---|---|
| View Org Overview & Profile | Allowed | Allowed | Allowed | Allowed | **Denied (403)** |
| Edit Org Profile (`name`, `domain`) | Allowed | Allowed | **Denied (403)** | **Denied (403)** | **Denied (403)** |
| View Team Members | Allowed | Allowed | Allowed | Allowed | **Denied (403)** |
| Manage Member Roles / Status / Remove | Allowed | Allowed (non-`SUPER_ADMIN`, non-self) | **Denied (403)** | **Denied (403)** | **Denied (403)** |
| View / Create / Revoke / Resend Invitations | Allowed | Allowed (non-`SUPER_ADMIN`) | **Denied (403)** | **Denied (403)** | **Denied (403)** |

---

## 7. Member-Management Functionality

Implemented in `/organization` (Team Members tab) backed by `OrganizationService`:
- Server-side search by name or email (`q`), role filter (`role`), status filter (`is_active`), and pagination (`limit=10`, `offset`).
- Confirmation step before member removal.
- Server-enforced safeguards:
  - No self-role modification, self-deactivation, or self-removal (`403`).
  - No `SUPER_ADMIN` assignment or modification (`403`).
  - Last active `ORG_ADMIN` cannot be demoted, deactivated, or removed (`409 Conflict`).
  - Deactivating a member revokes all active `RefreshToken` rows for that user.

---

## 8. Invitation Acceptance Flow

Implemented at `/invite/accept?token=...` (`frontend/src/app/invite/accept/page.tsx`):
1. Reads `token` from URL query string.
2. Calls `GET /api/v1/auth/invitations/validate?token=...`.
3. Renders explicit error states for `INVALID`, `REVOKED`, `EXPIRED`, `ACCEPTED`, or network failure without exposing organization metadata.
4. For `PENDING` tokens, displays organization name, fixed assigned role (read-only), and masked email hint; if an existing account matches, directs user to `/login`.
5. New users enter their invited work email, full name, and strong password, then submit `POST /api/v1/auth/invitations/accept`.
6. Access token is stored strictly in memory via `AuthContext`, HttpOnly refresh cookie is set by the backend, and the user is redirected to `/`.

---

## 9. Email Delivery Limitations

- Backend SMTP / email provider integration is **not configured** (`email_delivery_status = "NOT_CONFIGURED_OUT_OF_BAND_DELIVERY_REQUIRED"`).
- The UI makes this explicit and never claims an email was sent.
- Authorized administrators (`user:invite`) receive a one-time **Copy Link** (`/invite/accept?token=...`) in transient component state (never persisted in `localStorage`/`sessionStorage`) for out-of-band distribution.

---

## 10. Security Implementation

- **Single-Use Atomic Claim:** `accept_invitation()` performs an atomic conditional `UPDATE` requiring `token_hash`, `email`, `accepted_at IS NULL`, and `revoked_at IS NULL`.
- **No Client-Supplied `organization_id`:** All `/organizations/me*` and `/auth/invitations` endpoints derive `organization_id` exclusively from `current_user.organization_id`.
- **Audit Logging:** `ORGANIZATION_PROFILE_UPDATED`, `MEMBER_ROLE_UPDATED`, `MEMBER_STATUS_UPDATED`, `MEMBER_REMOVED`, `AUTH_INVITATION_CREATED`, `AUTH_INVITATION_REVOKED`, `AUTH_INVITATION_RESENT`, and `AUTH_INVITATION_ACCEPTED` recorded in immutable `audit_logs`.

---

## 11. Tenant-Isolation Verification

Verified in `backend/test_enterprise_org_invitations.py::test_member_management_safeguards_and_cross_tenant_isolation` and `backend/test_postgres_rls_and_concurrency.py` under restricted `bidguard_app` (`NOSUPERUSER`, `NOBYPASSRLS`):
- Org A admin cannot list Org B members.
- Org A admin attempting to change role (`PUT`), remove (`DELETE`), or revoke invitations (`POST`) for Org B targets receives `404 Not Found`.
- All 13 tenant-scoped PostgreSQL tables remain protected with `FORCE ROW LEVEL SECURITY`.

---

## 12. Frontend & Backend Test Results

- **Alembic Fresh Migration (`bidguard_fresh_test`):** `0001_initial_baseline -> 0006_invitation_revocation (head)` succeeded.
- **Full Backend `pytest` Suite (`cd backend; python -m pytest -q --tb=short`):** **`326 passed, 0 failed, 0 errors, 0 skipped`** in `240.44s (0:04:00)` (includes `test_enterprise_org_invitations.py` 3/3, `test_postgres_rls_and_concurrency.py` 2/2, `test_enterprise_auth.py` 4/4, and `test_golden_demo_frozen_regression.py` 4/4).
- **Frontend TypeScript (`cd frontend; npx tsc --noEmit`):** **0 errors**.
- **Frontend Test Suite (`cd frontend; npm test`):** **`10 passed, 0 failed, 0 skipped`** in `104.00ms`.

---

## 13. Production Build Result

- **Command:** `cd frontend; npm run build` (`next build`)
- **Result:** Succeeded cleanly (`✓ Compiled successfully`, `✓ Generating static pages (9/9)`), including `/organization` (`9.01 kB`) and `/invite/accept` (`4.89 kB`).

---

## 14. Remaining Risks

- Email delivery remains out-of-band until an approved email provider is configured in a later phase.
- Existing-user invitation acceptance (adding an already-registered user to a second organization) is blocked (`409 Conflict`) by the current single-organization-per-user data model (`users.organization_id` is non-null 1:N).
- Frontend tests cover client/RBAC logic with mocked `fetch`; live headless-browser E2E screenshots were not captured in this CLI pass.

---

## 15. Screenshots

Not captured in this CLI verification pass. All UI routes (`/login`, `/organization`, `/invite/accept`) compiled and prerendered cleanly in `next build`.
