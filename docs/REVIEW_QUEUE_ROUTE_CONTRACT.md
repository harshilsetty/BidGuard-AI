# Review Queue Route Contract

## Non-Overlapping Endpoints

| Endpoint | Router | Permission | Response Schema | Purpose |
|---|---|---|---|---|
| `GET /api/v1/tenders/{tender_id}/review-queue` | `verification_intelligence.py` | `evaluation:read` | `OfficerReviewQueueResponse` | Phase 8.4 Officer bidder risk & statutory verification review queue |
| `GET /api/v1/tenders/{tender_id}/tenderlens-review-queue` | `tenders.py` | `audit:read` | `ReviewQueueListResponse` | Phase 2.0E TenderLens human review queue across requirements, conflicts, and evidence mappings |

## Frontend Alignment
- `fetchTenderReviewQueue(tenderId)` -> `GET /api/v1/tenders/${tenderId}/review-queue` (`OfficerReviewQueueResponse`)
- `fetchTenderLensReviewQueue(tenderId, params)` -> `GET /api/v1/tenders/${tenderId}/tenderlens-review-queue` (`ReviewQueueListResponse`)
