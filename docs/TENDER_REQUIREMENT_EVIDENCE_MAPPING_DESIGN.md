# TenderLens Requirement Evidence Mapping Design (Phase 2.0D)

## 1. Evidence Model (`tender_requirement_evidence`)

Links each `TenderRequirement` to expected bidder evidence records:
- `evidence_type`: Controlled vocabulary (`COMPANY_REGISTRATION`, `GST_CERTIFICATE`, `PAN`, `AUDITED_FINANCIAL_STATEMENTS`, `TURNOVER_CERTIFICATE`, `WORK_ORDER`, `COMPLETION_CERTIFICATE`, `EXPERIENCE_CERTIFICATE`, `ISO_CERTIFICATE`, `BIS_CERTIFICATE`, `MSME_OR_UDYAM_CERTIFICATE`, `EMD_PROOF`, `BANK_GUARANTEE`, `TECHNICAL_DATASHEET`, `OEM_AUTHORIZATION`, `SELF_DECLARATION`, `UNDERTAKING`, `OTHER`).
- `expected_document_name`, `evidence_purpose`, `is_mandatory` (derived from requirement's `mandatory_status`), `source_passage` (exact supporting text from `source_text`), `mapping_method` (`DETERMINISTIC_RULE`), `confidence`, `mapping_status` (`SUGGESTED` or `NEEDS_REVIEW` — never `CONFIRMED`).

---

## 2. Grounding & Safety Rules

- Evidence types are suggested **only** when explicit lexical/semantic cues exist in `source_text` or `expected_document_or_evidence` (e.g., `"audited balance sheet"` -> `AUDITED_FINANCIAL_STATEMENTS`, `"ISO 9001"` -> `ISO_CERTIFICATE`, `"Udyam"`/`"MSME"` -> `MSME_OR_UDYAM_CERTIFICATE`, `"MAF"`/`"Manufacturer Authorization"` -> `OEM_AUTHORIZATION`).
- If `source_text` is missing or unverified, any mapping is capped in confidence and marked `NEEDS_REVIEW` (or skipped if no grounded evidence cue exists).
- Re-generation preserves existing `CONFIRMED` or `REJECTED` human-reviewed mappings.
