# Phase 2.0D Evaluation: Provenance, Conflict Detection & Evidence Mapping

**Repository:** `harshilsetty/BidGuard-AI`  
**Evaluation Date:** 2026-11-27  
**Mode:** Deterministic evaluation on synthetic labeled test cases (`test_phase2_0d_provenance_conflicts_evidence.py`). Real-world multi-tender LLM evaluation remains deferred until an active NIM chat endpoint replaces the `410 Gone` `openai/gpt-oss-20b` model.

---

## 1. Provenance Verification Evaluation (Synthetic Tiered Fixtures)

| Test Case | Expected Status | Observed Status | Result |
|---|---|---|---|
| Exact verbatim quotation on attributed page (`p.2`) | `VERIFIED` | `VERIFIED` | Pass |
| Hyphenated line-break split (`compre-\nhensive`) | `PARTIALLY_VERIFIED` | `PARTIALLY_VERIFIED` | Pass |
| Verbatim quote attributed to wrong page (`p.1` instead of `p.2`) | `PARTIALLY_VERIFIED` (`matched_page=2`) | `PARTIALLY_VERIFIED` (`matched_page=2`) | Pass |
| Non-existent page (`p.5`) | `SOURCE_NOT_FOUND` | `SOURCE_NOT_FOUND` | Pass |
| Fabricated/ungrounded quotation | `UNVERIFIED` | `UNVERIFIED` | Pass |
| Document SHA-256 mismatch (`recorded != current`) | `SOURCE_CHANGED` | `SOURCE_CHANGED` | Pass |

- **Synthetic Provenance Accuracy:** `6/6` (`100%`) on controlled test cases.

---

## 2. Scope-Aware Conflict Detection Evaluation (Synthetic Fixtures)

| Pair Tested | Expected Outcome | Observed Outcome |
|---|---|---|
| `FIN-01` (NIT `INR 500 Lakhs`) vs `FIN-02` (Corrigendum `INR 8 Crore`) | `FINANCIAL_MISMATCH`, `POTENTIAL_AMENDMENT`, `NEEDS_REVIEW` | `FINANCIAL_MISMATCH`, `POTENTIAL_AMENDMENT`, `NEEDS_REVIEW` |
| `DEL-01` (`Lot 1`, `30 days`) vs `DEL-02` (`Lot 2`, `60 days`) | **No conflict** (disjoint scope `lot 1` vs `lot 2`) | `0` conflicts raised (false positive avoided) |

- **Synthetic Conflict Precision / Recall:** `1/1` (`100%` precision, `100%` recall, `0` false positives on disjoint-scope pair) on the synthetic fixture set.
- **Limitation:** Synthetic pairs do not establish real-world recall on complex, un-normalized multi-document tenders.

---

## 3. Evidence Mapping Evaluation (Synthetic Fixtures)

| Requirement | Expected Evidence Output | Observed Output |
|---|---|---|
| `FIN-01` (`INR 500 Lakhs with audited balance sheets`) | `AUDITED_FINANCIAL_STATEMENTS` + `TURNOVER_CERTIFICATE`, status `SUGGESTED` | `AUDITED_FINANCIAL_STATEMENTS`, `TURNOVER_CERTIFICATE` (`SUGGESTED`) |
| `TECH-01` (ungrounded quote, no evidence cues) | `0` fabricated mappings | `0` mappings (`total == 0`) |
