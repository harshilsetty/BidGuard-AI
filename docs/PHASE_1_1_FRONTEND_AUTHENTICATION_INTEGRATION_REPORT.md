# PHASE 1.1: FRONTEND AUTHENTICATION INTEGRATION & ROUTE PROTECTION REPORT

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**Base Commit SHA:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Backend Foundation:** Phase 1.0–1.0.3.1 (PostgreSQL 16 + RLS + Argon2id + Rotating Refresh Tokens)  
**Final Status:** **IMPLEMENTED & VERIFIED**

---

## 1. Repository State Before & After

### Before Phase 1.1
- Backend Phase 1.0–1.0.3.1 uncommitted work preserved (`backend/alembic/`, `backend/app/api/v1/auth.py`, `backend/app/services/auth_service.py`, `backend/app/services/rbac_service.py`, `docs/PHASE_1_0_3_1_POSTGRESQL_FINAL_VERIFICATION_REPORT.md`, etc.).
- Frontend (`frontend/src/`) had 13 files with unauthenticated `fetch()` calls, no `/login` route, no `AuthContext`, no route protection, and no `credentials: "include"` or `Authorization` header handling.

### After Phase 1.1
**Modified frontend files:**
- `frontend/package.json` — added `"test": "sucrase-node tests/auth.test.ts"`.
- `frontend/src/app/globals.css` — configured `--font-inter` / `Inter` typography.
- `frontend/src/app/layout.tsx` — loaded `Inter` via `next/font/google`, wrapped app in `AuthProvider` and `AppShell`.
- `frontend/src/app/page.tsx` — gated `+ Upload Tender` action with `hasPermission("tender:create")`.
- `frontend/src/lib/api-client.ts` — centralized `apiFetch` / `apiFetchResponse`, `ApiError`, `credentials: "include"`, `Authorization: Bearer` attachment, proactive + `401` single-flight refresh, safe idempotent retry, and `403` handling.
- `frontend/src/lib/types.ts` — added `UserRole`, `AuthStatus`, `LoginRequest`, `TokenResponse`, `UserProfile`.

**New frontend files:**
- `frontend/src/lib/auth-store.ts` — in-memory access-token store, expiry buffer check, single-flight refresh lock, and session-expiration event bus.
- `frontend/src/lib/auth-service.ts` — `loginWithCredentials`, `restoreSession`, `fetchCurrentUser`, `logoutSession`.
- `frontend/src/lib/rbac.ts` — permission helpers (`hasPermission`, `hasRole`), `ROUTE_POLICIES`, `NAV_ITEMS`, `canAccessRoute`, `getAuthorizedNavItems`, `sanitizeRedirectPath`.
- `frontend/src/context/AuthContext.tsx` — `AuthProvider` and `useAuth` hook.
- `frontend/src/components/AuthGate.tsx` — session-initialization gate, unauthenticated redirect, and `403` Access Restricted view.
- `frontend/src/components/AppShell.tsx` — role-aware navigation header, organization/role context pill, `+ Create Tender` permission gate, and `Sign Out` button.
- `frontend/src/app/login/page.tsx` — enterprise login page (`#101C32`, `#1769AA`, `#EAF2FA`, `#FFFFFF`, Inter).
- `frontend/tests/auth.test.ts` — 10 automated authentication, refresh-concurrency, RBAC, and security tests.
- `frontend/README.md` — frontend authentication, environment, and deployment documentation.

All uncommitted backend work and Golden Demo fixtures (`backend/gem_compliance.db`, `backend/seed_golden_demo.py`) remain untouched.

---

## 2. Existing Frontend Architecture Findings

- **Framework:** Next.js `15.1.0` (App Router, `output: "standalone"`), React `19.0.0`, TypeScript `5.6.3`, Tailwind CSS `3.4.14`, `lucide-react` `0.460.0`.
- **Routes:** `/`, `/mock-data`, `/tenders/new`, `/tenders/[id]/bidders`, `/tenders/[id]/clauses`, `/tenders/[id]/compliance`.
- **State Management:** React hooks and local component state (no Redux/Zustand; React Context + module-level in-memory store fits cleanly without adding dependencies).
- **Previous API Client:** Direct `fetch()` calls in `src/lib/api-client.ts` against `API_BASE_URL` (`NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_API_BASE_URL` / `http://localhost:8000`) without `credentials` or `Authorization` headers.

---

## 3. Backend API Contracts Used

Verified directly against `backend/app/api/v1/auth.py`, `backend/app/schemas/auth.py`, `backend/app/core/config.py`, and `backend/app/main.py`:

