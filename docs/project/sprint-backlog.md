# Sprint 1 Workstream Backlog — SIH26100 BidGuard

This document establishes the official 10-issue workstream breakdown, domain owners, priorities, acceptance criteria, and critical path dependency graph for the 6-member engineering team.

---

## 1. Critical Path & Dependency Order

```
[Issue 8: Synthetic Data Fixtures] (Jahnavi) ──┐
                                                ├──> [Issue 1 & 2: AI Requirement & Evidence Extraction] (Harshil + Rohitha)
[Issue 7: Docker & Local Infra] (Karthik) ─────┤                           │
                                                │                           ▼
                                                │     [Issue 3 & 4: Backend APIs & Compliance Engine] (Kesav)
                                                │                           │
                                                │                           ▼
                                                │     [Issue 5 & 6: Frontend Upload & Compliance UI] (Kethana)
                                                │                           │
                                                │                           ▼
                                                └─>   [Issue 9: QA Integration & Edge Cases] (Rohitha + Jahnavi)
                                                                            │
                                                                            ▼
                                                      [Issue 10: SIH Jury Demo & Audit Documentation] (Rohitha + Lead)
```

### Dependency Rules:
1. **AI Schema (`docs/api/ai-contract.md`)** is frozen first.
2. **Backend API Contract (`docs/api/api-specification.md`)** implements the frozen AI schema.
3. **Frontend Contract (`docs/api/frontend-contract.md`)** consumes the backend endpoints.
4. **Data Fixtures (`data/sample/`)** are available immediately so backend, AI, and frontend can develop against mock JSON concurrently.
5. **Cloud (Docker Compose)** provides the unified runtime (`postgres`, `chromadb`, `backend`, `frontend`).
6. **QA** executes automated regression suites against every pull request.

---

## 2. Workstream Issues (1 to 10)

### ISSUE 1: AI — Requirement Extraction
- **Owner**: Harshil (Team Lead, AIML)
- **Priority**: `P0` (Blocker / High)
- **Objective**: Implement tender PDF clause parsing using PyMuPDF and Gemini structured prompt extraction to output typed `ExtractedRequirement` models.
- **Acceptance Criteria**:
  - [ ] Extracts Financial (turnover), Technical (past experience), Legal (debarment), and Statutory clauses from tender PDFs.
  - [ ] Returns 1-indexed source page numbers for every clause.
  - [ ] Complies with `ai-engine/schemas.py` and `docs/api/ai-contract.md`.
  - [ ] Fallback OCR triggers for scanned documents with low character density.
- **Dependencies**: Frozen AI Schema (`ai-engine/schemas.py`), sample tender PDF (`data/sample/`).

---

### ISSUE 2: AI — Evidence Extraction & Retrieval
- **Owner**: Harshil + Rohitha
- **Priority**: `P0` (Blocker / High)
- **Objective**: Implement bidder submission PDF parsing, dense vector indexing (ChromaDB), and semantic candidate retrieval to match extracted requirements.
- **Acceptance Criteria**:
  - [ ] Chunks bidder submission documents and stores embeddings in ChromaDB collection.
  - [ ] Semantic retriever returns top-3 candidate evidence chunks with confidence scores.
  - [ ] Contradiction detection engine flags conflicting claims between separate annexures.
  - [ ] Zero uncontrolled text; outputs adhere strictly to `AIComplianceEvaluation`.
- **Dependencies**: Issue 1 (Requirement Extractor), ChromaDB service (`docker-compose.yml`).

---

### ISSUE 3: Backend — Tender & Bidder Upload APIs
- **Owner**: Kesav (Full Stack Backend)
- **Priority**: `P1` (High)
- **Objective**: Expose robust multipart REST endpoints `POST /tender/upload` and `POST /bidder/upload` with validation, disk storage, and database persistence.
- **Acceptance Criteria**:
  - [ ] Validates PDF MIME type and enforces 25 MB max file size limit.
  - [ ] Stores files under UUID filenames in `uploads/` to prevent path traversal attacks.
  - [ ] Computes and stores SHA-256 integrity hash for each uploaded file.
  - [ ] Creates records in PostgreSQL `Tender`, `Bidder`, and `Document` tables.
- **Dependencies**: Database Schema (`docs/architecture/database-schema.md`), PostgreSQL container.

---

### ISSUE 4: Backend — Verification & Compliance APIs
- **Owner**: Kesav (Full Stack Backend)
- **Priority**: `P0` (Critical)
- **Objective**: Expose `POST /verification/start`, `GET /verification/{id}`, `GET /requirements/{id}`, `GET /evidence/{id}`, and `GET /report/{id}`.
- **Acceptance Criteria**:
  - [ ] Integrates AI Engine output with deterministic Rule Engine (turnover comparison, debarment checks).
  - [ ] Computes 100-point composite compliance score and writes `ComplianceResult` rows.
  - [ ] Exposes exact source document and page number for every evaluated clause.
  - [ ] Returns HTTP 202 Accepted on start and handles asynchronous polling.
