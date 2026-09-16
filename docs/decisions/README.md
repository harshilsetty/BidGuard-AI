# Architecture Decision Records (ADRs) — BidGuard

This directory documents key architectural decisions, design rationale, and engineering trade-offs made during the development of BidGuard for Smart India Hackathon 2026.

---

## Index of Architecture Decision Records

| ADR ID | Title | Status | Date |
|---|---|---|---|
| **ADR-001** | [Monorepo Structure for 6-Person Parallel Work](#adr-001-monorepo-structure-for-6-person-parallel-work) | **Accepted** | 2026-09-10 |
| **ADR-002** | [Deterministic Rule Validation Over Probabilistic LLM Matching](#adr-002-deterministic-rule-validation-over-probabilistic-llm-matching) | **Accepted** | 2026-09-11 |
| **ADR-003** | [Human-in-the-Loop Procurement Decision-Support System](#adr-003-human-in-the-loop-procurement-decision-support-system) | **Accepted** | 2026-09-12 |
| **ADR-004** | [Explicit Synthetic Statutory Data Modeling vs Fake Government APIs](#adr-004-explicit-synthetic-statutory-data-modeling-vs-fake-government-apis) | **Accepted** | 2026-09-13 |
| **ADR-005** | [Strict AI Structured Output JSON Contract (PASS / FAIL / REVIEW)](#adr-005-strict-ai-structured-output-json-contract) | **Accepted** | 2026-09-14 |

---

### ADR-001: Monorepo Structure for 6-Person Parallel Work

- **Context**: 6 developers with distinct domains (AI/ML, Backend, Frontend, Cloud/DevOps, Data, QA) must work simultaneously during SIH sprints without blocking each other or causing merge conflicts.
- **Decision**: Adopt a clean monorepo containing `/frontend`, `/backend`, `/ai-engine`, `/data`, `/docs`, `/scripts`, and `/.github`.
- **Consequences**:
  - Independent dependency files (`requirements.txt` in backend and ai-engine, `package.json` in frontend).
  - Clean boundary ownership mapped in `CONTRIBUTING.md`.
  - Simple local developer setup via single `docker-compose.yml`.

---

### ADR-002: Deterministic Rule Validation Over Probabilistic LLM Matching

- **Context**: Public procurement under GFR 2017 requires transparent, legally defensible compliance checks. Pure LLM judgments risk hallucinations, nondeterminism, and legal challenge.
- **Decision**: Use LLMs and RAG strictly for semantic text extraction and candidate discovery. Enforce hard deterministic code rules for numeric thresholds (turnover, experience years), registration expiry dates, and debarment timelines.
- **Consequences**:
  - Zero hallucinated compliance passes on statutory requirements.
  - Deterministic rules can override model predictions and log an audit reason.

---

### ADR-003: Human-in-the-Loop Procurement Decision-Support System

- **Context**: Autonomous AI disqualification is illegal under Indian public procurement regulations. Procurement officers are personally liable for tender awards.
- **Decision**: Design BidGuard strictly as a **decision-support platform**. The AI flags issues, highlights evidence, computes risk scores, and recommends actions; the procurement officer makes the final binding qualification decision.
- **Consequences**:
  - Clear UI audit trails showing human sign-offs.
  - No claims of fully autonomous government procurement replacement.

---

### ADR-004: Explicit Synthetic Statutory Data Modeling vs Fake Government APIs

- **Context**: SIH guidelines strictly prohibit falsely claiming live government production credentials. Live GeM/GSTN/Udyam APIs require government sandbox authorization.
- **Decision**: Model realistic synthetic registries (1,000 deterministically seeded records for GSTN, Udyam, DPIIT, EPFO, ESIC, NSIC, DigiLocker) conforming to published government schemas. Explicitly label all mock data in documentation and UI.
- **Consequences**:
  - 100% honesty and transparency before SIH evaluators and jury.
  - Pluggable adapter architecture ready for live REST/SOAP government endpoints when authorized.

---

### ADR-005: Strict AI Structured Output JSON Contract

- **Context**: Free-form text responses from LLMs break frontend dashboards and fail automated validation.
- **Decision**: AI engine outputs must conform to a typed Pydantic schema returning `requirement`, `evidence`, `source_document`, `page`, `status` (`PASS`, `FAIL`, `REVIEW`), `confidence`, and `reason`.
- **Consequences**:
  - Reliable frontend rendering.
  - Direct database persistence without custom text scraping.
