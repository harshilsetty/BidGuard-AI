# BidGuard AI — Product Readiness Gap Register

**Assessment Phase:** Phase 1.4 (Enterprise Application Integration & Readiness)  
**Repository:** `harshilsetty/BidGuard-AI`  
**Severity Scale:** `P0` (Critical security/data integrity) • `P1` (Important release blocker) • `P2` (Significant usability/functionality gap) • `P3` (Enhancement)

---

## Summary Table

| ID | Severity | Category | Description | Blocks TenderLens (Phase 2.0)? |
|---|---|---|---|---|
| `GAP-01` | `P1` | Operational / Backend | Tender upload does not sanitize `file.filename` (`os.path.basename`) or enforce `settings.MAX_UPLOAD_SIZE_MB` in `upload_tender_pdf` | **Yes (Recommended before Phase 2.0)** |
| `GAP-02` | `P1` | Platform Infrastructure | Clause extraction (`POST /tenders/{id}/extract`) runs synchronously inside the HTTP request rather than a background worker/task queue | **Yes (For large multi-page PDFs)** |
| `GAP-03` | `P2` | Operational / Deployment | Email transport for invitations is not configured (`NOT_CONFIGURED_OUT_OF_BAND_DELIVERY_REQUIRED`); admin copies single-use link manually | No |
| `GAP-04` | `P2` | Missing Business Functionality | Dedicated `BIDDER`-scoped submission/profile endpoints (`/my-bids`) and `SUPER_ADMIN` cross-tenant org directory do not yet exist | No |
| `GAP-05` | `P2` | Backend Security / Infra | `mock-sources/{source}/export/csv` browser `<a href>` download does not attach `Authorization: Bearer` header | No |
| `GAP-06` | `P2` | Missing Business Functionality | `audit:export` permission exists in `SYSTEM_PERMISSIONS` without a dedicated export endpoint | No |
| `GAP-07` | `P3` | Frontend / E2E Testing | No headless browser E2E suite (e.g., Playwright) is installed in `frontend/package.json`; frontend tests run via `sucrase-node` with mocked `fetch` | No |
| `GAP-08` | `P3` | Operational / Storage | Uploaded tender PDFs are stored on local container filesystem (`UPLOAD_DIR`) rather than object storage (S3/MinIO) | No (for single-node); Yes for multi-replica |

---

## Detailed Gap Entries

### `GAP-01` (`P1` — Backend Security / Operational)
- **Description:** `upload_tender_pdf` (`backend/app/api/v1/tenders.py`) saves uploaded files using `f"tender_{file_uuid}_{file.filename}"` without stripping directory components (`os.path.basename`) and without enforcing `settings.MAX_UPLOAD_SIZE_MB`.
- **Affected Component:** `backend/app/api/v1/tenders.py` (`upload_tender_pdf`)
- **Evidence:** Inspected lines 62–68 of `backend/app/api/v1/tenders.py`.
- **Business & Technical Impact:** Unbounded file reads could exhaust memory on large uploads; unsanitized client filenames risk path-traversal edge cases on certain platforms.
- **Recommended Resolution:** Sanitize filename via `os.path.basename(file.filename)`, enforce `MAX_UPLOAD_SIZE_MB` during streaming read (`413 Payload Too Large`), and verify `%PDF-` magic header.
- **Blocks TenderLens:** **Yes** — should be closed at the start of Phase 2.0 before expanding tender ingestion.

### `GAP-02` (`P1` — Platform Infrastructure)
- **Description:** `POST /api/v1/tenders/{tender_id}/extract` executes 3-page sliding-window LLM extraction synchronously in the HTTP request lifecycle.
- **Affected Component:** `backend/app/api/v1/tenders.py` (`extract_tender_clauses`)
- **Evidence:** Inspected lines 116–140 of `backend/app/api/v1/tenders.py`.
- **Business & Technical Impact:** Large GeM NIT PDFs (50–200 pages) will hit HTTP gateway/browser timeouts before extraction completes.
- **Recommended Resolution:** Move extraction to an async background worker / FastAPI `BackgroundTasks` or queue with `GET /tenders/{id}/status` polling.
- **Blocks TenderLens:** **Yes** — required for reliable multi-document TenderLens ingestion.

### `GAP-03` (`P2` — Operational Deployment)
- **Description:** Invitation emails are not sent; administrators distribute `/invite/accept?token=...` out of band.
- **Affected Component:** `backend/app/services/auth_service.py`, `frontend/src/app/organization/page.tsx`
- **Recommended Resolution:** Integrate an approved transactional email provider (SMTP/SES/Resend) behind a feature flag.
- **Blocks TenderLens:** No.

### `GAP-04` (`P2` — Missing Business Functionality)
- **Description:** `BIDDER` users only have `tender:read` + `evaluation:read` without a bidder-isolated submission portal, and `SUPER_ADMIN` lacks a cross-tenant organization directory endpoint.
- **Affected Component:** `backend/app/api/v1/organizations.py`, `backend/app/api/v1/bidders.py`, `frontend/src/app/page.tsx`
- **Recommended Resolution:** Implement bidder-scoped endpoints and `SUPER_ADMIN` platform directory in dedicated future phases.
- **Blocks TenderLens:** No.

### `GAP-05` (`P2` — Frontend / API Security)
- **Description:** `getMockSourceExportUrl` in `frontend/src/lib/api-client.ts` is used as a direct `<a href>` link, which does not attach the in-memory Bearer token.
- **Affected Component:** `frontend/src/app/mock-data/page.tsx`, `frontend/src/lib/api-client.ts`
- **Recommended Resolution:** Replace `<a href>` with an authenticated `apiFetchResponse` Blob download handler.
- **Blocks TenderLens:** No.

### `GAP-06` (`P2` — Missing Business Functionality)
- **Description:** `audit:export` is defined in `SYSTEM_PERMISSIONS` (`rbac_service.py`) without an export endpoint.
- **Affected Component:** `backend/app/api/v1/audit.py`
- **Recommended Resolution:** Add `GET /api/v1/audit/logs/export` gated by `require_permission("audit:export")`.
- **Blocks TenderLens:** No.

### `GAP-07` (`P3` — Frontend E2E Testing)
- **Description:** No Playwright/Cypress browser runner is configured in `frontend/package.json`.
- **Affected Component:** `frontend/package.json`, `frontend/tests/`
- **Recommended Resolution:** Add Playwright E2E suite in a future UI-hardening pass.
- **Blocks TenderLens:** No.

### `GAP-08` (`P3` — Operational Storage)
- **Description:** Tender PDFs are stored on local disk (`UPLOAD_DIR`), which is non-shared across horizontal replicas.
- **Affected Component:** `backend/app/api/v1/tenders.py`, `backend/app/api/v1/bidders.py`
- **Recommended Resolution:** Abstract storage behind an S3/MinIO-compatible interface before multi-replica production scaling.
- **Blocks TenderLens:** No (single-node), Yes (multi-replica).
