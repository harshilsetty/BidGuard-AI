# TenderLens — Product Requirements Specification (Phase 2.0)

**Product:** BidGuard — *Intelligence behind every bid.*  
**Module:** TenderLens (Tender Intelligence & Bid Readiness)  
**Target Users:** `PROCUREMENT_OFFICER`, `ORG_ADMIN`, `AUDITOR` (read-only), `BIDDER` (read-only on permitted tenders)

---

## 1. Product Mission & Scope

TenderLens transforms raw GeM tender notices (NITs), technical specifications, BoQs, and corrigenda into a **verified, source-grounded tender intelligence profile** and an **actionable bid-readiness checklist** before bidder compliance evaluation begins.

**Core Principles:**
1. Every extracted requirement links to an exact source document, page (or page range), and verbatim quote.
2. AI assists extraction and classification; human procurement officers review, edit, confirm, or reject requirements.
3. No fabricated readiness percentages, invented page numbers, or silent auto-approvals.
4. Original SIH Golden Demo (`GEM/2026/B/8912450`) remains independently runnable and regression-protected.

---

## 2. End-to-End TenderLens User Journey

1. Officer creates a tender workspace (`POST /api/v1/tenders`).
2. Officer uploads one or more tender PDFs (primary NIT, technical annexure, BoQ, corrigendum).
3. Platform validates file safety (size, extension, `%PDF-` signature, sanitized name) and enqueues asynchronous processing.
4. Background worker runs digital/OCR page extraction, stores page-level text & provenance, and executes structured requirement extraction.
5. Requirements are classified by taxonomy and obligation (`MANDATORY`, `OPTIONAL`, `UNCLEAR`), with expected evidence types attached.
6. Conflicts/supersessions across corrigenda and ambiguous requirements are flagged explicitly.
7. Officer reviews extracted requirements side-by-side against source page text, edits/confirms/rejects items, and resolves ambiguities.
8. Platform computes transparent **Bid Readiness** metrics (without conflating extraction completeness, review progress, evidence expectations, and bidder compliance).
9. Confirmed tender profile feeds downstream bidder compliance evaluation.

---

## 3. Requirement Taxonomy (Non-Collapsing Classification)

TenderLens MUST distinguish rather than collapse extracted text into generic clauses:

| Category | Code Prefix | Examples |
|---|---|---|
| Mandatory Eligibility Criteria | `ELIG` | Minimum years in business, OEM authorization, GeM seller category |
| Technical Requirements | `TECH` | Hardware/software specs, throughput, ISO/BIS certifications, warranty |
| Financial Requirements | `FIN` | Annual turnover, net worth, EMD, PBG |
| Statutory Requirements | `STAT` | Make-in-India local content %, GSTIN, PAN, EPFO/ESIC, non-debarment |
| Experience / Past Performance | `EXP` | Similar completed projects count, minimum order value |
| Documentary Requirements | `DOC` | Signed undertaking, audited balance sheets, notarized affidavits |
| Delivery / SLA | `DEL` | Delivery lead time, uptime SLA, liquidated damages |
| Submission Instructions | `SUB` | Two-packet bid format, BoQ upload rules, fee exemption steps |
| Deadlines & Milestones | `DATE` | Bid submission end date, pre-bid meeting, technical opening date |
| Optional Preferences | `PREF` | Desirable features, MSE/Startup relaxation notes (`OPTIONAL`) |

---

## 4. Requirement Provenance & Lifecycle

Every extracted requirement record MUST preserve:
- `requirement_id` (immutable human-readable code, e.g. `TECH-01`)
- `original_source_text` (verbatim quote; if unverified, marked `PROVENANCE_UNAVAILABLE` and `NEEDS_REVIEW`)
- `normalized_interpretation` (concise plain-English obligation summary)
- `source_document_id`, `page_number` (and optional `page_end`), `section_heading`
- `category` (from Section 3 taxonomy)
- `obligation` (`MANDATORY` | `OPTIONAL` | `UNCLEAR`)
- `extraction_confidence` (`0.000`–`1.000`) + `extraction_method` (`DIGITAL_TEXT` | `OCR_PROCESSED` | `OCR_LOW_CONFIDENCE`)
- `verification_status` (`DRAFT` | `CONFIRMED` | `REJECTED` | `NEEDS_REVIEW` | `SUPERSEDED`)
- `review_history` (actor, timestamp, previous/new values, justification)

---

## 5. Evidence Expectation & Bid Readiness Model

### 5.1 Evidence States
Each requirement maps to expected evidence items with explicit states:
`EXPECTED` -> `UPLOADED` -> `EXTRACTED` -> `VERIFIED` | `MISSING` | `CONTRADICTORY` | `AWAITING_REVIEW`.

### 5.2 Transparent Readiness Metrics (4 Separate Measurements)
1. **Extraction Completeness:** `processed_pages / total_pages` (and count of `OCR_LOW_CONFIDENCE` / `OCR_FAILED` pages).
2. **Requirement Review Progress:** `confirmed_or_rejected_requirements / total_extracted_requirements` (highlighting `UNCLEAR` and `NEEDS_REVIEW` counts).
3. **Document & Evidence Checklist Coverage:** `requirements_with_mapped_expected_evidence / mandatory_requirements`.
4. **Conflict & Milestone Status:** Count of unresolved corrigendum conflicts and upcoming deadlines (`DATE` items).

These 4 measurements MUST NOT be averaged into an opaque single percentage. Actual bidder compliance remains downstream in the Compliance Matrix.
