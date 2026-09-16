# SIH 2026 Jury Demonstration Flow — BidGuard (SIH26100)

**Target Audience**: SIH Evaluators, Ministry of Commerce & Industry / GeM Jury, Procurement Officers  
**Scenario**: Evaluation of Bids for GeM Tender `GEM/2026/B/891241` (Procurement of Enterprise Cloud & Compute Infrastructure)

---

## 1. Demo Objectives & Value Proposition

1. **Demonstrate Speed**: Reduce manual bid evaluation time from 4–5 days to under 90 seconds.
2. **Demonstrate Accuracy & Rigor**: Automatic detection of hidden non-compliances (expired certificates, active debarment periods, insufficient turnover).
3. **Demonstrate Explainability**: Every compliance status is linked to an exact source PDF page and verifiable quote.
4. **Demonstrate Officer Empowerment**: Emphasize decision support—officer retains final sign-off authority.

---

## 2. Step-by-Step Jury Walkthrough

### Phase 1: Upload Tender Specification (30 seconds)
- **Action**: Navigate to `http://localhost:3000/tenders/upload`.
- **Demo Step**:
  - Drag-and-drop sample tender document: `data/sample/tender_cloud_infra_2026.pdf`.
  - Click **"Extract Requirements"**.
- **System Behavior**:
  - PyMuPDF extracts clauses; LLM segments them into Financial, Technical, Statutory, and Experience criteria.
  - Officer views parsed criteria list with page numbers within 3 seconds.

---

### Phase 2: Upload Bidder Submissions (30 seconds)
- **Action**: Upload bidder technical submissions:
  - Bidder A: *Apex Tech Solutions* (Fully compliant bidder).
  - Bidder B: *Vanguard Systems Ltd* (Debarred entity with expired MSME certificate).
- **Demo Step**:
  - Click **"Initiate Integrated Verification"**.

---

### Phase 3: Statutory & Cross-Source Verification (20 seconds)
- **Display**: The dashboard animates the statutory verification progress across:
  - **GSTN Verification**: Confirms active taxpayer status.
  - **Udyam / MSME Verification**: Identifies Micro enterprise exemption claim.
  - **DPIIT Startup India**: Confirms DPIIT registration number.
  - **EPFO & ESIC**: Verifies active establishment records and wage filings.
  - **Debarment Central Registry**: Evaluates temporal ban status.
- **Key Demo Highlight**:
  - Show Bidder B flagged with **TEMPORAL DEBARMENT** (Debarred by Ministry order dated Jan 2025 – Dec 2026).
  - Show how Bidder B's turnover is automatically flagged as **FAIL** (presents 25 Lakhs vs mandatory 50 Lakhs).

---

### Phase 4: Compliance Matrix & Evidence Inspector (30 seconds)
- **Display**: Navigate to the interactive Compliance Matrix for Bidder A (`/tenders/{id}/compliance`).
- **Demo Step**:
  - Click on a clause chip: `[PASS: Experience >= 3 Years]`.
  - The side-by-side Evidence Viewer immediately scrolls to **Page 5** of Bidder A's submission, highlighting the completion certificate issued by Indian Railways.
  - Show the **Confidence Bar (96%)** and grounding reasoning.

---

### Phase 5: Verification Intelligence & Officer Risk Cockpit (20 seconds)
- **Display**: The Verification Intelligence Panel aggregates:
  - Total Sources Verified: 7 registries.
  - Cross-Source Contradictions: 0 contradictions found.
  - Technical Errors: 0 timeouts.
  - Overall Composite Compliance Score: **94.5 / 100**.

---

### Phase 6: Procurement Officer Sign-Off & Audit Report (20 seconds)
- **Action**:
  - Officer enters evaluation remarks: *"Bidder meets all mandatory GFR criteria. Cleared for technical qualification."*
  - Click **"Generate Audit Report PDF"**.
- **Result**:
  - Downloaded PDF displays complete chronological verification history, statutory verification hashes, and officer electronic sign-off stamp.