- **Dependencies**: Issue 1, Issue 2, and Issue 3.

---

### ISSUE 5: Frontend — Upload Workflow
- **Owner**: Kethana (Full Stack Frontend)
- **Priority**: `P1` (High)
- **Objective**: Build the user-friendly upload interface for tenders and bidder dossiers in Next.js 15.
- **Acceptance Criteria**:
  - [ ] Drag-and-drop file picker with client-side file size and extension checks.
  - [ ] Displays parsed tender requirements summary cards upon tender upload.
  - [ ] Multi-document upload station for bidder proposals, CA certificates, and annexures.
  - [ ] Clear loading and error state notifications for failed network requests.
- **Dependencies**: Issue 3 (Upload APIs), Frontend Contract (`docs/api/frontend-contract.md`).

---

### ISSUE 6: Frontend — Compliance Dashboard & Evidence Viewer
- **Owner**: Kethana (Full Stack Frontend)
- **Priority**: `P0` (Critical)
- **Objective**: Build the procurement officer review dashboard, compliance matrix table, and split-screen PDF evidence inspector.
- **Acceptance Criteria**:
  - [ ] Interactive Compliance Matrix displaying Requirement, Status (`PASS`/`FAIL`/`REVIEW`), Evidence, Source, Confidence, and Reason.
  - [ ] Clicking any requirement opens side drawer with highlighted evidence text and page jump.
  - [ ] Visual distinction: Green (`PASS`), Red (`FAIL`), Amber (`REVIEW`).
  - [ ] Officer notes input and "Download Audit Report PDF" action.
- **Dependencies**: Issue 4 (Compliance APIs), Frontend Contract (`docs/api/frontend-contract.md`).

---

### ISSUE 7: Cloud — Docker & Deployment
- **Owner**: Karthik (Cloud & DevOps)
- **Priority**: `P1` (High)
- **Objective**: Ensure seamless multi-container orchestration (`postgres`, `chromadb`, `backend`, `frontend`) and reproducible development environments.
- **Acceptance Criteria**:
  - [ ] `docker compose up --build` boots all 4 services healthy on localhost:3000, 8000, 8001, 5432.
  - [ ] Volume persistence configured for PostgreSQL (`pgdata`) and ChromaDB (`chroma_data`).
  - [ ] GitHub Actions CI pipeline passes tests and production builds on push/PR.
  - [ ] Zero committed secrets verified via automated `.gitignore` checks.
- **Dependencies**: Backend `Dockerfile.backend`, Frontend `Dockerfile.frontend`.

---

### ISSUE 8: Data — Synthetic Tender & Bidder Dataset
- **Owner**: Jahnavi (Cloud & Data)
- **Priority**: `P1` (High)
- **Objective**: Curate realistic, non-confidential GFR-compliant tender specifications and synthetic bidder dossiers covering PASS, FAIL, and CONTRADICTORY cases.
- **Acceptance Criteria**:
  - [ ] Seed fixtures created under `data/sample/`: `bidder_compliant.json`, `bidder_non_compliant.json`, `bidder_contradictory.json`.
  - [ ] All datasets explicitly labeled as synthetic with zero claims of unauthorized government access.
  - [ ] Contradictory bidder fixture specifically exercises conflicting date/experience claims.
  - [ ] `scripts/seed_mock_data.py` executes idempotently to populate local databases.
- **Dependencies**: None (Can proceed immediately).

---

### ISSUE 9: QA — Edge Cases & Integration Tests
- **Owner**: Rohitha + Jahnavi
- **Priority**: `P1` (High)
- **Objective**: Build and maintain the automated test suite in `tests/e2e/` covering deterministic rules, missing evidence, and edge cases.
- **Acceptance Criteria**:
  - [ ] 6 core scenarios tested: PASS, FAIL, REVIEW, Missing evidence, Numeric threshold, and Contradictory evidence.
  - [ ] All `pytest tests/e2e -v` tests pass in under 1 second.
  - [ ] Validates Pydantic schema rejection when AI responses are malformed.
  - [ ] Continuous regression testing during feature merges into `develop`.
- **Dependencies**: Issue 1, Issue 2, Issue 4, Issue 8.

---

### ISSUE 10: Documentation & SIH Demo
- **Owner**: Rohitha + Team Lead (Harshil)
- **Priority**: `P1` (High)
- **Objective**: Maintain complete, judge-ready documentation and prepare the 10-step Golden Demo presentation.
- **Acceptance Criteria**:
  - [ ] Complete `docs/demo/golden-demo.md` verified runnable offline with sample fixtures.
  - [ ] Architecture diagrams up-to-date in `docs/architecture/`.
  - [ ] Video demonstration / presentation slide deck prepared for SIH jury.
  - [ ] Strict compliance with SIH honesty guidelines (no fake government API claims).
- **Dependencies**: Issue 6 (Compliance Dashboard), Issue 8 (Synthetic Data).
