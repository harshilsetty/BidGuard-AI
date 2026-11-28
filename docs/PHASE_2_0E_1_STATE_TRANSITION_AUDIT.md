# Phase 2.0E.1 State-Transition Audit

**Inspected Source:** `backend/app/services/review_service.py` (`ALLOWED_TRANSITIONS`, `submit_decision`), `backend/app/schemas/tender.py` (`ReviewDecisionRequest`), `frontend/src/components/TenderReviewWorkspace.tsx`.

---

## 1. Tender Requirements (`REQUIREMENT` -> `TenderRequirement.review_status`)

| Decision | Accepted Previous States | New State | Permission | Rationale Mandatory? | Increments `review_version`? | Writes `ReviewDecision`? | Repeated Request |
|---|---|---|---|---|---|---|---|
| `CONFIRM` | `DRAFT`, `NEEDS_REVIEW`, `NEEDS_CLARIFICATION` | `CONFIRMED` | `evaluation:override` | No (default generated if empty) | Yes (`+1`) | Yes | Rejected (`409`) |
| `REJECT` | `DRAFT`, `NEEDS_REVIEW`, `NEEDS_CLARIFICATION` | `REJECTED` | `evaluation:override` | Yes (`>= 5` chars, `422`) | Yes (`+1`) | Yes | Rejected (`409`) |
| `REQUEST_CLARIFICATION` | `DRAFT`, `NEEDS_REVIEW`, `CONFIRMED` | `NEEDS_CLARIFICATION` | `evaluation:override` | Yes (`>= 5` chars, `422`) | Yes (`+1`) | Yes | Rejected (`409`) |
| `REOPEN` | `CONFIRMED`, `REJECTED`, `NEEDS_CLARIFICATION` | `NEEDS_REVIEW` | `evaluation:override` | Yes (`>= 5` chars, `422`) | Yes (`+1`) | Yes | Rejected (`409`) |

**Additional Guard:** `CONFIRM` is rejected (`409 Conflict`) if `obj.provenance_status == "SOURCE_CHANGED"`.

---

## 2. Conflicts (`CONFLICT` -> `TenderRequirementConflict.status`)

| Decision | Accepted Previous States | New State | Permission | Rationale Mandatory? | Increments `review_version`? | Writes `ReviewDecision`? | Repeated Request |
|---|---|---|---|---|---|---|---|
| `CONFIRM` | `DETECTED`, `NEEDS_REVIEW` | `CONFIRMED` | `evaluation:override` | No | Yes (`+1`) | Yes | Rejected (`409`) |
| `DISMISS` | `DETECTED`, `NEEDS_REVIEW`, `CONFIRMED` | `DISMISSED` | `evaluation:override` | Yes (`>= 5` chars) | Yes (`+1`) | Yes | Rejected (`409`) |
| `RESOLVE` | `DETECTED`, `NEEDS_REVIEW`, `CONFIRMED` | `RESOLVED` | `evaluation:override` | Yes (`>= 5` chars) | Yes (`+1`) | Yes | Rejected (`409`) |
| `REOPEN` | `CONFIRMED`, `DISMISSED`, `RESOLVED` | `NEEDS_REVIEW` | `evaluation:override` | Yes (`>= 5` chars) | Yes (`+1`) | Yes | Rejected (`409`) |

---

## 3. Expected Evidence Mappings (`EVIDENCE` -> `TenderRequirementEvidence.mapping_status`)

| Decision | Accepted Previous States | New State | Permission | Rationale Mandatory? | Increments `review_version`? | Writes `ReviewDecision`? | Repeated Request |
|---|---|---|---|---|---|---|---|
| `CONFIRM` | `SUGGESTED`, `NEEDS_REVIEW` | `CONFIRMED` | `evaluation:override` | No | Yes (`+1`) | Yes | Rejected (`409`) |
| `REJECT` | `SUGGESTED`, `NEEDS_REVIEW` | `REJECTED` | `evaluation:override` | Yes (`>= 5` chars) | Yes (`+1`) | Yes | Rejected (`409`) |
| `REOPEN` | `CONFIRMED`, `REJECTED` | `NEEDS_REVIEW` | `evaluation:override` | Yes (`>= 5` chars) | Yes (`+1`) | Yes | Rejected (`409`) |

---

## 4. Assessment
- All state transitions are server-enforced in `ALLOWED_TRANSITIONS` in `review_service.py` and schema-validated in `ReviewDecisionRequest`.
- No transition relies solely on frontend button visibility.
- Repeated identical requests are **not** silently idempotent; they are rejected with `409 Conflict` (both because `review_version` incremented and because the target status is no longer in `allowed_from`).
