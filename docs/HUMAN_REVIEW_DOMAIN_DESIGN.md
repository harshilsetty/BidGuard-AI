# Human Review Domain Design (Phase 2.0E)

## 1. Separation of Facts

BidGuard preserves five distinct layers without collapsing them into a single PASS/FAIL flag:
1. **Extracted Intelligence** (`TenderRequirement.normalized_statement`, `primary_category`, `mandatory_status`).
2. **Source Provenance** (`TenderRequirement.provenance_status`: `VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`, `SOURCE_NOT_FOUND`, `SOURCE_CHANGED`).
3. **Conflict Detection** (`TenderRequirementConflict.conflict_type`, `relationship_type`, `severity`, `status`).
4. **Expected Bidder Evidence** (`TenderRequirementEvidence.evidence_type`, `mapping_status` — never confused with uploaded/verified bidder documents).
5. **Human Review Decisions** (`review_status` / `status` / `mapping_status` + `ReviewDecision` append-only history).

---

## 2. Review Outcomes & Semantics

- **Requirements (`REQUIREMENT`):**
  - `CONFIRMED`: Reviewer accepts the extracted requirement as a faithful representation of the tender source (does *not* mean a bidder is eligible).
  - `REJECTED`: Reviewer rejects the extracted requirement as invalid/non-applicable (retains original extracted text & history).
  - `NEEDS_CLARIFICATION`: Reviewer flags the requirement as requiring buyer/tender clarification.
- **Conflicts (`CONFLICT`):**
  - `CONFIRMED`: Reviewer confirms the two requirements genuinely conflict (does *not* establish legal precedence).
  - `DISMISSED`: Reviewer dismisses a false-positive conflict.
  - `RESOLVED`: Reviewer records a manual resolution note without silently rewriting either original requirement.
- **Evidence Mappings (`EVIDENCE`):**
  - `CONFIRMED`: Reviewer confirms the expected evidence type is required/appropriate (does *not* mean a bidder has submitted authentic evidence).
  - `REJECTED`: Reviewer rejects an unsupported or unnecessary evidence mapping.

---

## 3. Rationale Validation

- **Mandatory Rationale (`min_length >= 5` non-whitespace chars, `max_length <= 2000`):** Required for `REJECT`, `REQUEST_CLARIFICATION`, `DISMISS`, `RESOLVE`, and `REOPEN`.
- **Optional/Concise Rationale:** Allowed for `CONFIRM` and `ASSIGN` (trimmed; if provided, recorded verbatim; if omitted, defaults to concise system label or optional note).
- Whitespace-only strings are rejected (`422 Unprocessable Entity`) whenever a rationale is required.
