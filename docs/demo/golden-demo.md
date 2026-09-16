# SIH26100 Golden Demo Scenario: 10-Step Procurement Verification

**Target Evaluation Time**: 3 to 4 Minutes  
**Primary Evaluators**: SIH Evaluators, Ministry of Commerce & Industry / GeM Jury  
**Offline Capability**: 100% executable using offline synthetic fixtures in `data/sample/` even if external LLM APIs are offline.

---

## 1. Golden Demo Overview

This scenario demonstrates the end-to-end BidGuard compliance verification pipeline evaluating three synthetic bidders for a Government e-Marketplace (GeM) server procurement tender:
1. **Bidder A (Zenith Cloud Solutions)**: Compliant bidder (`PASS`).
2. **Bidder B (Vanguard Telecom)**: Non-compliant bidder failing turnover and debarment (`FAIL`).
3. **Bidder C (Nova Systems)**: Contradictory claims across annexures (`REVIEW`).

---

## 2. Step-by-Step Demonstration Script

### STEP 1: Upload Tender Specification
- **Action**: Procurement officer navigates to `http://localhost:3000/tenders/new`.
- **Demo Cue**: *"We begin by uploading the official Notice Inviting Tender (NIT) PDF for enterprise IT compute infrastructure."*
- **File**: `data/sample/tender_cloud_infra_2026.pdf`.

---

### STEP 2: System Extracts Requirements
- **Action**: Click **"Extract Requirements"**.
- **System Display**:
  - `REQ-001`: Minimum annual turnover ₹5.0 crore (Financial, Mandatory).
  - `REQ-002`: Minimum 3 past completed government contracts (Experience, Mandatory).
  - `REQ-003`: Clean legal record / non-debarred status (Legal, Mandatory).
- **Demo Cue**: *"Notice how BidGuard segments unstructured clauses into typed criteria with exact source page citations."*

---

### STEP 3: Upload Bidder Documents
- **Action**: Navigate to `http://localhost:3000/tenders/[id]/bidders`.
- **Demo Cue**: *"Now we upload the submitted tender dossiers for competing vendors."*
- **Action**: Upload `data/sample/bidder_compliant.json` and `data/sample/bidder_contradictory.json` dossiers.

---

### STEP 4: System Retrieves Evidence
- **Action**: Click **"Run Compliance Verification"**.
- **System Display**: Progress telemetry shows dense vector embeddings scanning bidder documents (ChromaDB RAG) and extracting key clauses into typed evidence snippets.

---

### STEP 5: System Evaluates Compliance
- **System Execution**:
  - LLM evaluates semantic alignment.
  - Deterministic Python rules evaluate numeric turnover (e.g. ₹8.45 Cr vs ₹5.0 Cr) and check active debarment dates.
  - Zero hallucination: Math is checked deterministically.

---

### STEP 6: Dashboard Shows Status (PASS / FAIL / REVIEW)
- **Display**: The Compliance Matrix Table renders:
  - 🟢 **PASS** for Zenith Cloud Solutions (Score: 96.5 / 100).
  - 🔴 **FAIL** for Vanguard Telecom (Score: 38.0 / 100).
  - 🟡 **REVIEW** for Nova Systems (Score: 62.0 / 100).

---

### STEP 7: Click a Failed Requirement
- **Action**: Click on the failed row for Vanguard Telecom: `[REQ-001: Minimum Turnover ₹5.0 Crore]`.
- **System Display**: The side drawer immediately pops out.

---

### STEP 8: Inspect Evidence Drawer
- **Display**:
  - **Document Name**: `financial_balance_sheet_2023.pdf`
  - **Page Number**: `Page 5`
  - **Evidence Text**: *"Average turnover for the firm over the stated period is INR 2.80 crore."*
  - **Reason**: *"Turnover of ₹2.80 crore is below mandatory threshold of ₹5.0 crore (Deterministic rule validation)."*
  - **Confidence**: `100% (Deterministic Code Override)`
- **Demo Cue**: *"The officer doesn't need to hunt through a 100-page PDF. BidGuard gives the exact page, the quote, and the mathematical proof."*

---

### STEP 9: Show Contradiction & Review Example
- **Action**: Click on the amber row for Nova Systems: `[REQ-002: Minimum 5 Years Experience]`.
- **Display**:
  - Status: 🟡 **REVIEW**
  - Contradiction Flag: **TRUE**
  - **Evidence 1**: `nova_technical_overview.pdf` (Page 2) — Claims *"over 6 years of proven industry experience"*.
  - **Evidence 2**: `certificate_of_incorporation.pdf` (Page 1) — Proves legal incorporation date is *"18th July 2023"*.
  - **Reason**: *"Conflicting evidence detected: Technical proposal claims 6 years experience, but incorporation certificate proves company is less than 3 years old."*
- **Demo Cue**: *"This is what makes BidGuard unique. It cross-checks multiple bidder annexures against each other to catch deceptive fabrication."*

---

### STEP 10: Generate Tamper-Proof Audit Report
- **Action**: Click **"Generate Audit Report PDF"**.
- **Display**: A digitally sealed summary PDF is downloaded, complete with requirement-by-requirement audit trace, timestamps, and an officer electronic signature placeholder.
- **Demo Cue**: *"The Procurement Officer retains 100% decision authority under GFR 2017. BidGuard delivers the decision support."*
