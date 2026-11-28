# Source Version and Review Invalidation Design

## 1. Source-Version Identity
- **Requirement Extraction (`tender_processing_worker.py`):** Captures `doc.sha256_hash` (verified against the on-disk file when available) at the start of `REQUIREMENT_EXTRACTION`, re-verifies before finalizing, and persists `source_document_sha256` on every extracted `TenderRequirement`. If the file or DB hash changes mid-extraction, the worker aborts publication (`SOURCE_CHANGED_DURING_EXTRACTION`) without overwriting current state.
- **Provenance Verification (`requirement_provenance_service.py`):** Compares `req.source_document_sha256` against `doc.sha256_hash`. On mismatch, sets `provenance_status = "SOURCE_CHANGED"` and invokes `TenderReviewService.invalidate_for_source_change`.

## 2. Invalidation Semantics
- **Historical decisions preserved:** Existing `ReviewDecision` rows are never modified or deleted (`trg_review_decisions_immutable`).
- **Requirements:** If `review_status in ("CONFIRMED", "REJECTED", "NEEDS_CLARIFICATION")`, transitions atomically to `NEEDS_REVIEW`, increments `review_version` (`WHERE review_version == current_version`), and records a `SOURCE_INVALIDATED` `ReviewDecision` (`reviewer_user_id=None`, `source_document_sha256=current_sha256`) + `AuditLog` (`REVIEW_SOURCE_INVALIDATED`).
- **Conflicts & Evidence:** Any dependent `TenderRequirementConflict` (`CONFIRMED`, `DISMISSED`, `RESOLVED`) or `TenderRequirementEvidence` (`CONFIRMED`, `REJECTED`) linked to an invalidated requirement is atomically transitioned to `NEEDS_REVIEW` with `review_version += 1` and a `SOURCE_INVALIDATED` history entry.
- **Idempotency:** Objects already in `NEEDS_REVIEW` or `DRAFT`/`DETECTED`/`SUGGESTED` are not re-invalidated, preventing duplicate `SOURCE_INVALIDATED` history entries.
- **Conflict & Evidence Regeneration:** `detect_conflicts` and `generate_for_requirement` preserve human decisions **only** when underlying requirements are not `SOURCE_CHANGED` / `NEEDS_REVIEW` (and for evidence, when `source_passage` matches `req.source_text`).
