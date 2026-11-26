# TenderLens Module Readiness Assessment (Pre-Phase 2.0)

**Assessment Phase:** Phase 1.4  
**Scope:** Readiness of the BidGuard Enterprise Platform (`Phase 1.0–1.4`) to support **TenderLens** (Tender Analysis & Bid Readiness Intelligence).

---

## 1. Requirement-by-Requirement Readiness Classification

| Capability Area | Classification | Evidence & Current State | Minimum Work Required for Phase 2.0 |
|---|---|---|---|
| **Organization-Scoped Tender Ownership** | **Ready** | `tenders.organization_id` foreign key + PostgreSQL `FORCE ROW LEVEL SECURITY` (`0003`/`0004`) + `get_authorized_tender` in `deps.py` | None |
| **RBAC & Permission Enforcement** | **Ready** | `tender:create`, `tender:read`, `tender:update`, `tender:delete` enforced via `require_permission(...)` | None |
| **Authentication & Session Context** | **Ready** | In-memory JWT + rotating HttpOnly refresh cookie + single-flight refresh + `AuthGate` | None |
| **Tender Metadata & Clause Schema** | **Ready** | `tenders` and `tender_clauses` (`clause_code`, `category`, `is_mandatory`, `rule_config`, `source_text`, `page_number`, `is_confirmed`) | None |
| **Evidence Provenance & Vector Storage** | **Ready** | PostgreSQL 16 + `pgvector` 0.8.6 (`Vector(2048)` on `document_chunks`) + `Nemotron` embeddings | None |
| **Compliance Evaluation & Scoring** | **Ready** | Deterministic rule engine + Golden Demo regression (`100.00 / 53.41 / 47.95` standalone, `90.45 / 40.45 / 34.77` fused) | None |
| **Auditability** | **Ready** | Append-only `audit_logs` enforced by PostgreSQL `trg_audit_logs_immutable` trigger + `/audit` viewer | Add audit events on tender upload/extraction mutations |
| **Tender Upload & File Validation** | **Ready with limitations** | `POST /api/v1/tenders/upload` checks `.pdf` extension, writes to `UPLOAD_DIR`, parses via PyMuPDF | Enforce `MAX_UPLOAD_SIZE_MB` + `os.path.basename` sanitization + `%PDF-` magic check (`GAP-01`) |
| **Long-Running Processing & Retries** | **Not ready** | `POST /api/v1/tenders/{id}/extract` runs LLM sliding-window extraction synchronously in the HTTP request | Move extraction to background task/worker with status polling & retry state (`GAP-02`) |
| **Frontend Integration Boundaries** | **Ready with limitations** | `/tenders/new`, `/tenders/[id]/clauses`, `/tenders/[id]/bidders`, `/tenders/[id]/compliance` all routed through `apiFetch` & `AuthGate` | Add `403` / `hasPermission` action-button gating inside existing tender detail pages |

---

## 2. Architectural Decisions & Minimum Pre-Phase 2.0 Checklist

1. **Close `GAP-01` (Upload Hardening):** Sanitize `file.filename` and enforce `MAX_UPLOAD_SIZE_MB` in `upload_tender_pdf`.
2. **Close `GAP-02` (Async Extraction):** Decouple `extract_tender_clauses` from synchronous HTTP request timeouts so multi-page NITs process reliably without gateway `504` errors.
3. **Preserve Golden Demo Invariants:** Keep `GEM/2026/B/8912450` scoring and clause outputs isolated from any new TenderLens readiness scoring or gap-analysis features.

**Overall Readiness Verdict:** **READY WITH LIMITATIONS** — Platform auth, RBAC, PostgreSQL RLS, pgvector provenance, and auditability are solid; address `GAP-01` and `GAP-02` as the first engineering tasks of Phase 2.0.
