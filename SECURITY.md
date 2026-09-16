# Security Policy — BidGuard

Security and data integrity are fundamental to the **BidGuard** AI procurement verification platform. This document outlines our security practices, file handling constraints, and vulnerability disclosure process.

---

## 1. Security Architecture & Best Practices

### A. Strict Secrets Hygiene
- **Never commit secrets, API keys, credentials, or production tokens** to version control.
- All secrets and runtime parameters must be injected via `.env` or system environment variables.
- Repository `.gitignore` explicitly filters `.env`, `*.pem`, `*.key`, `*.sqlite`, and credentials.
- Automated secret scanners (e.g. GitGuardian or GitHub Secret Scanning) should be enabled on all branches.

### B. Document & File Upload Security
Government tenders and bidder submissions contain sensitive commercial and technical data:
- **File Type Restrictions**: Only sanitized, valid document types are permitted (`application/pdf`, `image/jpeg`, `image/png`). Executable files (`.exe`, `.sh`, `.bat`, `.js`) or macro-enabled archives are strictly rejected.
- **File Size Limits**: Hard upload limits are enforced on both the client (Next.js) and server (FastAPI) layers (maximum 25 MB per document).
- **MIME Type Validation**: Files are validated using binary magic bytes inspection rather than relying solely on user-supplied file extensions.
- **Malicious Payload Mitigation**: Uploaded PDFs are parsed in memory or in isolated temporary storage, preventing arbitrary code execution.

### C. Input Sanitization & Data Safety
- All REST endpoint payloads are strictly validated using typed Pydantic v2 schemas.
- Path traversal protections: Document storage uses random UUIDs rather than raw user-supplied file names on disk.
- SQL injection prevention: All database operations use async SQLAlchemy ORM parameterized queries.

### D. Privacy & Sensitive Content Logging
- **Do not log raw document contents or Personally Identifiable Information (PII)** into server logs.
- Sensitive numbers (PAN, GSTIN, Aadhaar, bank details) are masked in application logs and trace telemetry.

### E. Authentication-Ready Architecture
- Backend routes are structured with modular FastAPI dependency injection (`Depends(get_current_user)` stubs), ready to integrate OAuth2 / JWT / OpenID Connect when deploying to production environments.

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability in BidGuard:
1. **Do not create a public GitHub issue.**
2. Report the vulnerability privately to the project lead (Harshil Somisetty) or cloud lead (Karthik).
3. Include:
   - Type of issue (e.g., buffer overflow, path traversal, injection).
   - Step-by-step instructions to reproduce.
   - Proof-of-concept script or payload if applicable.
4. The team will acknowledge receipt within 48 hours and work on a coordinated fix.
