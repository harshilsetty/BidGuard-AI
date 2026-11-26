# Tender Document Upload Security Specification (Phase 2.0A)

**Module:** `backend/app/services/tender_upload_service.py` & `backend/app/api/v1/tenders.py`  
**GAP Remediated:** `GAP-01`

---

## 1. Security Controls Implemented

1. **Authorization & Tenant Ownership:**
   - `POST /api/v1/tenders/upload` requires `tender:create`; `POST /api/v1/tenders/{tender_id}/documents` requires `tender:update` + `get_authorized_tender`.
   - `GET /api/v1/tenders/{tender_id}/documents*` requires `tender:read` + `get_authorized_tender`.
   - Organization identity is derived exclusively from `current_user.organization_id` / `tender.organization_id`.
2. **Filename Sanitization (`sanitize_pdf_filename`):**
   - Rejects empty/whitespace filenames, null bytes (`\x00`), POSIX/Windows path separators (`/` and `\`), `..` traversal segments, Windows drive prefixes (`C:`), names exceeding `255` characters, and non-`.pdf` extensions (`400 Bad Request`).
   - Original filename is stored strictly as display metadata (`original_filename`); never used in filesystem paths.
3. **Bounded Streaming & Size Enforcement (`stream_validate_and_store_pdf`):**
   - Reads uploads in `64 KB` (`65536` byte) chunks; never loads unbounded uploads into memory.
   - Tracks cumulative bytes and aborts immediately with `413 Payload Too Large` when exceeding `settings.MAX_UPLOAD_SIZE_MB` (`50 MB`).
4. **Content & Structural PDF Validation:**
   - Rejects `0`-byte files (`422`).
   - Verifies `%PDF-` magic header on the first chunk (`422`), independent of browser-supplied `Content-Type`.
   - Opens the written file with `pymupdf.open()`: rejects encrypted PDFs (`422`), corrupted/malformed structures (`422`), and `0`-page PDFs (`422`).
5. **Tenant-Partitioned Storage & Failure Cleanup:**
   - Storage path: `UPLOAD_DIR/{organization_id}/{tender_id}/{document_uuid}.pdf`, resolved and verified via `target_path.is_relative_to(upload_root)`.
   - `storage_path` is **never** returned in `TenderDocumentResponse`.
   - Partial or invalid files are unlinked immediately (`cleanup_stored_file`), including on DB persistence failures (`rollback` + `unlink`).
6. **SHA-256 Deduplication & PostgreSQL RLS:**
   - SHA-256 computed incrementally during streaming and enforced per tender via `uq_tender_documents_tender_sha256` (`409 Conflict`).
   - `tender_documents` has `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` (`0007_tender_documents.py`) scoped through `tenders.organization_id`.

## 2. Remaining Risks

- **Active Malware Scanning:** Structural PDF parsing via PyMuPDF does not replace an antivirus/CDR engine (e.g., ClamAV) for embedded JavaScript/active exploits if PDFs are later rendered or downloaded by end-users.
- **Local Filesystem Storage:** `UPLOAD_DIR` is single-node local storage; multi-replica deployments require object storage (S3/MinIO) in a future phase.
