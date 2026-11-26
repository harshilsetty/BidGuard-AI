# TenderLens Requirement Extraction Evaluation (Phase 2.0C)

**Repository:** `harshilsetty/BidGuard-AI`  
**Evaluation Date:** 2026-11-27  
**Reference Fixture:** `backend/sample_data/sample_gem_tender.pdf` (4 pages, 258 words, `DIGITAL_TEXT`)

---

## 1. Annotation Protocol & Reference Set

Because no pre-existing 10-category annotated gold-standard dataset existed in the repository, a manual inspection protocol was applied to `backend/sample_data/sample_gem_tender.pdf`:
- **Source:** 4-page Government e-Marketplace (GeM) Notice Inviting Tender (`GEM/2026/B/891204`).
- **Expected Requirement Span (13 primary clauses across 4 sections):**
  - Page 1: `1.1` Make in India (`STAT`, `MANDATORY`), `1.2` Minimum Annual Turnover (`FIN`, `MANDATORY`), `1.3` MSE EMD Exemption (`PREF`/`FIN`, `OPTIONAL`/conditional).
  - Page 2: `2.1` Processor Architecture (`TECH`, `MANDATORY`), `2.2` System Memory (`TECH`, `MANDATORY`), `2.3` Storage Subsystem (`TECH`, `MANDATORY`), `2.4` Warranty and Support (`DEL`, `MANDATORY`).
  - Page 3: `3.1` Past Experience Criteria (`EXP`, `MANDATORY`), `3.2` Quality Certifications (`STAT`/`TECH`, `MANDATORY`), `3.3` OEM Authorization (`DOC`/`ELIG`, `MANDATORY`).
  - Page 4: `4.1` Delivery Schedule (`DEL`, `MANDATORY`), `4.2` Liquidated Damages (`DEL`, `MANDATORY`), `4.3` Payment Terms (`FIN`, `MANDATORY`).
- **Validation Status:** Preliminary internal reference set (not an external multi-tender benchmark).

---

## 2. Live LLM Provider Probe Results

Running `TenderRequirementExtractionService` against `sample_gem_tender.pdf` with the configured NVIDIA NIM credentials produced:

1. **Configured Default (`settings.NVIDIA_MODEL = "openai/gpt-oss-20b"`):**
   - **Observed Outcome:** HTTP `410 Gone` — `"The model 'openai/gpt-oss-20b' has reached its end of life on 2026-11-18T08:00:00Z and is no longer available."`
   - **Service Behavior:** Failed safely by raising `RequirementExtractionProviderError("LLM_PROVIDER_ERROR")` after bounded retry; did **not** fabricate requirements or mark extraction `SUCCEEDED`.
2. **Alternate Model Probe (`"google/gemma-3-12b-it"`):**
   - **Observed Outcome:** HTTP `404 Not Found` (`Function 'ee47df99-c92b-4dc9-b3a7-f3fb0f087b73': Not found for account`).

---

## 3. Metrics Summary (Honest Separation)

| Metric | Status | Observed Value / Notes |
|---|---|---|
| Requirement Precision $TP / (TP + FP)$ | **Unmeasured (Blocked by Provider EOL/404)** | No active NIM chat model available on configured account to run live inference |
| Requirement Recall $TP / (TP + FN)$ | **Unmeasured (Blocked by Provider EOL/404)** | Requires active LLM endpoint (`NVIDIA_MODEL` update + account entitlement) |
| Category / Mandatory Accuracy (Live LLM) | **Unmeasured (Blocked by Provider EOL/404)** | Same as above |
| Schema Validation & Grounding Verification (`test_phase2_0c_requirements.py`) | **Verified (Mocked LLM Responses)** | `5/5` structured items validated: verbatim quotes verified (`source_quote_verified=True`), unsupported quote downgraded (`NEEDS_REVIEW`, `confidence <= 0.45`), unknown category/status mapped to `UNCLASSIFIED` + `UNCLEAR` + `NEEDS_REVIEW`, invalid JSON & timeout rejected cleanly |

---

## 4. Known Limitations & Next Steps for Benchmarking

1. **Configured Model EOL:** `settings.NVIDIA_MODEL` (`openai/gpt-oss-20b`) is end-of-life (`410 Gone`); update `.env` / `NVIDIA_MODEL` to an active, entitled model on the deployment's NVIDIA NIM account before running live extraction.
2. **Sample Size:** `sample_gem_tender.pdf` is a 4-page synthetic GeM tender; real multi-document tenders (50–500 pages, scanned PDFs, tables, corrigenda) require a larger human-annotated evaluation corpus before claiming production accuracy.
