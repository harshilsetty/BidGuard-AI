# Current Sprint Execution Plan

## Sprint Goal

> **Make the complete Golden Demo work end-to-end for SIH 2026 jury presentation.**

---

## Priority Task Breakdown

### P0 — Critical (Core Verification Path)

1. **Requirement Extraction**
   - **Owner**: Harshil
   - **Scope**: Parse tender specifications via PyMuPDF + GeminiAdapter into structured `ExtractedRequirement` models.
   - **Contract**: `docs/api/ai-contract.md`

2. **Evidence Extraction & Retrieval**
   - **Owner**: Harshil + Rohitha
   - **Scope**: Parse bidder submission PDFs, index dense embeddings into ChromaDB, and retrieve candidate evidence quotes with page references.
   - **Contract**: `docs/api/ai-contract.md`

3. **Tender / Bidder Upload APIs**
   - **Owner**: Kesav
   - **Scope**: Expose `POST /tender/upload` and `POST /bidder/upload` with 25MB file validation and database persistence.
   - **Contract**: `docs/api/api-specification.md`

4. **Verification & Compliance APIs**
   - **Owner**: Kesav
   - **Scope**: Expose `POST /verification/start`, `GET /verification/{id}`, and `GET /report/{id}` combining semantic matching with deterministic rule validation.
   - **Contract**: `docs/api/api-specification.md`

5. **Upload Workflow UI**
   - **Owner**: Kethana
   - **Scope**: Build the Next.js upload station for tender RFPs and bidder submission dossiers with client-side file checks.
   - **Contract**: `docs/api/frontend-contract.md`

6. **Compliance Dashboard & Evidence Viewer**
   - **Owner**: Kethana
   - **Scope**: Interactive Compliance Matrix (`PASS` / `FAIL` / `REVIEW`) and side-drawer Evidence Viewer with source PDF page citations.
   - **Contract**: `docs/api/frontend-contract.md`

---

### P1 — Foundation, Data, Testing & Presentation

7. **Docker & Cloud Deployment**
   - **Owner**: Karthik
   - **Scope**: Validate multi-container orchestration (`postgres`, `chromadb`, `backend`, `frontend`) and CI/CD pipelines.

8. **Synthetic Tender & Bidder Dataset**
   - **Owner**: Jahnavi
   - **Scope**: Curate compliant, non-compliant, and contradictory synthetic procurement documents under `data/sample/`.

9. **Edge-Case & Integration Testing**
   - **Owner**: Rohitha + Jahnavi
   - **Scope**: Expand automated test suites in `tests/e2e/` covering missing evidence, turnover thresholds, and debarment edge cases.

10. **Documentation & Demo Rehearsal**
    - **Owner**: Rohitha + Harshil
    - **Scope**: Maintain judge-ready documentation and rehearse the 10-step Golden Demo (`docs/demo/golden-demo.md`).

---

## Development Order

```
Phase 1: Tender upload ➔ PDF extraction ➔ Requirement extraction
   ↓
Phase 2: Bidder upload ➔ Evidence extraction ➔ Evidence retrieval
   ↓
Phase 3: Requirement vs evidence ➔ Rule validation ➔ PASS / FAIL / REVIEW
   ↓
Phase 4: Dashboard ➔ Evidence viewer ➔ Risk score
   ↓
Phase 5: Report ➔ Full end-to-end demo ➔ Deployment
```

---

## Definition of Done

> [!IMPORTANT]
> **A feature is NOT done simply because the code exists.**
> It is done only when:
> - [ ] Code works as intended.
> - [ ] Automated tests pass (`pytest` / Next.js build).
> - [ ] Frozen API contracts are strictly respected.
> - [ ] No secrets, keys, or credentials are committed.
> - [ ] Relevant technical documentation exists.
> - [ ] The feature can be demonstrated live in the Golden Demo flow.
