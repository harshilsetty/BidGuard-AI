# [FEAT]: AI — Requirement Extraction

### Title
[FEAT]: AI — Requirement Extraction from Tender PDFs

### Objective
Implement tender PDF clause parsing using PyMuPDF and Gemini structured prompt extraction to output typed `ExtractedRequirement` models.

### Description
Parse incoming tender notices and RFPs to extract mandatory technical, financial, experience, legal, and statutory qualification criteria into standardized JSON structures with exact source page citations.

### Expected Outcome
Structured extraction of eligibility criteria from tender PDFs with 100% adherence to `ai-engine/schemas.py`.

### Acceptance Criteria
- [ ] Extracts Financial (turnover), Technical (experience), Legal (debarment), and Statutory clauses.
- [ ] Returns 1-indexed source page numbers for every clause.
- [ ] Complies with `ai-engine/schemas.py` and `docs/api/ai-contract.md`.
- [ ] Fallback OCR triggers for scanned documents with low character density.

### Owner
Harshil

### Priority
P0

### Dependencies
Frozen AI Schema (`ai-engine/schemas.py`), sample tender PDF (`data/sample/`).
