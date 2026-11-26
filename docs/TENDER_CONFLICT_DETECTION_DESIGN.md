# TenderLens Cross-Document Conflict Detection Design (Phase 2.0D)

## 1. Controlled Conflict Taxonomy

`NUMERIC_MISMATCH`, `DATE_MISMATCH`, `TECHNICAL_MISMATCH`, `ELIGIBILITY_MISMATCH`, `FINANCIAL_MISMATCH`, `DOCUMENT_MISMATCH`, `DELIVERY_MISMATCH`, `SCOPE_MISMATCH`, `OTHER`.

- **Severity:** `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- **Status:** `DETECTED`, `NEEDS_REVIEW`, `CONFIRMED`, `DISMISSED`, `RESOLVED` (automated detection only ever sets `DETECTED` or `NEEDS_REVIEW`).
- **Relationship Type:** `CONFLICT` vs `POTENTIAL_AMENDMENT` (when one document is a `CORRIGENDUM` or contains explicit amendment phrasing such as *"amended"*, *"revised"*, *"read as"*, *"extended"*, *"substituted"*).

---

## 2. Candidate Partitioning & Scope-Aware Rules

1. **Candidate Partitioning:** Requirements are grouped by `(primary_category, requirement_type)` (plus cross-document pairs) to avoid unbounded $O(N^2)$ comparisons on large tenders.
2. **Unit & Currency Normalization:** Normalizes `Lakh`/`Lakhs` (`* 1e5`), `Crore`/`Crores` (`* 1e7`), `K` (`* 1e3`), `days`/`weeks` (`* 7`)/`months` (`* 30`)/`years` (`* 365`), `GB`/`TB` (`* 1024`).
3. **Scope-Aware Filtering:** Extracts explicit scope markers (e.g., `Lot 1` vs `Lot 2`, `MSE` vs `General`/`Non-MSE`, `Class-I` vs `Class-II`, distinct locations/sites). If two requirements have explicitly disjoint scopes, they are **not** flagged as a contradiction.
4. **Corrigendum Safety:** Potential amendments record both sides (`requirement_a_id`, `requirement_b_id`) with `relationship_type = 'POTENTIAL_AMENDMENT'` and `status = 'NEEDS_REVIEW'`, preserving both the original requirement and the newer passage intact.
