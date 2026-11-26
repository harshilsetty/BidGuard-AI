# BidGuard AI — Frontend (`Next.js 15` + `React 19` + `TypeScript`)

## Enterprise Authentication & Route Protection (Phase 1.1)

The frontend integrates with the Phase 1.0–1.0.3.1 FastAPI authentication and RBAC backend:

- **Access Token Storage:** Short-lived JWT access tokens (`15m`) are stored **strictly in module memory** (`src/lib/auth-store.ts`), never in `localStorage` or `sessionStorage`.
- **Refresh Token Handling:** Long-lived refresh tokens (`7d`) are managed exclusively by the backend via the `HttpOnly` cookie `bidguard_refresh_token` (`path=/api/v1/auth`). All API requests use `credentials: "include"`.
- **Single-Flight Refresh:** Concurrent `401` responses or proactive refresh checks coalesce onto a single `POST /api/v1/auth/refresh` request.
- **Route Protection & Role-Aware Navigation:** `AuthGate` (`src/components/AuthGate.tsx`) blocks protected routes until session restoration completes, redirects unauthenticated users to `/login`, and renders a `403` state when a user lacks route permissions defined in `src/lib/rbac.ts`. The backend remains the final authority for every authorization check.

## Environment & Origin Requirements

- `NEXT_PUBLIC_API_URL` (or `NEXT_PUBLIC_API_BASE_URL`): defaults to `http://localhost:8000`.
- **Local Development:** Run the frontend on `http://localhost:3000` (same-site with `http://localhost:8000` so `SameSite=Lax` cookies are sent).
- **Production:** Serve frontend and backend over **HTTPS** under the same parent site (or reverse-proxy `/api` under the frontend origin) with backend `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax` (or `none` with HTTPS if cross-site), and explicit `BACKEND_CORS_ORIGINS` (no wildcards).

## Scripts

```bash
npm run dev      # Start Next.js dev server on port 3000
npm test         # Run frontend auth, RBAC, and security tests (sucrase-node)
npm run build    # Production Next.js build
```
