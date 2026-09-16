# Backend REST API Specification — BidGuard (SIH26100)

**Version**: 1.0.0 (SIH MVP Frozen Specification)  
**Base URL**: `http://localhost:8000/api/v1`  
**Content-Type**: `application/json` (unless multipart upload)  

---

## 1. Overview of Minimum Required Endpoints

| Method | Endpoint | Description | Primary Owner |
|---|---|---|---|
| `POST` | `/tender/upload` | Upload & extract clauses from tender specification PDF | Kesav + Harshil |
| `POST` | `/bidder/upload` | Upload bidder technical & financial submission PDFs | Kesav + Kethana |
| `POST` | `/verification/start` | Trigger compliance matching pipeline for a bidder | Kesav + Harshil |
| `GET` | `/verification/{verification_id}` | Query verification job status, summary & risk score | Kesav |
| `GET` | `/requirements/{verification_id}` | Retrieve extracted requirements for the verified tender | Kesav |
| `GET` | `/evidence/{verification_id}` | Retrieve extracted evidence chunks with page citations | Kesav |
| `GET` | `/report/{verification_id}` | Retrieve procurement officer decision report data | Kesav |

---

## 2. Detailed Endpoint Contracts

### 2.1 `POST /tender/upload`
Uploads a tender notice or RFP document (PDF). PyMuPDF parses the document into text and extracts qualification criteria.

- **Request Format**: `multipart/form-data`
- **Form Fields**:
  - `file`: `UploadFile` (Required, PDF only, Max 25 MB)
  - `tender_number`: `string` (Required, e.g. `"GEM/2026/B/891241"`)
  - `title`: `string` (Required, e.g. `"Procurement of Server Hardware"`)
  - `estimated_value_inr`: `float` (Optional, in INR Lakhs)
- **Successful Response**: `201 Created`
```json
{
  "tender_id": "tnd-8f92a10b",
  "tender_number": "GEM/2026/B/891241",
  "title": "Procurement of Server Hardware",
  "total_pages": 14,
  "extracted_requirements_count": 8,
  "status": "PARSED",
  "created_at": "2026-09-15T10:30:00Z"
}
```
- **Error Responses**:
  - `400 Bad Request`: `{"error": "INVALID_FILE_TYPE", "message": "Only PDF documents are allowed."}`
  - `413 Payload Too Large`: `{"error": "FILE_TOO_LARGE", "message": "File exceeds maximum size of 25 MB."}`
  - `422 Unprocessable Entity`: Missing required form fields.

---

### 2.2 `POST /bidder/upload`
Uploads a bidder technical proposal, balance sheet, or statutory certificate PDF.

- **Request Format**: `multipart/form-data`
- **Form Fields**:
  - `file`: `UploadFile` (Required, PDF only, Max 25 MB)
  - `tender_id`: `string` (Required, UUID of the tender)
  - `bidder_name`: `string` (Required, e.g. `"Apex Cloud Solutions Pvt Ltd"`)
  - `pan`: `string` (Required, e.g. `"AAACA1234A"`)
  - `gstin`: `string` (Optional, e.g. `"07AAACA1234A1Z5"`)
  - `udyam`: `string` (Optional, e.g. `"UDYAM-DL-01-0012345"`)
- **Successful Response**: `201 Created`
```json
{
  "bidder_id": "bdr-7c18e90a",
  "tender_id": "tnd-8f92a10b",
  "bidder_name": "Apex Cloud Solutions Pvt Ltd",
  "document_id": "doc-55a1e2",
  "document_name": "apex_technical_submission.pdf",
  "total_pages": 22,
  "status": "UPLOADED",
  "created_at": "2026-09-15T10:35:00Z"
}
```
- **Error Responses**:
  - `400 Bad Request`: Invalid PAN format or unsupported document type.
  - `404 Not Found`: `{"error": "TENDER_NOT_FOUND", "message": "Tender tnd-8f92a10b does not exist."}`

---

### 2.3 `POST /verification/start`
Asynchronously queues or triggers the compliance evaluation pipeline for a bidder against tender requirements.

