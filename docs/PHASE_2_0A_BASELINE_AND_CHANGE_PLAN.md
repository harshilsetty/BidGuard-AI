# PHASE 2.0A: BASELINE & CHANGE PLAN

**Repository:** `harshilsetty/BidGuard-AI`  
**Branch:** `main`  
**Base Commit SHA:** `96b040bf03bba17fe7400c95b57e3907bdd0cd82`  
**Alembic Chain:** `0001_initial_baseline` -> `0002_enterprise_foundation` -> `0003_security_and_integrity` -> `0004_comprehensive_rls` -> `0005_audit_immutability` -> `0006_invitation_revocation`

---

## 1. Audited Baseline State

- **`backend/app/api/v1/tenders.py` (`upload_tender_pdf`):**
  - Only checks `file.filename.lower().endswith(".pdf")`.
  - Uses `f"tender_{file_uuid}_{file.filename}"` directly in `os.path.join(upload_dir, saved_filename)`.
  - Calls `await file.read()` unbounded into memory without checking `settings.MAX_UPLOAD_SIZE_MB` (`50`).
  - Does not verify `%PDF-` magic bytes or compute `sha256_hash`.
- **`backend/app/models/tender.py`:**
  - `Tender` stores single-PDF `file_name` and `file_path` columns (nullable `organization_id` preserved for Golden Demo `GEM/2026/B/8912450`).
  - No `tender_documents` child table exists yet.
- **`backend/app/core/config.py`:**
  - `UPLOAD_DIR: str = "uploads"`, `MAX_UPLOAD_SIZE_MB: int = 50`.

## 2. Planned Phase 2.0A Changes

1. **Data Model & Migration:** Add `TenderDocument` ORM model (`backend/app/models/tender.py`) and forward migration `0007_tender_documents.py` with `uq_tender_documents_tender_sha256` and PostgreSQL `FORCE ROW LEVEL SECURITY`.
2. **Secure Upload Service (`backend/app/services/tender_upload_service.py`):** Streaming chunk reader enforcing `MAX_UPLOAD_SIZE_MB` (`413`), strict filename sanitization, `%PDF-` magic + PyMuPDF structural validation (`422`), SHA-256 hashing, tenant-partitioned storage (`UPLOAD_DIR/{organization_id}/{tender_id}/{document_uuid}.pdf`), and guaranteed file cleanup on failure.
3. **Backend APIs (`backend/app/api/v1/tenders.py` + `schemas/tender.py`):**
   - Harden `POST /api/v1/tenders/upload` (legacy single-PDF flow + initial `PRIMARY_NIT` `TenderDocument` record).
   - Add `POST /api/v1/tenders/{tender_id}/documents` (`201`/`400`/`401`/`403`/`404`/`409`/`413`/`422`).
   - Add `GET /api/v1/tenders/{tender_id}/documents` and `GET /api/v1/tenders/{tender_id}/documents/{document_id}` (never exposing `storage_path`).
4. **Frontend Integration:** Add `TenderDocument` types, API client methods, and a permission-gated `TenderDocumentsPanel` inside `/tenders/[id]/clauses`.
5. **Testing:** 20+ backend security/RLS tests + frontend upload/RBAC tests + full regression + Golden Demo verification.
