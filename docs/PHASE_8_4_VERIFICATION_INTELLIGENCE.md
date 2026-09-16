# Phase 8.4: Verification Intelligence & Officer Risk View

## 1. Overview & Architecture

Phase 8.4 elevates the statutory verification and compliance checking foundation into an **Officer-Facing Verification Intelligence & Decision Support Layer**.

The primary purpose of this layer is to answer the officer's core questions:
> *"What did we verify, as of when, from which source, what conflicts exist, what failed technically, and what requires officer review?"*

### Authoritative Architecture Flow

```
┌─────────────────────────┐
│     Bidder Dossier      │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│              Authoritative Fact Engines                 │
│  - Statutory Adapters (GSTN, Udyam, MCA, etc.)          │
│  - Cross-Source Verifier (Multi-Registry Discrepancies)  │
│  - Debarment Temporal Service (Inclusive Date Intervals) │
│  - Compliance Engine (Clause Compliance PASS/FAIL/REV)  │
│  - Scoring Service (Phase 6.4 100-Point Score Formula)   │
│  - OCR Pipeline (Digital Text & Scanned Image Quality)   │
└───────────┬─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│        Verification Intelligence Service (READ-ONLY)    │
│  - Consolidates 11 Statutory Sources                    │
│  - Distinguishes Technical vs Business Status           │
│  - Preserves Append-Only Execution History              │
│  - Builds Structured, Traceable Risk Reasons            │
│  - Populates Deterministic Human Review Queue           │
└───────────┬─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│                 Procurement Officer UI                  │
│  - Overall Risk State (LOW / MEDIUM / HIGH)             │
│  - 100-Point Score Breakdown (Protected)                │
│  - 11-Source Status Grid with Error Transparency        │
│  - Actionable Human Review Queue                        │
│  - Append-Only Verification History Drawer              │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Locked 11-Source Statutory Registry

The verification intelligence system monitors **exactly 11 statutory sources**:

1. **GSTN** — Goods & Services Tax Network
2. **Udyam** — Udyam MSME Registration Portal
3. **MCA** — Ministry of Corporate Affairs
4. **Income Tax** — Central Board of Direct Taxes (CBDT)
5. **MII** — Make in India (DPIIT Local Content)
6. **Debarment** — CPPP Central Debarment Register
7. **DPIIT** — DPIIT / Startup India Recognition
8. **EPFO** — Employees' Provident Fund Organisation
9. **ESIC** — Employees' State Insurance Corporation
10. **NSIC** — National Small Industries Corporation (SPRS)
11. **DigiLocker** — DigiLocker Document Verification & Provenance

*Note: State Debarment is not registered as a separate 12th source; central and state debarment authorities are integrated within the authoritative debarment verification pipeline.*

---

## 3. Status Semantics: Technical vs Business Failure

Technical failures are strictly separated from business verification outcomes to protect bidders from administrative injustice:

$$\text{SOURCE\_UNAVAILABLE} \neq \text{Bidder Non-Compliance}$$
$$\text{TIMEOUT} \neq \text{Bidder Non-Compliance}$$
$$\text{AUTH\_FAILURE} \neq \text{Bidder Non-Compliance}$$

### Status Classifications

| Classification | Status Values | Procurement Meaning | Impact on Bidder Score |
| :--- | :--- | :--- | :--- |
| **Business Verified** | `VERIFIED` | Authority connection succeeded and facts confirmed. | Full compliance credit. |
| **Business Not Found**| `NOT_FOUND` | Authority connection succeeded, but entity is absent. | Evaluated per tender clause rules. |
| **Business Inactive** | `INACTIVE`, `EXPIRED` | Authority confirmed entity is expired or inactive. | Discrepancy / Review flagged. |
| **Technical Failure** | `TIMEOUT`, `UNAVAILABLE`, `AUTH_FAILURE`, `ERROR`, `RATE_LIMITED` | Source could not be reached, timed out, or rejected credentials. | **Zero score deduction.** Flagged for officer review/retry. |

---

## 4. Append-Only History & Latest Attempt Semantics

All statutory verification attempts are appended immutably to `statutory_verification_records` in PostgreSQL.

### Deterministic Ordering
Historical records are retrieved using explicit, deterministic ordering:
```sql
ORDER BY retrieved_at DESC, created_at DESC, id DESC
```

### Previous Successful Result Preservation
When a subsequent verification run suffers a technical failure (e.g. timeout), the system:
1. Surfaces the latest attempt honestly (`connection_status: TIMEOUT`).
2. Does **not** pretend the source is currently verified.
3. Exposes the `previous_successful_result` (e.g. `VERIFIED` from the prior run) with timestamps.

---

## 5. Temporal Provenance & Zero `date.today()` Fallback

In strict compliance with Phase 8.2 locked requirements:
- Inclusive intervals: `start_date <= as_of_date <= end_date`.
- Open-ended registrations are active **only** when explicitly recorded as `ACTIVE_INDEFINITE` or `PERMANENT`.
- If `as_of_date` is omitted (`as_of_date is None`):
  - **NEVER** falls back to `date.today()`.
  - Classifies temporal status as `UNKNOWN_PERIOD` / `UNVERIFIED`.
  - Generates a structured `TEMPORAL_UNVERIFIED` officer review reason.

---

## 6. Structured Risk Reason Model

Risk reasons are emitted as typed, machine-readable `RiskReasonItem` objects:

| Reason Code | Default Severity | Description | Tracing Provenance |
| :--- | :--- | :--- | :--- |
| `ACTIVE_DEBARMENT` | `HIGH` | Entity is debarred under an active order overlapping the bid date. | `order_number`, debarring authority, date range. |
| `MAJOR_CONTRADICTION`| `HIGH` | Statutory facts contradict tender claims (e.g. turnover, local content). | Parameter name, claimed vs verified values. |
| `IDENTITY_CONFLICT` | `HIGH` | Queried identifier conflicts with authoritative bidder PAN/CIN. | Authority name, query ID, conflicting attributes. |
| `MANDATORY_CLAUSE_FAIL`| `HIGH` | Bidder failed an evaluation against a mandatory tender clause. | `clause_code`, reasoning, shortfall. |
| `INSUFFICIENT_EVIDENCE`| `REVIEW` | Required proof is missing or unsubstantiated. | `clause_code`, missing document category. |
| `OCR_LOW_CONFIDENCE` | `REVIEW` | Scanned proposal OCR confidence is below 70%. | `clause_code`, page number, confidence percentage. |
| `SOURCE_TIMEOUT` | `REVIEW` | Statutory authority request exceeded timeout threshold. | Source name, timeout duration. |
| `SOURCE_UNAVAILABLE`| `REVIEW` | Source endpoint unavailable or network transport failed. | Authority name, error message. |
| `TEMPORAL_UNVERIFIED`| `REVIEW` | Missing `as_of_date` prevented date-bounded validity check. | Reference date absence notice. |

---

## 7. Deterministic Officer Review Queue

The review queue exposes all bidders requiring human intervention.

### Review Triggers
- Active Debarment
- Major Contradiction
- Identity Conflict
- Insufficient Evidence on Mandatory Clauses
- Critical Source Unavailable / Timeout / Auth Failure
- OCR Low Confidence (< 70%) on Decisive Evidence
- Unresolved Temporal Status

### Priority Ordering
1. Overall Risk Severity: `HIGH` (Rank 0) $\to$ `MEDIUM` (Rank 1) $\to$ `LOW` (Rank 2)
2. Debarment Precedence: Actively debarred bidders sort first
3. Review Trigger Count: Descending count of triggers
4. Stable Tie-Breaker: Bidder UUID ascending

---

## 8. Score & Decision Protection Invariants

1. **Phase 6.4 100-Point Score Formula is 100% Unchanged**:
   - Tender Compliance = 50 pts
   - Statutory Consistency = 20 pts
   - Evidence Completeness = 15 pts
   - Contradictions = 15 pts
2. **Debarment is Orthogonal**: Elevates overall risk state to `HIGH`, but deducts 0 points from the mathematical compliance score.
3. **Clean Bidder Invariance**: Clean bidders retain their exact scores, LOW risk, and are omitted from the human review queue unless an external trigger occurs.
4. **Zero Automatic Decision**: The platform never executes automatic disqualification or automated winner selection. Final qualification remains the statutory prerogative of the Procurement Officer.

---

## 9. Mock / Demonstration Disclaimer

> [!IMPORTANT]
> All statutory verification adapters in this platform operate in `SourceMode.MOCK` using synthetic demonstration data (Seed `26100`, 1,000 records per source). They do not connect to live government servers, NIC gateways, or production CBDT/MCA/DigiLocker endpoints. No real applicant secrets, private credentials, or live PII are stored or transmitted.