- **Request Format**: `application/json`
- **Request Body**:
```json
{
  "tender_id": "tnd-8f92a10b",
  "bidder_id": "bdr-7c18e90a"
}
```
- **Successful Response**: `202 Accepted`
```json
{
  "verification_id": "ver-990a14de",
  "status": "PENDING",
  "tender_id": "tnd-8f92a10b",
  "bidder_id": "bdr-7c18e90a",
  "created_at": "2026-09-15T10:36:00Z"
}
```
- **Error Responses**:
  - `404 Not Found`: Tender or Bidder ID does not exist.
  - `409 Conflict`: Verification already in progress for this bidder.

---

### 2.4 `GET /verification/{verification_id}`
Fetches the current execution status and aggregated compliance scorecard.

- **Path Parameter**: `verification_id` (`string`, required)
- **Successful Response**: `200 OK`
```json
{
  "verification_id": "ver-990a14de",
  "tender_id": "tnd-8f92a10b",
  "bidder_id": "bdr-7c18e90a",
  "status": "COMPLETED",
  "compliance_score": 87.5,
  "summary": {
    "total_clauses": 8,
    "passed": 6,
    "failed": 1,
    "review": 1
  },
  "debarment_check": {
    "is_debarred": false,
    "checked_against": "Central Debarment Registry"
  },
  "completed_at": "2026-09-15T10:37:12Z"
}
```
- **Error Responses**:
  - `404 Not Found`: `{"error": "NOT_FOUND", "message": "Verification job not found."}`

---

### 2.5 `GET /requirements/{verification_id}`
Retrieves all qualification criteria extracted from the tender associated with this verification.

- **Path Parameter**: `verification_id` (`string`, required)
- **Successful Response**: `200 OK`
```json
{
  "verification_id": "ver-990a14de",
  "tender_id": "tnd-8f92a10b",
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "category": "financial",
      "clause_text": "Minimum annual turnover of INR 5 crore in last 3 years.",
      "page_number": 4,
      "is_mandatory": true
    },
    {
      "requirement_id": "REQ-002",
      "category": "technical",
      "clause_text": "Bidder must possess past experience of completing 3 similar supply orders.",
      "page_number": 5,
      "is_mandatory": true
    }
  ]
}
```

---

### 2.6 `GET /evidence/{verification_id}`
Retrieves all extracted bidder evidence snippets associated with this verification.

- **Path Parameter**: `verification_id` (`string`, required)
- **Successful Response**: `200 OK`
```json
{
  "verification_id": "ver-990a14de",
  "bidder_id": "bdr-7c18e90a",
  "evidence_items": [
    {
      "evidence_id": "EVD-001",
      "document": "audited_financials_2023.pdf",
      "page": 7,
      "text": "Average annual turnover stands at INR 3.2 crore as certified by CA.",
      "extracted_entities": {
        "turnover_inr_crore": 3.2
      }
    }
  ]
}
```

---

### 2.7 `GET /report/{verification_id}`
Retrieves the comprehensive procurement decision-support report for the officer dashboard.

- **Path Parameter**: `verification_id` (`string`, required)
- **Successful Response**: `200 OK`
```json
{
  "verification_id": "ver-990a14de",
  "tender_number": "GEM/2026/B/891241",
  "bidder_name": "Apex Cloud Solutions Pvt Ltd",
  "overall_compliance_score": 87.5,
  "preliminary_status": "FLAGGED_FOR_OFFICER_REVIEW",
  "compliance_results": [
    {
      "requirement_id": "REQ-001",
      "requirement": "Minimum annual turnover of INR 5 crore in last 3 years.",
      "requirement_type": "financial",
      "status": "FAIL",
      "evidence": [
        {
          "text": "Average annual turnover stands at INR 3.2 crore as certified by CA.",
          "document": "audited_financials_2023.pdf",
          "page": 7
        }
      ],
      "confidence": 1.0,
      "reason": "Turnover of ₹3.2 crore is below mandatory threshold of ₹5.0 crore (Deterministic rule check).",
      "requires_human_review": false,
      "contradiction_detected": false
    }
  ],
  "download_pdf_url": "/api/v1/report/ver-990a14de/pdf",
  "generated_at": "2026-09-15T10:38:00Z"
}
```
