# Database Schema Contract — BidGuard (SIH26100)

**Engine**: PostgreSQL 16 (with `pgvector` extension)  
**ORM**: SQLAlchemy 2.0 (asyncpg)  
**Location**: `backend/app/models/`  

---

## 1. Entity-Relationship Model

```
┌──────────────┐             1:N             ┌─────────────────────┐
│    Tender    │────────────────────────────>│     Requirement     │
└──────────────┘                             └─────────────────────┘
       │ 1                                              │ 1
       │                                                │
       │ 1:N                                            │ 1:N
       ▼                                                ▼
┌──────────────┐      N:1    ┌──────────────┐1:N   ┌─────────────────────┐
│ Verification │────────────>│    Bidder    │─────>│  ComplianceResult   │
└──────────────┘             └──────────────┘      └─────────────────────┘
       │ 1                          │ 1                     ▲
       │                            │                       │
       │ 1:N                        │ 1:N                   │ (links evidence)
       ▼                            ▼                       │
┌──────────────┐             ┌──────────────┐               │
│   Document   │             │   Evidence   │───────────────┘
└──────────────┘             └──────────────┘
```

---

## 2. Core Entities & Field Specifications

### 2.1 `Tender`
Represents an official Notice Inviting Tender (NIT) or RFP document.
- `id`: `UUID` (Primary Key)
- `tender_number`: `VARCHAR(100)` (Unique, Indexed, e.g. `"GEM/2026/B/891241"`)
- `title`: `VARCHAR(255)` (Title of procurement)
- `estimated_value_inr`: `NUMERIC(15, 2)` (Optional, in INR Lakhs)
- `status`: `VARCHAR(50)` (`"CREATED"`, `"PARSED"`, `"COMPLETED"`)
- `created_at`: `TIMESTAMPTZ` (Default `NOW()`)

---

### 2.2 `Requirement`
Represents a discrete qualification clause parsed from a tender specification.
- `id`: `UUID` (Primary Key)
- `tender_id`: `UUID` (Foreign Key ➔ `Tender.id`, Indexed)
- `requirement_code`: `VARCHAR(50)` (e.g. `"REQ-001"`)
- `category`: `VARCHAR(50)` (`"financial"`, `"technical"`, `"statutory"`, `"experience"`)
- `clause_text`: `TEXT` (Full text of the requirement)
- `source_clause`: `VARCHAR(100)` (e.g. `"Section 4.1.2"`)
- `page_number`: `INTEGER` (1-indexed source PDF page)
- `is_mandatory`: `BOOLEAN` (Default `TRUE`)
- `created_at`: `TIMESTAMPTZ`

---

### 2.3 `Bidder`
Represents an enterprise or vendor participating in the tender.
- `id`: `UUID` (Primary Key)
- `name`: `VARCHAR(255)` (Legal registered name)
- `pan`: `VARCHAR(10)` (Indexed, 10-char PAN)
- `gstin`: `VARCHAR(15)` (Optional, 15-char GSTIN)
- `udyam_registration`: `VARCHAR(30)` (Optional, Udyam number)
- `created_at`: `TIMESTAMPTZ`

---

### 2.4 `Document`
Tracks raw files uploaded to the platform (stored securely in `/uploads`).
- `id`: `UUID` (Primary Key)
- `tender_id`: `UUID` (Optional Foreign Key ➔ `Tender.id`)
- `bidder_id`: `UUID` (Optional Foreign Key ➔ `Bidder.id`)
- `verification_id`: `UUID` (Optional Foreign Key ➔ `Verification.id`)
- `filename`: `VARCHAR(255)` (Original filename)
- `file_path`: `VARCHAR(512)` (Local disk / object store path)
- `file_hash`: `VARCHAR(64)` (SHA-256 integrity hash)
- `total_pages`: `INTEGER`
- `created_at`: `TIMESTAMPTZ`

---

### 2.5 `Evidence`
Represents candidate factual statements extracted from bidder documents.
- `id`: `UUID` (Primary Key)
- `bidder_id`: `UUID` (Foreign Key ➔ `Bidder.id`, Indexed)
- `document_id`: `UUID` (Foreign Key ➔ `Document.id`, Indexed)
- `page_number`: `INTEGER` (1-indexed page where evidence appears)
- `extracted_text`: `TEXT` (Snippet or paragraph)
- `numeric_values`: `JSONB` (Extracted turnover, years, counts)
- `created_at`: `TIMESTAMPTZ`

---

### 2.6 `Verification`
Represents an end-to-end evaluation session matching a bidder against a tender.
- `id`: `UUID` (Primary Key)
- `tender_id`: `UUID` (Foreign Key ➔ `Tender.id`, Indexed)
- `bidder_id`: `UUID` (Foreign Key ➔ `Bidder.id`, Indexed)
- `status`: `VARCHAR(50)` (`"PENDING"`, `"PROCESSING"`, `"COMPLETED"`, `"FAILED"`)
- `compliance_score`: `NUMERIC(5, 2)` (0.0 to 100.0)
- `debarment_status`: `BOOLEAN` (Default `FALSE`)
- `officer_remarks`: `TEXT` (Human officer input)
- `completed_at`: `TIMESTAMPTZ`
- `created_at`: `TIMESTAMPTZ`

---

### 2.7 `ComplianceResult` (The Explainability Core)
Stores the evaluated verdict for each requirement. Retains full chain-of-custody metadata for human review.
- `id`: `UUID` (Primary Key)
- `verification_id`: `UUID` (Foreign Key ➔ `Verification.id`, Indexed)
- `requirement_id`: `UUID` (Foreign Key ➔ `Requirement.id`, Indexed)
- `bidder_id`: `UUID` (Foreign Key ➔ `Bidder.id`, Indexed)
- `status`: `VARCHAR(20)` (`"PASS"`, `"FAIL"`, `"REVIEW"`, Indexed)
- `confidence`: `NUMERIC(4, 3)` (0.000 to 1.000)
- `evidence_text`: `TEXT` (Primary supporting quote)
- `source_document`: `VARCHAR(255)` (Document filename)
- `source_page`: `INTEGER` (1-indexed page number)
- `reason`: `TEXT` (Grounded reason for assignment)
- `review_flag`: `BOOLEAN` (Default `FALSE`, indicates officer attention needed)
- `contradiction_flag`: `BOOLEAN` (Default `FALSE`, indicates conflicting claims)
- `deterministic_override`: `BOOLEAN` (Default `FALSE`, indicates code rule overrode model)
- `created_at`: `TIMESTAMPTZ`
