# BidGuard AI

## AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement

**Smart India Hackathon 2026** | **Problem Statement ID: SIH26100** | **Theme: Smart Automation** | **Category: Software**

> *"AI assists. Evidence explains. Rules verify. Humans decide."*

---

> [!IMPORTANT]
> **Prototype & Demonstration Notice**:
> - This repository contains a **prototype / sandbox demonstration** developed for SIH 2026 evaluation.
> - The demonstration procurement records, bidder documents, and statutory registry records are **synthetic** or anonymized public-domain specimens.
> - The platform does not connect to live, closed-access government production databases (GeM, GSTN, MCA21, CBDT, etc.) without authorized production credentials.
> - Disqualification and contract award are **never automated**. **The final procurement decision remains with the authorized procurement officer.**

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Solution](#3-solution)
4. [Core Architecture](#4-core-architecture)
5. [Key Features](#5-key-features)
6. [Golden Demo](#6-golden-demo)
7. [PASS Scenario](#7-pass-scenario)
8. [FAIL Scenario](#8-fail-scenario)
9. [REVIEW / Contradiction Scenario](#9-review--contradiction-scenario)
10. [Evidence Drawer](#10-evidence-drawer)
11. [Human-in-the-Loop Adjudication](#11-human-in-the-loop-adjudication)
12. [Dashboard](#12-dashboard)
13. [Technology Stack](#13-technology-stack)
14. [Why This Architecture](#14-why-this-architecture)
15. [Safety and Trust Model](#15-safety-and-trust-model)
16. [Current PoC Status](#16-current-poc-status)
17. [Local Development](#17-local-development)
18. [Docker Deployment](#18-docker-deployment)
19. [Testing & Verification](#19-testing--verification)
20. [Project Structure](#20-project-structure)
21. [UI/UX Design System](#21-uiux-design-system)
22. [Data and Limitations](#22-data-and-limitations)
23. [Future Scope](#23-future-scope)
24. [Research Basis](#24-research-basis)
25. [Team](#25-team)
26. [Responsible Use](#26-responsible-use)
27. [Contributing](#27-contributing)
28. [Security Policy](#28-security-policy)
29. [SIH 2026 Information](#29-sih-2026-information)
30. [Project Links](#30-project-links)

---

## 1. Overview

**BidGuard AI** is an explainable, evidence-backed decision-support system designed for public procurement evaluation on the Government e-Marketplace (GeM). It bridges the critical gap between unstructured procurement documents (hundreds of pages of technical brochures, financial statements, and CA certificates) and deterministic statutory compliance under General Financial Rules (GFR 2017).

By pairing semantic understanding with a zero-hallucination deterministic Python rule engine, BidGuard AI extracts technical specifications and financial figures, links every claim to source page coordinates, detects cross-document contradictions, queries multi-source statutory registers, and presents findings in a human-centric officer cockpit.

---

## 2. Problem Statement

### Background: SIH26100 — Smart Automation

Public procurement across Central Ministries, Defence, State Departments, and PSUs on GeM involves millions of high-value transactions. Every Notice Inviting Tender (NIT) mandates rigorous multi-category eligibility:
- Technical specifications and minimum functional thresholds
- Average annual turnover and audited financial viability
- Past performance and project delivery experience
- Statutory compliance (GST, MSME/Udyam, Make in India, PAN, Debarment)

### Operational Pain Points

1. **Manual Ingestion Bottleneck**: Officers spend days manually reviewing multi-hundred-page technical brochures, balance sheets, and annexures across dozens of competing bidders per tender.
2. **Hidden Contradictions & Irregularities**: Bidders may state one financial turnover figure in self-declarations (e.g., Annexure I) while the audited balance sheet or CA certificate shows a lower amount.
3. **Risks of Generic LLM Hallucination**: Off-the-shelf generative AI cannot be trusted with public funds; LLMs can fabricate numbers, hallucinate compliant specifications, and fail to provide auditable citations.
4. **Disjointed Statutory Verification**: Verification against statutory registers (GSTN, Udyam, MCA, CBDT, Debarment) is typically performed piecemeal across distinct portals, creating blind spots.

---

## 3. Solution

BidGuard AI addresses these challenges with a **hybrid decision-support architecture**:

- **AI Semantic Ingestion**: High-precision PDF extraction (PyMuPDF with OCR fallback) and dense embedding retrieval (NVIDIA Nemotron Embeddings, 2048-dim) locate candidate evidence spans across complex bidder dossiers.
- **Strict Evidence Grounding**: Every extracted fact is bound to an immutable citation: document name, page number, bounding coordinates, and verbatim text quotation.
- **Deterministic Verification Engine**: Disqualification and compliance calculations are executed by hard-coded, auditable Python logic, completely isolating mathematical comparisons from LLM generation.
- **Contradiction Detection Engine**: Automatically compares multiple declarations of the same metric across all uploaded bidder files, flagging internal discrepancies for human officer review.
- **Statutory Cross-Verification Orchestrator**: Concurrently cross-references bidder claims against simulated authoritative registers (GSTN, Udyam, MCA, Income Tax, Make in India, Debarment, DPIIT, EPFO, ESIC, NSIC, DigiLocker).
- **Human Officer Supremacy**: The system never unilaterally disqualifies any vendor. Edge cases, contradictions, and shortfalls route to `REVIEW` with clear explanations for officer adjudication.

---

## 4. Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BIDGUARD AI ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────────────┘

    Tender Notice (NIT PDF)                 Bidder Dossiers (Technical / CA / EMD)
               │                                               │
               ▼                                               ▼
    ┌──────────────────────┐                       ┌──────────────────────┐
    │  PyMuPDF Text / OCR  │                       │  PyMuPDF Text / OCR  │
    └──────────┬───────────┘                       └──────────┬───────────┘
               │                                               │
               ▼                                               ▼
    ┌──────────────────────┐                       ┌──────────────────────┐
    │  Clause Extractor    │                       │  Document Chunking   │
    │  (11 GFR Categories) │                       │  & Dense Embeddings  │
    └──────────┬───────────┘                       └──────────┬───────────┘
               │                                               │
               └───────────────────────┬───────────────────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │   Semantic Candidate Search   │
                       │   (NVIDIA Nemotron 2048-dim)  │
                       └───────────────┬───────────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │  Deterministic Rule Engine    │
                       │  - Numeric threshold test     │
                       │  - Cross-doc contradiction    │
                       │  - Time-aware debarment check │
                       └───────────────┬───────────────┘
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        ▼                                                             ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│ Statutory Orchestrator (Mock) │             │  Pydantic Structured Contract │
│ - GSTN, Udyam, MCA, Income Tax│             │  - Status: PASS / FAIL / REV  │
│ - MII, Debarment, EPFO, ESIC  │             │  - Grounded Evidence Snippet  │
│ - DPIIT, NSIC, DigiLocker     │             │  - Page Citation & Provenance │
└───────────────┬───────────────┘             └───────────────┬───────────────┘
                │                                             │
                └──────────────────────┬──────────────────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │   Officer Cockpit (Next.js)   │
                       │   - Visual Compliance Matrix  │
                       │   - Side-by-Side Evidence     │
                       │   - Adjudication & Override   │
                       └───────────────┬───────────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │    Authorized Human Officer   │
                       │         FINAL DECISION        │
                       └───────────────────────────────┘
```

---

## 5. Key Features

- **Clause Extraction Taxonomy**: Automatically parses and standardizes requirements into Technical, Financial, Statutory, Experience, Delivery SLA, and Security categories.
- **Provenance-Grounded Evidence**: Highlights verbatim source text extracts with document name and page number citations.
- **Deterministic Arithmetic Engine**: Evaluates `>=` and `<=` logic deterministically (e.g., minimum turnover, core count, experience years).
- **Cross-Document Contradiction Detection**: Flags conflicts between bidder self-declarations and third-party audited certificates.
- **Unified Statutory Verification (11 Registers)**: Concurrent asynchronous checks across GSTN, Udyam, MCA, CBDT PAN, Make in India, Debarment, DPIIT, EPFO, ESIC, NSIC, and DigiLocker.
- **Temporal Debarment Engine**: Time-aware blacklist validation verifying whether debarment orders were active on the bid cutoff date.
- **Interactive Evidence Drawer**: Split-screen drawer displaying raw text extracts, confidence scores, extraction methods (digital vs OCR), and document references.
- **Officer Adjudication Audit Trail**: Human officers can confirm, reject, or override any compliance determination with mandatory recorded remarks.
- **Comprehensive Tender Dashboard**: Overview of procurement tenders, extraction progress, bidder counts, and compliance matrices.

---

## 6. Golden Demo

The repository includes a verified Golden Demonstration tender:

| Parameter | Specification |
| :--- | :--- |
| **Tender ID** | `7d6c8530-d780-40f5-a0c3-45f8d7577752` |
| **GeM Tender Reference** | `GEM/2026/B/8912450` |
| **Title** | Enterprise Server Compute Infrastructure Procurement |
| **Total Clauses** | 11 GFR 2017 compliant requirements |
| **Evaluating Bidders** | 3 distinct behavioral archetypes |

---

## 7. PASS Scenario

### Demonstration Vendor: Enterprise Tech Solutions Ltd (Bidder A)

- **Clause Code**: `TECH-001`
- **Requirement**: Dual-socket rack server configuration with a minimum of **64 processor cores per node**.
- **Bidder Evidence**: Technical Datasheet specifies AMD EPYC 9554 processor nodes with **64 physical cores** per node (Technical Specifications Brochure, Page 3).
- **Rule Verification**:
  $$\text{Evidence Cores } (64) \ge \text{Mandatory Cores } (64) \implies \mathbf{PASS}$$
- **Result**: **PASS** (Zero shortfall; complete technical compliance).

---

## 8. FAIL Scenario

### Demonstration Vendor: Legacy Hardware Trading Co (Bidder B)

- **Clause Code**: `FIN-001`
- **Requirement**: Minimum average annual turnover of **₹5.0 Crore** across the last 3 financial years.
- **Bidder Evidence**: Audited Balance Sheet extract reflects an average turnover of **₹2.1 Crore** (Financial Schedule Annexure, Page 7).
- **Rule Verification**:
  $$\text{Evidence Turnover } (₹2.1\text{ Cr}) < \text{Mandatory Turnover } (₹5.0\text{ Cr}) \implies \mathbf{FAIL}$$
- **Computed Shortfall**: **₹2.9 Crore deficit**.
- **Result**: **FAIL** with clear mathematical deficiency explanation for officer review.

---

## 9. REVIEW / Contradiction Scenario

### Demonstration Vendor: Apex System Integrators (Bidder C)

- **Clause Code**: `FIN-001`
- **Requirement**: Minimum average annual turnover of **₹5.0 Crore**.
- **Self-Declaration (Doc 1)**: Bidder claims **₹8.0 Crore** average annual turnover in General Self-Declaration (Page 2).
- **CA Certificate (Doc 2)**: Chartered Accountant Audit Certificate reveals actual average turnover of **₹3.65 Crore** (Page 4).
- **Detection**:
  $$\text{Claimed } (₹8.0\text{ Cr}) \ne \text{Certified } (₹3.65\text{ Cr})$$
- **Result**: **REVIEW (CONTRADICTION DETECTED)**. The system isolates the conflicting extracts and flags the item for officer investigation rather than silently accepting the higher self-declared value.

---

## 10. Evidence Drawer

Clicking any status badge in the Compliance Matrix opens the **Evidence Drawer**:

- **Verbatim Evidence Quote**: Exact quotation extracted from the submitted dossier.
- **Provenance Metadata**: Source filename, page number, and paragraph coordinates.
- **Extraction Provenance**: Indicates whether text was extracted via digital stream (`DIGITAL_TEXT`) or optical recognition (`OCR`).
- **Confidence Metric**: Confidence score computed from semantic retrieval affinity and rule verification.
- **Rule Details**: Exact arithmetic breakdown showing mandatory threshold, observed evidence value, and difference.

---

## 11. Human-in-the-Loop Adjudication

BidGuard AI enforces **Human-in-the-Loop (HITL)** governance:

1. **System Recommends**: Algorithms generate preliminary `PASS`, `FAIL`, or `REVIEW` indicators based on grounded evidence.
2. **Officer Assesses**: Procurement officers inspect citations, verify conflicting documents, and review statutory register statuses.
3. **Officer Adjudicates**: The officer can accept system recommendations or enter an explicit override (e.g., accepting an equivalent certificate or marking a clarification request).
4. **Audit Logging**: Every adjudication requires an officer justification remark, recorded with an immutable timestamp and user identifier.

---

## 12. Dashboard

The procurement workspace dashboard provides:

- **Active Tender Repository**: Visual cards for active, review, and completed procurement tenders.
- **Requirement Counters**: Instant summary of extracted technical, financial, and statutory clauses.
- **Bidder Status Indicators**: Total evaluated vendors and submission completion statuses.
- **Statutory Health Indicators**: Real-time operational availability status for the verification orchestrator.
- **Navigation Shortcuts**: Quick links to the interactive Mock Data Explorer and tender creation pipelines.

---

## 13. Technology Stack

| Layer | Component | Version / Description |
| :--- | :--- | :--- |
| **Frontend** | Next.js | 15.1 (App Router, Server & Client Components) |
| **Frontend** | React & TypeScript | React 18, TypeScript 5 (Strict Mode) |
| **Styling** | Tailwind CSS | Government-grade design tokens (GeM-inspired aesthetic) |
| **Icons** | Lucide React | Clean, standard visual indicators |
| **Backend API** | FastAPI | Python 3.12+ ASGI Web Framework |
| **Validation** | Pydantic | v2 strict input/output contract enforcement |
| **ORM & DB Layer**| SQLAlchemy & Alembic| Async database sessions (`asyncpg` / `aiosqlite`) |
| **Primary Database**| PostgreSQL 16 | Relational storage with `pgvector` extension |
| **Local Fallback DB**| SQLite | Zero-configuration local database (`gem_compliance.db`) |
| **AI LLM Inference**| NVIDIA NIM | `openai/gpt-oss-20b` via OpenAI-compatible endpoint |
| **Embeddings** | NVIDIA Nemotron | `nvidia/nemotron-3-embed-1b` (2048 dimensions) |
| **Document Engine**| PyMuPDF (fitz) | High-speed PDF text and coordinate extraction |
| **OCR Fallback** | Tesseract OCR | Image-based text recovery for scanned annexures |
| **Vector Store** | ChromaDB | Local vector indexing and semantic similarity |
| **Rule Engine** | Deterministic Python | Arithmetic, threshold, and temporal comparison logic |
| **Containerization**| Docker & Docker Compose | Multi-container orchestration |

---

## 14. Why This Architecture

| Traditional Black-Box LLM | BidGuard AI Hybrid Architecture |
| :--- | :--- |
| Generates unstructured prose answers without references | Outputs structured Pydantic schemas with page-level citations |
| Prone to arithmetic and numeric reasoning errors | Delegates all numerical and threshold logic to deterministic Python rules |
| Unpredictable hallucination on negative or missing facts | Explicitly tags absence as `MISSING_EVIDENCE` or `REVIEW` |
| Black-box automated decision without transparency | Evidence-first decision support; final authority remains with the officer |
| Relies solely on self-submitted vendor text | Cross-checks claims against 11 independent statutory registries |

---

## 15. Safety and Trust Model

BidGuard AI adheres to strict procurement safety principles:

1. **Zero Silent Automation**: Disqualification and bid rejection are never automated.
2. **Strict Verifiability**: Every compliance assertion must be supported by an auditable text quotation and page reference.
3. **No Inference Over Extrapolation**: When data is ambiguous, the system defaults to `REVIEW`, preventing false negatives or false positives.
4. **Data Isolation**: Multi-tenant database schemas isolate tender data; no vendor dossier data is sent to public training corpora.
5. **PII & Sensitive Data Redaction**: The statutory adapter layer automatically redacts sensitive credentials and passwords before persistence.

---

## 16. Current PoC Status

- **Evaluation Prototype**: Fully functional Proof-of-Concept ready for SIH 2026 jury evaluation.
- **Verified Core Flow**: End-to-end workflow verified from tender ingestion to compliance matrix and statutory cross-verification.
- **Synthetic Registries**: 11 simulated statutory adapters populated with realistic synthetic records modeled after official schema standards.
- **High-Fidelity UI**: Clean, government-grade user experience built with Next.js 15.

---

## 17. Local Development

### Prerequisites
- Python 3.11 or 3.12
- Node.js 20+ and npm
- Git

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI backend server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup

```bash
# Open a new terminal and navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
```

### 3. Golden Demo Seeding

To populate the golden demo tender, 11 requirements, 3 bidders, and synthetic registers:

```bash
# From the backend directory (with virtual environment active):
cd backend
python seed_golden_demo.py
```

### 4. Access URLs
- **Web Application**: `http://localhost:3000`
- **Interactive Swagger API Docs**: `http://localhost:8000/docs`
- **Alternative Redoc API Documentation**: `http://localhost:8000/redoc`

---

## 18. Docker Deployment

To launch the complete multi-container environment (PostgreSQL with pgvector, Backend, and Frontend):

```bash
# From repository root
docker compose up --build
```

Services exposed:
- **Frontend Dashboard**: `http://localhost:3000`
- **Backend API**: `http://localhost:8000`
- **PostgreSQL**: `localhost:5432`

---

## 19. Testing & Verification

The platform includes a comprehensive automated test suite covering unit contracts, deterministic rules, multi-source statutory adapters, and full procurement lifecycle workflows:

```bash
# Run backend unit and integration tests
cd backend
pytest -v

# Run end-to-end workflow tests
pytest tests/e2e -v

# Validate frontend production build
cd frontend
npm run build
```

### Repository Verification Results

| Test Suite | Scope | Status |
| :--- | :--- | :--- |
| **E2E Integration** | Full procurement lifecycle evaluation | **6/6 PASSED** |
| **Backend Integration** | API contracts, rule verification, adapters | **25/25 PASSED** |
| **Total Automated Tests** | Repository test coverage | **31/31 PASSED** |
| **Frontend Production Build** | Next.js TypeScript & route compilation | **CLEAN (0 Errors)** |

*(Note: These are repository verification results confirming codebase health, not AI accuracy claims.)*

---

## 20. Project Structure

```
.
├── .github/                      # Issue templates, PR checklists, and CI workflows
├── ai-engine/                    # Extraction models, ChromaDB RAG, and semantic matching
├── backend/                      # FastAPI application backend
│   ├── app/
│   │   ├── api/                  # REST API v1 endpoints (tenders, bidders, evaluations, statutory)
│   │   ├── core/                 # Config, database engine, SQLite fallback guard
│   │   ├── models/               # SQLAlchemy ORM models (Tender, Bidder, Evaluation, Statutory)
│   │   ├── schemas/              # Pydantic v2 schemas and validation contracts
│   │   └── services/             # Core engines: rule engine, extractor, orchestrator, adapters
│   ├── mock_data/                # Synthetic statutory records (GSTN, Udyam, MCA, PAN, etc.)
│   ├── seed_golden_demo.py       # Golden demonstration seeder script
│   └── requirements.txt          # Python backend dependencies
├── data/                         # Public sample documents and synthetic statutory datasets
│   ├── sample/                   # Anonymized sample tender and bidder PDF documents
│   ├── synthetic/                # Schema definitions for mock statutory fixtures
│   └── README.md                 # Dataset provenance disclosure
├── docker/                       # Dockerfiles and production Compose configurations
├── docs/                         # Architecture, API specifications, and decisions (ADRs)
│   ├── api/                      # REST API endpoint documentation
│   ├── architecture/             # System architecture and data flow diagrams
│   ├── decisions/                # Architectural Decision Records (ADRs)
│   ├── demo/                     # SIH jury presentation flow guide
│   └── team/                     # Team roles and workflow documents
├── frontend/                     # Next.js 15 React application
│   ├── public/                   # Static branding assets
│   ├── src/
│   │   ├── app/                  # App Router pages (tenders, clauses, bidders, compliance, mock-data)
│   │   ├── components/           # UI components (ComplianceTable, EvidenceDrawer, StatutoryPanel)
│   │   └── lib/                  # API client, TypeScript definitions, utility helpers
│   ├── package.json              # Node.js dependencies
│   └── tailwind.config.ts        # Design tokens and theme configuration
├── scripts/                      # Verification and developer utility scripts
├── tests/                        # End-to-end integration test suites
├── .env.example                  # Environment configuration template
├── .env.production.example       # Production environment template
├── .gitignore                    # Git exclusion rules
├── docker-compose.yml            # Container orchestration specification
├── CODE_OF_CONDUCT.md            # Contributor Covenant v2.1
├── CONTRIBUTING.md               # Contribution workflow and guidelines
├── LICENSE                       # Apache License 2.0
└── SECURITY.md                   # Vulnerability reporting and security practices
```

---

## 21. UI/UX Design System

The frontend is designed with a **government-grade visual identity** inspired by national portal design standards (GeM, Digital India):

- **Color Palette**: Curated deep navy (`#0F2D5B`), royal blue (`#1F4E9E`), neutral background (`#F5F8FB`), clean card surface (`#FFFFFF`), and refined slate borders (`#E9EEF5`).
- **Semantic Status Badges**:
  - `PASS`: Subtle emerald green (`bg-emerald-50 text-emerald-800 border-emerald-200`)
  - `FAIL`: High-contrast crimson (`bg-rose-50 text-rose-800 border-rose-200`)
  - `REVIEW`: Cautionary amber (`bg-amber-50 text-amber-800 border-amber-200`)
- **Visual Evidence Distinction**: Digital PDF text vs OCR-scanned text are demarcated with distinct provenance indicators.
- **Responsive Layout**: Accessible across desktop workstations and mobile viewport displays.

---

## 22. Data and Limitations

### Data Transparency
- All demonstration tender notices are derived from anonymized public-domain procurement schedules.
- All bidder profiles and financial statements are synthetic constructs created solely to demonstrate deterministic rule verification.
- Mock statutory databases contain 5,000 synthetic records structured in accordance with published schema specifications.

### Technical Limitations
- **Synthetic Statutory Environment**: Direct production integration requires official MoU and authenticated gateway credentials from respective government authorities.
- **Complex Scanned Tables**: Badly skewed or low-resolution physical document scans may produce degraded OCR output, which the platform systematically routes to `REVIEW` status for human verification.
- **Procurement Scope**: Current rules are optimized for Goods and Services tenders under GFR 2017; complex civil works contracts with CPWD schedules may require additional taxonomy configurations.

---

## 23. Future Scope

- **Production GeM API Gateway**: Direct, authenticated handshake with GeM 2.0 developer APIs once credentials are sanctioned.
- **Multilingual Tender Parsing**: Support for tenders and annexures published in regional Indian languages (Hindi, Marathi, Tamil, Telugu, Bengali) via Indic-LLM integrations.
- **Cryptographic Audit Notarization**: Anchoring finalized procurement evaluation reports on a permissioned Hyperledger Fabric ledger or the National Blockchain Framework.
- **Market Cartelization Intelligence**: Advanced cross-tender network analysis to identify bid-rigging rings and collusive bidding patterns.

---

## 24. Research Basis

BidGuard AI's architecture is informed by:

- **General Financial Rules (GFR 2017)**: Standards for public procurement, financial evaluation, and vendor eligibility.
- **Manual for Procurement of Goods (Ministry of Finance, GoI)**: Strict guidelines on mandatory technical compliance and fairness in technical bid evaluation.
- **Explainable AI (XAI) in Public Administration**: Research emphasizing that algorithmic systems in government decision-making must be transparent, traceable, and inspectable.
- **Deterministic-Semantic Hybrid Systems**: Separation of neural linguistic interpretation (LLMs) from rule-based mathematical execution to achieve zero hallucination in critical processes.

---

## 25. Team

**Team Name**: Team BidGuard (SIH26100)

| Member | Role | Core Focus Areas |
| :--- | :--- | :--- |
| **Harshil Somisetty** | **Team Lead & Lead AIML** | Hybrid architecture, RAG, extraction pipelines, deterministic rule engine, system integration |
| **Karthik** | **Cloud & DevOps Lead** | Docker containerization, CI/CD pipelines, cloud deployment, network security |
| **Kethana** | **Full Stack (Frontend Lead)** | Next.js architecture, officer cockpit, interactive evidence drawer, compliance matrix |
| **Kesav** | **Full Stack (Backend Lead)** | FastAPI backend services, database models, REST API endpoints, audit report generation |
| **Jahnavi** | **Cloud & Data Pipeline** | Synthetic statutory datasets, ingestion pipelines, database fixtures, testing automation |
| **Rohitha** | **QA & AIML Support** | End-to-end test suites, prompt benchmarking, edge-case evaluation, documentation |

---

## 26. Responsible Use

- BidGuard AI is an **officer-assistive tool**, not a replacement for statutory procurement committees.
- The platform should never be configured to automatically award contracts or issue disqualifications without human review.
- Procurement officers must independently confirm critical findings using the direct document citations provided.

---

## 27. Contributing

We welcome contributions following standard open-source practices:
1. Review the [Code of Conduct](CODE_OF_CONDUCT.md) and [Contributing Guidelines](CONTRIBUTING.md).
2. Fork the repository and create a feature branch (`git checkout -b feature/improvement`).
3. Commit your changes following conventional commits (`git commit -m 'feat: add enhanced clause validation'`).
4. Ensure all automated tests pass (`pytest` and `npm run build`).
5. Open a Pull Request referencing the relevant issue.

---

## 28. Security Policy

- **Reporting Vulnerabilities**: See [SECURITY.md](SECURITY.md) for vulnerability disclosure protocols.
- **Secret Management**: Never commit credentials, private keys, or API tokens. Use `.env` files matching the templates in `.env.example`.
- **Payload Sanitization**: All statutory verification responses automatically redact sensitive key patterns (`password`, `token`, `secret`, `api_key`).

---

## 29. SIH 2026 Information

- **Competition**: Smart India Hackathon 2026 (Software Edition)
- **Problem Statement ID**: `SIH26100`
- **Title**: AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement
- **Category**: Software
- **Theme**: Smart Automation

---

## 30. Project Links

- **Source Code Repository**: [https://github.com/harshilsetty/sih26100-bidguard](https://github.com/harshilsetty/sih26100-bidguard)
- **Smart India Hackathon Official Portal**: [https://www.sih.gov.in/](https://www.sih.gov.in/)
- **Government e-Marketplace (GeM)**: [https://gem.gov.in/](https://gem.gov.in/)
- **Architecture Documentation**: [`docs/architecture/`](docs/architecture/)
- **API Documentation**: [`docs/api/`](docs/api/)