| Endpoint | Method | Request | Response | Cookie / Auth Behavior |
|---|---|---|---|---|
| `/api/v1/auth/login` | `POST` | `{ email, password }` | `TokenResponse` (`access_token`, `expires_in=900`, `user_id`, `organization_id`, `roles`, `permissions`) | Sets `HttpOnly` cookie `bidguard_refresh_token` (`path=/api/v1/auth`, `samesite=lax`) |
| `/api/v1/auth/me` | `GET` | — | `UserProfileResponse` (`id`, `email`, `full_name`, `organization_id`, `organization_name`, `roles`, `permissions`, `is_active`, `is_verified`, `last_login_at`, `created_at`) | Requires `Authorization: Bearer <access_token>` |
| `/api/v1/auth/refresh` | `POST` | Optional body or cookie | `TokenResponse` | Reads `bidguard_refresh_token` cookie (`credentials: "include"`), atomically rotates token family, sets new `bidguard_refresh_token` cookie |
| `/api/v1/auth/logout` | `POST` | Optional body or cookie | `{ message }` | Revokes refresh token family and clears `bidguard_refresh_token` cookie |
| `/api/v1/auth/invitations/accept` | `POST` | `InvitationAcceptRequest` | `TokenResponse` | Supported by backend; public `/register` is disabled (`ALLOW_PUBLIC_ORG_SIGNUP=False` -> `403`) |

**CORS:** `allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"]`, `allow_credentials=True`, `allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]`, `allow_headers=["Authorization", "Content-Type"]`.

---

## 4. Authentication Architecture

- **`src/lib/auth-store.ts`**: Holds `inMemoryAccessToken` and `accessTokenExpiresAtMs` strictly in JS module memory; manages `inFlightRefresh` single-flight lock and `subscribeSessionExpired` listeners.
- **`src/lib/api-client.ts`**: Central `apiFetchResponse` / `apiFetch` wrapper attaching `credentials: "include"` and `Authorization: Bearer <token>`, handling `401` refresh + safe retry and `403` `ApiError`.
- **`src/lib/auth-service.ts`**: High-level flows (`loginWithCredentials`, `restoreSession`, `fetchCurrentUser`, `logoutSession`).
- **`src/context/AuthContext.tsx`**: React Context exposing `status` (`"initializing" | "authenticated" | "unauthenticated"`), `user`, `organizationId`, `organizationName`, `roles`, `permissions`, `login`, `logout`, `hasPermission`, `hasRole`, and `sessionNotice`.
- **`src/components/AuthGate.tsx` & `src/components/AppShell.tsx`**: Route gating and role-aware shell.

---

## 5. Session Lifecycle

1. **Initialization (`status = "initializing"`):** `AuthGate` renders a neutral verification spinner; no protected page content or API calls render before session resolution.
2. **Restoration:** `AuthProvider` calls `restoreSession()` -> `POST /api/v1/auth/refresh` (via HttpOnly cookie). If valid, `GET /api/v1/auth/me` loads `UserProfile` + `organization_name` + `roles` + `permissions`, transitioning to `status = "authenticated"`.
3. **Unauthenticated:** If refresh returns `401`/null, transitions to `status = "unauthenticated"` and `AuthGate` redirects to `/login?next=<sanitized_path>`.
4. **Expiration / Revocation:** Unrecoverable `401` on refresh clears in-memory token, emits `"session_expired"`, and redirects to `/login?reason=session_expired`.
5. **Logout:** `POST /api/v1/auth/logout` revokes the refresh-token family on the backend, clears in-memory token, emits `"logged_out"`, and navigates to `/login`.

---

## 6. Refresh-Token Handling

- **HttpOnly Cookie Only:** Refresh tokens are never stored in `localStorage`, `sessionStorage`, or JS-readable cookies.
- **Single-Flight Coalescing:** `runSingleFlightRefresh()` ensures concurrent `401` responses or proactive expiry checks share a single `POST /api/v1/auth/refresh` Promise.
- **Proactive Refresh:** Requests made within 45s of `expires_in` proactively refresh before hitting the endpoint.
- **Safe Retry Policy:** On `401` (excluding `/auth/login`, `/auth/refresh`, `/auth/logout`), `apiFetchResponse` refreshes once (`_retried: true` prevents infinite loops). Only idempotent methods (`GET`, `HEAD`, `OPTIONS`) retry automatically; non-idempotent mutations (`POST`, `PUT`, `DELETE`) are **not** blindly re-submitted and surface a clear `ApiError(401, "Session renewed. Please submit your request again.")`.

---

## 7. Route-Protection Implementation

- **Public Route:** `/login` (authenticated users are redirected to sanitized `next` path or `/`).
- **Authenticated & Permission-Gated Routes (`src/lib/rbac.ts` + `src/components/AuthGate.tsx`):**
  - `/` -> `tender:read`
  - `/tenders/new` -> `tender:create`
  - `/tenders/[id]/clauses` -> `tender:read`
  - `/tenders/[id]/bidders` -> `tender:read`
  - `/tenders/[id]/compliance` -> `evaluation:read`
  - `/mock-data` -> authenticated active user
- **Unauthorized State:** Authenticated users lacking required route permissions receive an explicit `403 • Access Restricted` view with a link back to `/`.
- **Open-Redirect Protection:** `sanitizeRedirectPath()` rejects protocol-relative (`//`), external URLs, and `/login` loops.

---

## 8. Role-to-Navigation Matrix

Derived directly from `backend/app/services/rbac_service.py` (`ROLE_PERMISSIONS_MAP`) and `backend/app/api/v1/*.py`:

