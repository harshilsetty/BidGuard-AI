# Data Strategy & Datasets — BidGuard (SIH26100)

This directory documents all datasets, sample procurement documents, and synthetic data generators used by BidGuard for Smart India Hackathon 2026.

---

## 1. Transparency & Statutory Disclosure

> [!IMPORTANT]
> **SIH Integrity Statement on Government Data & APIs**:
> - BidGuard does **NOT** possess live production access or credentials to official government backends (GeM, GSTN, Udyam, EPFO, ESIC, DPIIT, NSIC, or DigiLocker production APIs).
> - For our SIH MVP prototype, all statutory verification records and databases are **rigorously modeled synthetic mock datasets** based on published official schemas and publicly structured procurement formats.
> - **All mock data is explicitly tagged and displayed as synthetic** in both our internal database models and officer dashboard UI.
> - Real procurement decisions in government portals require live integration; our platform demonstrates the technical architecture, adapters, and officer decision-support workflow.

---

## 2. Directory Layout

```
data/
├── sample/
│   ├── README.md               # Explanation of public sample bid documents & tender formats
│   └── .gitkeep
├── synthetic/
│   ├── README.md               # Schemas and generation logic for synthetic statutory data
│   └── .gitkeep
└── README.md                   # This document
```

---

## 3. Data Categories

### A. Sample Documents (`data/sample/`)
Contains publicly available sample bid documents, RFP extracts, and synthetic bidder certificates:
- Sample General Financial Rules (GFR) compliant tender notices.
- Sample technical specification schedules and eligibility criteria.
- Synthetic bidder submission packages (work completion certificates, financial solvency letters, declarations).

### B. Synthetic Statutory Records (`data/synthetic/`)
Modeled according to official Government of India statutory formats:

| Registry | Modeled Identifier Schema | Test Dataset Scale | Purpose in MVP |
|---|---|---|---|
| **GSTN** | `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$` | 1,000 synthetic records | Active tax filing status, business entity name matching |
| **Udyam / MSME** | `^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$` | 1,000 synthetic records | MSME exemption eligibility (turnover/experience relaxation) |
| **DPIIT / Startup** | `^DPIIT-[0-9]{5,6}$` | 1,000 synthetic records | Startup India eligibility & prior experience waivers |
| **EPFO** | `^[A-Z]{2}[A-Z]{3}[0-9]{7}[0-9]{3}$` | 1,000 synthetic records | Provident fund wage compliance & active establishment check |
| **ESIC** | `^[0-9]{17}$` | 1,000 synthetic records | Employee State Insurance contribution verification |
| **NSIC / SPRS** | `^NSIC-[A-Z]{2,4}-[0-9]{4,6}$` | 1,000 synthetic records | Single Point Registration Scheme fee exemption & validity |
| **DigiLocker** | Mock Requester / Doc URI Hash | 1,000 synthetic records | Document provenance, SHA-256 hash validation, issuer authenticity |
| **Debarment DB** | PAN / CIN / Entity Name | 500 synthetic records | Central/State debarment lists with temporal order windows |

---

## 4. Synthetic Data Generation & Seeding

All synthetic records are deterministically seeded into PostgreSQL using our automated seeder:
```bash
# Seed or reset local synthetic datasets
python -m backend.app.services.mock_seeder
```
Seeding is idempotent: running the command guarantees identical, reproducible mock entities across all developer environments.
