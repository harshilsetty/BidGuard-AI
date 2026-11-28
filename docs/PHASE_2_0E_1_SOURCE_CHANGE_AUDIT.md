# Phase 2.0E.1 Source-Change & Decision-Semantics Audit

**Inspected Sources:** `backend/app/services/requirement_provenance_service.py`, `backend/app/services/requirement_conflict_service.py`, `backend/app/services/requirement_evidence_service.py`, `backend/app/services/tender_processing_worker.py`, `backend/app/services/review_service.py`.

---

## 1. Source Changes & Decision Invalidation

### What Works
- **Worker fencing & preservation:** `tender_processing_worker.py` uses `ownership_generation` fencing on all job state transitions and page/requirement persistence, and never writes `ReviewDecision` rows or overwrites `CONFIRMED`/`REJECTED` requirements during re-extraction (`TenderRequirement.review_status.in_(["DRAFT", "NEEDS_REVIEW"])` at line 551).
- **New `CONFIRM` blocked on `SOURCE_CHANGED`:** `TenderReviewService.submit_decision` (`review_service.py:118-122`) blocks `CONFIRM` with `409 Conflict` when `obj.provenance_status == "SOURCE_CHANGED"`.

### Finding P1-2: Source Changes Silently Preserve Previously Confirmed Decisions as Current
- In `TenderRequirementProvenanceService.verify_and_get_provenance` (`requirement_provenance_service.py:134-146`), when `recorded_sha256 != current_sha256`, `req.provenance_status` is updated to `"SOURCE_CHANGED"`, **but `req.review_status` is NOT transitioned from `CONFIRMED` (or `REJECTED`) back to `NEEDS_REVIEW`**.
- Consequently, a requirement that was `CONFIRMED` before its source document changed continues to report `review_status = "CONFIRMED"` as its current state unless a human manually clicks `REOPEN`.
- Additionally, `TenderRequirementConflictService.detect_conflicts` (`requirement_conflict_service.py:236`) and `TenderRequirementEvidenceService.generate_for_requirement` (`requirement_evidence_service.py:157`) unconditionally skip updating rows in `CONFIRMED`/`DISMISSED`/`RESOLVED`/`REJECTED` states even if underlying requirements or source documents changed, without flagging them for renewed review.
- Also, `tender_processing_worker.py:556` inserts `TenderRequirement` without populating `source_document_sha256` at extraction time (`source_document_sha256` is only backfilled on first `verify_and_get_provenance` call if missing).

---

## 2. Human Decision Semantics & Downstream Isolation
- `Select-String` across `backend/app/services/*.py` confirmed that `ReviewDecision` and Phase 2.0E review statuses (`TenderRequirement.review_status`, `TenderRequirementConflict.status`, `TenderRequirementEvidence.mapping_status`) are **not** consumed by compliance scoring, bidder eligibility, statutory verification, or tender recommendation engines.
- Confirmed requirements, conflicts, and evidence mappings cannot silently alter bidder eligibility, compliance scores, or autonomous procurement outcomes.
