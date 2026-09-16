# Frontend Integration Contract — BidGuard (SIH26100)

**Framework**: Next.js 15 (App Router) + TypeScript + Tailwind CSS  
**Target Module**: `frontend/src/` consuming `backend/app/api/v1/`  
**Rule of Separation**: The frontend is strictly a presentation and interaction layer. It **must never perform AI inference, parsing, or compliance evaluation** directly. All verdicts, scores, and extractions are consumed from backend REST endpoints.

---

## 1. Required UI Flow & States

The web application guides the procurement officer through 8 discrete operational phases:

```
[1. Tender Upload] ➔ [2. Bidder Upload] ➔ [3. Start Verification] ➔ [4. Processing State]
                                                                            │
[8. Audit Report]  <─ [7. Risk / Score]  <─ [6. Evidence Viewer]   <─ [5. Compliance Dashboard]
```

### State 1: Tender Upload (`/tenders/new`)
- **Inputs**: Tender PDF file picker, tender title, tender number.
- **Action**: Calls `POST /api/v1/tender/upload`.
- **UI State**: Shows upload progress bar, displays count of extracted requirements upon completion.

### State 2: Bidder Document Upload (`/tenders/[id]/bidders`)
- **Inputs**: Multiple file uploader (technical bid, financial balance sheet, certificates), bidder legal name, PAN.
- **Action**: Calls `POST /api/v1/bidder/upload`.
- **UI State**: Lists uploaded documents with page count and SHA-256 confirmation badges.

### State 3 & 4: Start Verification & Processing State
- **Trigger**: Officer clicks `"Run Compliance Verification"`.
- **Action**: Calls `POST /api/v1/verification/start`.
- **UI State**: Renders active processing spinner with progress steps:
  - *"Extracting bidder evidence..."*
  - *"Running semantic retrieval (RAG)..."*
  - *"Applying deterministic statutory rules..."*
- **Polling**: Polls `GET /api/v1/verification/{verification_id}` every 2 seconds until status changes from `PENDING` to `COMPLETED`.

### State 5: Compliance Dashboard & Matrix (`/tenders/[id]/compliance`)
- **Action**: Consumes `GET /api/v1/report/{verification_id}`.
- **Display**: Primary interactive Compliance Table (see schema below).

### State 6: Split-Screen Evidence Viewer
- **Interaction**: Clicking any requirement row opens the side-by-side Evidence Drawer.
- **Display**: Highlights extracted quote, displays source document name, and auto-scrolls the embedded PDF to the exact cited page.

### State 7: Risk Index & Officer Review Cockpit
- **Display**: Composite compliance score (0 - 100), breakdown chips, debarment alert banner, and officer decision notes text area.

### State 8: Audit Report Generation
- **Action**: Calls `GET /api/v1/report/{verification_id}/pdf`.
- **Display**: Download button for official tamper-proof PDF audit report.

---

## 2. Compliance Matrix Table Specification

The compliance matrix table **must** present the following columns:

| Column Header | Data Field | Display Component / Style |
|---|---|---|
| **Requirement** | `requirement` | Text string with category badge (`Financial`, `Technical`, etc.) |
| **Status** | `status` | Color-coded status badge (`PASS` green, `FAIL` red, `REVIEW` amber) |
| **Evidence** | `evidence[0].text` | Truncated quote preview with quotation marks |
| **Source** | `evidence[0].document` + `page` | Clickable pill: `[📄 document.pdf: Page 7]` |
| **Confidence** | `confidence` | Numeric badge (e.g. `94%`) with progress bar |
| **Reason** | `reason` | Plain-language justification string |

---

## 3. Status Badges & Visual Semantics

| Status | Badge Background | Badge Text | Border | Procurement Officer Meaning |
|---|---|---|---|---|
| **`PASS`** | `bg-emerald-950/40` | `text-emerald-400` | `border-emerald-500/30` | Validated compliant. Meets or exceeds mandatory threshold. |
| **`FAIL`** | `bg-rose-950/40` | `text-rose-400` | `border-rose-500/30` | Non-compliant. Below threshold or banned entity. |
| **`REVIEW`** | `bg-amber-950/40` | `text-amber-400` | `border-amber-500/30` | Officer inspection required. Ambiguous, missing, or contradictory. |

---

## 4. TypeScript Interfaces (`frontend/src/lib/types.ts`)

```typescript
export type ComplianceStatus = 'PASS' | 'FAIL' | 'REVIEW';

export interface EvidenceItem {
  text: string;
  document: string;
  page: number;
}

export interface ComplianceResultItem {
  requirement_id: string;
  requirement: string;
  requirement_type: 'financial' | 'technical' | 'statutory' | 'experience' | 'legal';
  status: ComplianceStatus;
  evidence: EvidenceItem[];
  confidence: number;
  reason: string;
  requires_human_review: boolean;
  contradiction_detected?: boolean;
}

export interface VerificationReportResponse {
  verification_id: string;
  tender_number: string;
  bidder_name: string;
  overall_compliance_score: number;
  preliminary_status: string;
  compliance_results: ComplianceResultItem[];
  download_pdf_url: string;
  generated_at: string;
}
```
