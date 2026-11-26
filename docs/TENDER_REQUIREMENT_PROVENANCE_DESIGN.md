# TenderLens Requirement Provenance Design (Phase 2.0D)

## 1. Provenance Verification Outcomes

`TenderRequirementProvenanceService` verifies `TenderRequirement.source_text` against persisted `TenderDocumentPage` rows without altering the original `source_text`:

- `VERIFIED`: Exact contiguous token sequence found on `source_page_number` (or matched page in the same `source_document_id`).
- `PARTIALLY_VERIFIED`: Matches after OCR/hyphenation/whitespace normalization (e.g., line-break hyphen splits, minor OCR punctuation noise, or >= 80% contiguous token containment) — flags `needs_review` if page differs.
- `SOURCE_CHANGED`: `TenderRequirement.source_document_sha256` was recorded and no longer matches `TenderDocument.sha256_hash`.
- `SOURCE_NOT_FOUND`: `source_page_number` does not exist or no `TenderDocumentPage` records exist for `source_document_id`.
- `UNVERIFIED` / `NEEDS_REVIEW`: Quote cannot be grounded on any persisted page of `source_document_id`.

---

## 2. Multiple Supporting Sources (`tender_requirement_sources`)

`TenderRequirementSource` links a requirement to one or more document passages without overwriting the primary source:
- `source_role`: `PRIMARY_SUPPORTING`, `ADDITIONAL_SUPPORTING`, `CONTEXTUAL`, `POTENTIALLY_CONTRADICTORY`
- `source_document_id`, `source_page_number`, `source_section`, `source_text`, `verification_status`, `source_document_sha256`.
