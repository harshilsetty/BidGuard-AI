# AI Engine → Backend Contract Specification

**Document Version**: 1.0.0 (Frozen for SIH MVP)  
**Primary AI Provider**: Google Gemini API (`gemini-1.5-flash`)  
**Target Module**: `ai-engine/` ➔ `backend/app/services/`  

---

## 1. Core Principle: Zero Free-Form Text

The AI Engine must **never** return unformatted, conversational, or arbitrary text responses to the backend. Every inference query—whether executed via Google Gemini API or local RAG retrieval—must return structured JSON strictly validated against Pydantic models.

If an LLM invocation fails or returns malformed JSON, the backend's error-handling wrapper must catch the validation error, log the incident, and gracefully fall back to:
```json
{
  "requirement_id": "REQ-ERR",
  "requirement": "Unprocessed Clause",
  "requirement_type": "unknown",
  "evidence": [],
  "status": "REVIEW",
  "confidence": 0.0,
  "reason": "AI extraction or schema validation encountered an error. Routed to officer for manual verification.",
  "requires_human_review": true,
  "contradiction_detected": false
}
```

---

## 2. Canonical JSON Output Schema

```json
{
  "requirement_id": "REQ-001",
  "requirement": "Minimum annual turnover of INR 5 crore in the last 3 financial years",
  "requirement_type": "financial",
  "evidence": [
    {
      "text": "Average annual turnover is INR 3.2 crore as certified by Chartered Accountant.",
      "document": "financial_statement_2023.pdf",
      "page": 7
    }
  ],
  "status": "FAIL",
  "confidence": 0.94,
  "reason": "Bidder turnover of INR 3.2 crore is below the mandatory minimum threshold of INR 5.0 crore.",
  "requires_human_review": false,
  "contradiction_detected": false
}
```

---

## 3. Allowed Status Enum

The `status` field must strictly be one of:

| Status | Definition | Deterministic Rule / Trigger |
|---|---|---|
| **`PASS`** | The bidder's submitted evidence conclusively and unambiguously satisfies the requirement. | Numeric/date threshold satisfied AND supporting evidence verified. |
| **`FAIL`** | The bidder's submitted evidence definitively violates a mandatory requirement. | Turnover below threshold, experience insufficient, or active debarment order found. |
| **`REVIEW`** | Ambiguity detected, evidence is missing, or contradictory claims exist across documents. | Contradiction detected across annexures, low OCR confidence, or missing certificate. |

---

## 4. Strict Separation: AI vs. Deterministic Business Rules

To prevent hallucinations and guarantee legally defensible procurement decisions under General Financial Rules (GFR 2017), responsibilities are strictly decoupled:

```
Unstructured PDFs
       │
       ▼
┌────────────────────────────────────────────────────────┐
│               AI ENGINE (Google Gemini)                │
│  - Extracts clause text & requirement types            │
│  - Extracts candidate evidence quotes & page numbers   │
│  - Understands semantic meaning of specifications      │
│  - Performs dense vector retrieval (ChromaDB)          │
│  - Flags potential contradictions across documents     │
└──────────────────────────────────┬─────────────────────┘
                                   │ Raw Facts & Extracted Quantities
                                   ▼
┌────────────────────────────────────────────────────────┐
│               DETERMINISTIC RULE ENGINE                │
│  - Evaluates numeric comparisons (3.2 < 5.0)           │
│  - Evaluates date windows (e.g. valid as of tender)    │
│  - Applies statutory exemption logic (MSME / DPIIT)    │
│  - Overrides model predictions with 100% certainty     │
└──────────────────────────────────┬─────────────────────┘
                                   │ Normalized Compliance Results
                                   ▼
┌────────────────────────────────────────────────────────┐
│             PROCUREMENT OFFICER DASHBOARD              │
│  - Human-in-the-loop review of PASS / FAIL / REVIEW    │
│  - Interactive evidence inspection on exact PDF page   │
│  - Final, legally binding qualification decision       │
└────────────────────────────────────────────────────────┘
```

### Concrete Example of Separation:
1. **Tender Requirement**: *"Bidder must possess minimum annual turnover of INR 5.0 crore."*
2. **Bidder Evidence Document**: *"The average audited turnover stands at INR 3.2 crore."*
3. **AI Layer Action**:
   - Extracts `required_turnover = 5.0`
   - Extracts `presented_turnover = 3.2`
   - Extracts `source_page = 7`, `document = "balance_sheet.pdf"`
4. **Deterministic Rule Engine Action**:
   - Evaluates: `3.2 < 5.0`
   - Status: **`FAIL`** (Deterministic code override, not LLM guess)
   - Reason: *"Turnover of ₹3.2 crore is below mandatory threshold of ₹5.0 crore."*

---

## 5. Pydantic Contract Implementation (`ai-engine/schemas.py`)

```python
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"

class EvidenceItem(BaseModel):
    text: str = Field(..., description="Exact textual quote from bidder submission")
    document: str = Field(..., description="Filename of source PDF")
    page: int = Field(..., ge=1, description="1-indexed page number")

class AIComplianceEvaluation(BaseModel):
    requirement_id: str = Field(..., description="Identifier e.g. REQ-001")
    requirement: str = Field(..., description="Tender qualification requirement text")
    requirement_type: str = Field(..., description="financial | technical | statutory | experience | legal")
    evidence: List[EvidenceItem] = Field(default_factory=list)
    status: ComplianceStatus = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=5)
    requires_human_review: bool = Field(default=False)
    contradiction_detected: bool = Field(default=False)
    deterministic_override: bool = Field(default=False)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

---

## 6. Contradiction Detection Contract

When a bidder makes contradictory claims across multiple documents, the AI Engine must flag `contradiction_detected: true`, force status to **`REVIEW`**, and populate `evidence` with snippets from both conflicting documents:

```json
{
  "requirement_id": "REQ-004",
  "requirement": "Bidder must possess at least 5 years of operating experience.",
  "requirement_type": "experience",
  "evidence": [
    {
      "text": "Apex Corp has over 6 years of industry experience since inception.",
      "document": "technical_proposal.pdf",
      "page": 2
    },
    {
      "text": "Certificate of Incorporation issued on 14th August 2023.",
      "document": "incorporation_cert.pdf",
      "page": 1
    }
  ],
  "status": "REVIEW",
  "confidence": 0.88,
  "reason": "Contradictory evidence detected: Technical proposal claims 6 years operating history, but Certificate of Incorporation proves incorporation in 2023 (less than 3 years active).",
  "requires_human_review": true,
  "contradiction_detected": true
}
```
