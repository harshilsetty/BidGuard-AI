# Contributing to BidGuard (SIH26100)

Welcome to the **BidGuard** contributor guide! This document outlines our team ownership, branching strategy, commit conventions, project management processes, and core architectural principles for our Smart India Hackathon 2026 project.

---

## 1. Team Ownership Matrix

To enable all 6 team members to work concurrently without merge bottlenecks or code conflicts, ownership is distributed as follows:

| Member | Primary Role | Domain Ownership & Responsibilities |
|---|---|---|
| **Harshil** | Team Lead & Lead AIML | • AI Engine architecture (`ai-engine/`)<br>• RAG pipeline & vector embeddings<br>• Requirement & evidence extraction models<br>• Semantic matching logic<br>• AI architecture & final integration coordinator |
| **Karthik** | Cloud & DevOps Lead | • Docker & container orchestration (`docker-compose.yml`, Dockerfiles)<br>• Cloud infrastructure & hosting configuration<br>• CI/CD GitHub Actions pipelines (`.github/workflows/`)<br>• Infrastructure security & network boundaries |
| **Kethana** | Full Stack (Frontend Lead) | • Next.js web application (`frontend/`)<br>• Officer review dashboard & telemetry panels<br>• Tender & bidder document upload interfaces<br>• Interactive compliance matrix<br>• Evidence viewer & split-screen source inspector |
| **Kesav** | Full Stack (Backend Lead) | • FastAPI REST services (`backend/app/`)<br>• Database schema design & migrations (PostgreSQL)<br>• REST API endpoints & typed Pydantic contracts<br>• Verification & audit report PDF generation<br>• Frontend/backend integration bridges |
| **Jahnavi** | Cloud & Data Pipeline | • Ingestion pipelines & document storage (`data/`)<br>• Database & cloud support<br>• Synthetic dataset creation & statutory fixtures (`data/synthetic/`)<br>• Backend testing automation<br>• Application telemetry, structured logging, & monitoring |
| **Rohitha** | QA & AIML Support | • End-to-end QA & automated test suites (`tests/`)<br>• AI/ML prompt testing & benchmark evaluation<br>• Edge-case test suites & statutory mock validation<br>• Technical documentation (`docs/`)<br>• Demo scripts & presentation workflow support |

---

## 2. Git Branching & Workflow

> [!IMPORTANT]
> **NEVER allow direct development or direct commits on `main`.**
> All active development occurs on feature or fix branches and merges into `develop`. Only vetted, stable releases merge from `develop` to `main`.

### Active Branch Hierarchy

- **`main`**: Production-ready, locked releases presented to SIH jury/evaluators.
- **`develop`**: Central integration branch for current sprint features.
- **`feature/<name>`**: New features, e.g.:
  - `feature/tender-upload`
  - `feature/compliance-engine`
  - `feature/dashboard`
  - `feature/ai-requirement-extraction`
- **`fix/<name>`**: Bug fixes, e.g.:
  - `fix/pdf-parser`
  - `fix/temporal-debarment-boundary`
- **`docs/<name>`**: Documentation updates, e.g.:
  - `docs/architecture`
  - `docs/api-specification`

### Step-by-Step Developer Workflow

1. **Pull Latest `develop`**:
   ```bash
   git checkout develop
   git pull origin develop
   ```
2. **Create Feature Branch**:
   ```bash
   git checkout -b feature/<your-feature-name>
   ```
3. **Implement Feature**:
   - Write clean, modular code within your assigned ownership boundary.
   - Keep AI prompts and models isolated in `ai-engine/` or appropriate service layers.
4. **Test Locally**:
   - Run backend tests: `pytest`
   - Run frontend checks: `npm run lint` && `npm run build`
5. **Commit with Conventional Commit Messages**:
   - Write clear, standardized commit messages (see below).
6. **Push Branch to Remote**:
   ```bash
   git push origin feature/<your-feature-name>
   ```
7. **Create Pull Request**:
   - Target base: `develop`
   - Use the repository Pull Request Template (`.github/pull_request_template.md`).
8. **Code Review**:
   - At least one code review approval required from the relevant domain owner.
9. **Merge into `develop`**:
   - Squash or merge commit into `develop`.
10. **Release to `main`**:
    - Handled strictly at scheduled milestones by Team Lead (Harshil).

---

## 3. Conventional Commit Standard

Every commit must follow the Conventional Commits specification:

`<type>: <short imperative description>`

### Allowed Types:
- `feat`: A new user-facing or platform capability.
- `fix`: A bug fix or error correction.
- `docs`: Documentation-only changes.
- `refactor`: Code restructuring without changing external behavior.
- `test`: Adding or modifying automated tests.
- `chore`: Build tasks, dependency updates, or configuration changes.

### Examples:
- `feat: add tender document upload and extraction endpoint`
- `feat: implement requirement extraction with structured JSON output`
- `fix: handle scanned PDFs with PyMuPDF OCR fallback`
- `docs: update architecture diagrams and data flow documentation`
- `test: add compliance test cases for GST and MSME exemptions`
- `chore: update docker-compose with chromadb vector store`

---

## 4. GitHub Project Board Management

All work items are tracked on the GitHub Project Board with the following columns:

```
[ BACKLOG ] ──> [ TODO ] ──> [ IN PROGRESS ] ──> [ BLOCKED ] ──> [ CODE REVIEW ] ──> [ TESTING ] ──> [ DONE ]
```

Each issue card **must** contain:
- **Owner**: Assigned team member.
- **Priority**: `P0` (Blocker), `P1` (High), `P2` (Medium), `P3` (Low).
- **Component**: `frontend`, `backend`, `ai-engine`, `data`, `infra`, `docs`.
- **Status**: Current column status.
- **Dependency**: Any upstream blocker issue or prerequisite PR.

---

## 5. Development Principles

1. **Keep modules small and understandable**: Single-responsibility functions and clean separation of concerns.
2. **Avoid unnecessary abstractions**: Write direct, legible Python and TypeScript code.
3. **Avoid premature microservices**: Maintain a clean, unified monorepo; communication between services should remain lightweight.
4. **Keep AI logic separate from business rules**: LLMs/RAG suggest extracted facts and semantic matches; business rules deterministically evaluate compliance.
5. **Keep frontend separate from backend**: Strict contract adherence via typed REST APIs and schemas.
6. **Use typed API contracts**: Pydantic models on backend; TypeScript interfaces on frontend.
7. **Write useful error messages**: Clear HTTP statuses (400, 404, 422, 500) and actionable JSON error payloads.
8. **Add tests for important logic**: Unit tests for parsers, matching logic, and statutory rules.
9. **Prefer working MVP functionality over fancy features**: Polish the core tender-to-decision pipeline first.
10. **Every feature must be demonstrable**: Deliver demonstrable, testable value in the procurement officer workflow.

---

## 6. Important SIH Compliance Rule

> [!CAUTION]
> **Strict SIH Rule on Transparency**:
> Never fabricate:
> - Government API integrations (e.g., live GeM, GSTN, Udyam, EPFO, ESIC production links).
> - Claimed accuracy percentages or synthetic dataset scale.
> - Government data access or real bidder documents.
>
> All sample and synthetic data must be explicitly documented and labeled as synthetic.
