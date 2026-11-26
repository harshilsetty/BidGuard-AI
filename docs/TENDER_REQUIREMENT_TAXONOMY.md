# TenderLens Requirement Taxonomy (Phase 2.0C)

## 1. Primary Categories (10 Authoritative Codes + Unclassified)

| Code | Category | Scope & Examples |
|---|---|---|
| `ELIG` | Eligibility | Bidder eligibility, OEM authorization, legal standing, years in business, disqualification conditions |
| `TECH` | Technical | Hardware/software specifications, capacity, architecture, performance benchmarks, interoperability |
| `FIN` | Financial | Annual turnover, net worth, solvency, Earnest Money Deposit (EMD), Performance Bank Guarantee (PBG), payment terms |
| `STAT` | Statutory | Legal, regulatory, tax (GST/PAN), Make-in-India (MII) local content, MSME/NSIC rules, non-blacklisting |
| `EXP` | Experience | Prior projects, similar work orders, contract counts/values, past performance certificates |
| `DOC` | Documentary | Required forms, affidavits, undertakings, declarations, certificates, supporting submissions |
| `DEL` | Delivery & SLA | Delivery timelines, commissioning schedules, warranty duration, uptime SLAs, liquidated damages (LD) |
| `SUB` | Submission | Bid submission format, portal instructions, two-bid/envelope rules, signing/sealing procedures |
| `DATE` | Deadlines & Milestones | Bid submission deadline, technical/financial opening dates, bid validity period, pre-bid meeting dates |
| `PREF` | Preferences | Buyer preferences, purchase preferences (MSE/MII), optional incentives, desirable advantages |
| `UNCLASSIFIED` | Unclassified / Review Needed | Statements that appear relevant to procurement obligations but cannot be confidently assigned to one of the 10 codes (automatically sets `review_status = 'NEEDS_REVIEW'`) |

- Every extracted requirement has one `primary_category` and an optional `secondary_categories: list[str]` (containing only valid secondary codes from the 10-category set when a requirement genuinely spans multiple domains).

---

## 2. Controlled Requirement Types

`QUALIFICATION`, `TECHNICAL_SPECIFICATION`, `FINANCIAL_THRESHOLD`, `CERTIFICATION`, `DECLARATION`, `DOCUMENT_SUBMISSION`, `DELIVERY_CONDITION`, `WARRANTY`, `SERVICE_LEVEL`, `SUBMISSION_INSTRUCTION`, `DEADLINE`, `PREFERENCE`, `OTHER`.

---

## 3. Obligation Status (`mandatory_status`)

- `MANDATORY`: Explicit binding language (*"must"*, *"shall"*, *"mandatory"*, *"is required to"*, *"liable for rejection"*).
- `OPTIONAL`: Preference or permissive language (*"preferable"*, *"desirable"*, *"optional"*, *"may"*).
- `UNCLEAR`: Ambiguous, contradictory, or underspecified obligation language. Automatically flagged `review_status = 'NEEDS_REVIEW'`.

---

## 4. Review Lifecycle (`review_status`)

`DRAFT`, `CONFIRMED`, `REJECTED`, `NEEDS_REVIEW`, `SUPERSEDED`.

- AI extraction **always** creates requirements in `DRAFT` or `NEEDS_REVIEW` (never `CONFIRMED`).
- Re-extraction increments `extraction_version` and never silently overwrites `CONFIRMED` or `REJECTED` records.