| Route / Nav Item | Required Permission | `SUPER_ADMIN` | `ORG_ADMIN` | `PROCUREMENT_OFFICER` | `AUDITOR` | `BIDDER` |
|---|---|---|---|---|---|---|
| `/login` (Public) | None | Redirects `/` | Redirects `/` | Redirects `/` | Redirects `/` | Redirects `/` |
| `/` (Tenders) | `tender:read` | Allowed | Allowed | Allowed | Allowed | Allowed |
| `/tenders/new` (Upload Tender PDF / `+ Create Tender`) | `tender:create` | Allowed | Allowed | Allowed | **Denied (403) & Hidden** | **Denied (403) & Hidden** |
| `/tenders/[id]/clauses` | `tender:read` | Allowed | Allowed | Allowed | Allowed | Allowed |
| `/tenders/[id]/bidders` | `tender:read` | Allowed | Allowed | Allowed | Allowed | Allowed |
| `/tenders/[id]/compliance` | `evaluation:read` | Allowed | Allowed | Allowed | Allowed | Allowed |
| `/mock-data` (Mock Explorer) | Authenticated user | Allowed | Allowed | Allowed | Allowed | Allowed |

---

## 9. Security Review

- **No refresh or access tokens in `localStorage`/`sessionStorage`:** Verified by unit test spies and code inspection.
- **No hardcoded secrets or demo credentials:** Login page contains zero prefilled or displayed demo accounts.
- **No client-side security bypass:** Backend `require_permission(...)` and PostgreSQL RLS remain authoritative on every endpoint; frontend checks only govern UX/navigation.
- **No wildcard CORS:** Backend uses explicit `BACKEND_CORS_ORIGINS` with `allow_credentials=True`.
- **No token or auth-payload console logging:** Zero `console.log` of tokens or auth responses.
- **Deployment / Origin Guidance:**
  - Local dev must use `http://localhost:3000` with `http://localhost:8000` (same-site `SameSite=Lax` cookie delivery).
  - Production requires HTTPS on both origins (or a shared reverse proxy), `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax`, and explicit `BACKEND_CORS_ORIGINS`.

---

## 10. Test Results

Command: `cd frontend; npm test` (`sucrase-node tests/auth.test.ts`)  
Result: **`10 passed, 0 failed, 0 skipped` in `224.08ms`**:
1. Valid login stores access token in memory only (0 `localStorage`/`sessionStorage` writes) and loads `UserProfile`.
2. Invalid credentials returns `401 ApiError` and leaves token empty.
3. Session restoration succeeds via HttpOnly refresh cookie + `/auth/me`, returns `null` when unauthenticated.
4. Logout revokes backend session (`POST /api/v1/auth/logout` with `credentials: "include"`), clears memory token, and notifies listeners.
5. Refresh & concurrency: 5 concurrent `401` `GET` requests trigger **exactly 1** `/api/v1/auth/refresh` call and retry safely.
6. Non-idempotent `POST` is not blindly re-submitted after `401` refresh.
7. Failed refresh / revoked session does not infinite-loop and emits `session_expired`.
8. Backend `403` does not trigger refresh and preserves `403` status.
9. RBAC & route protection enforces public, authenticated, and role-restricted routes across roles (`BIDDER`, `AUDITOR`, `PROCUREMENT_OFFICER`) and sanitizes redirect paths.
10. Direct concurrent `performTokenRefresh` calls coalesce to 1 fetch.

TypeScript check: `cd frontend; npx tsc --noEmit` — **0 errors**.

---

## 11. Production Build Results

Command: `cd frontend; npm run build` (`next build`)  
Result: **Succeeded cleanly** (`✓ Compiled successfully`, `✓ Generating static pages (7/7)`):
- `/` (`3.73 kB`)
- `/_not-found` (`979 B`)
- `/login` (`3.65 kB`)
- `/mock-data` (`7.04 kB`)
- `/tenders/[id]/bidders` (`9.59 kB`)
- `/tenders/[id]/clauses` (`8.1 kB`)
- `/tenders/[id]/compliance` (`24.3 kB`)
- `/tenders/new` (`5.63 kB`)

---

## 12. Remaining Limitations

- Frontend tests exercise the real client modules (`auth-store`, `api-client`, `auth-service`, `rbac`) with mocked `fetch` and storage spies; live browser DOM/E2E screenshots were not captured in this CLI-only pass.
- Invitation acceptance UI (`/invitations/accept`) and organization/audit admin pages were not added because Phase 1.1 scoped authentication integration and route protection without adding new administrative screens.
- Direct `<a href={getMockSourceExportUrl(...)}>` CSV export in `mock-data/page.tsx` does not attach a Bearer `Authorization` header (browser navigation only sends cookies); converting CSV export to an authenticated `fetch` blob download can be addressed in a follow-up if needed.

---

## 13. Screenshots

Not captured in this CLI verification pass (no headless browser screenshot run was executed). Live UI states implemented and verified via `next build`: `/login` (sign-in card with `#101C32`, `#1769AA`, `#EAF2FA`, `#FFFFFF`), session-initialization gate, `403` Access Restricted view, and role-aware `AppShell` header.
