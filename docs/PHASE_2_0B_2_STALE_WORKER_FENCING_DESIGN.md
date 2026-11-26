# Phase 2.0B.2 Design: Stale-Worker Fencing & Job Ownership Integrity

## 1. Monotonic Fencing Token (`ownership_generation`)

Every `TenderProcessingJob` carries a persistent integer column:
- `ownership_generation INTEGER NOT NULL DEFAULT 0`

### State Transitions & Generation Increments
| Transition | Trigger | `ownership_generation` Change |
|---|---|---|
| Enqueue / Retry (`-> QUEUED`) | API `/process` or `/retry` | Preserved (or initialized `0` on insert) |
| Claim (`QUEUED -> RUNNING`) | `claim_next_job(db, worker_id)` | **Atomically incremented (`ownership_generation + 1`)** |
| Lease Recovery (`RUNNING -> QUEUED` or `FAILED`) | `recover_expired_leases(db)` | **Atomically incremented (`ownership_generation + 1`)** |
| Graceful Shutdown (`RUNNING -> QUEUED`) | `CancelledError` handler | **Atomically incremented (`ownership_generation + 1`)** only when `WHERE id=:id AND status='RUNNING' AND worker_id=:wid AND ownership_generation=:gen` |

Because `ownership_generation` increments on **every** claim and **every** lease recovery/release, two executions—even from the **same `worker_id`**—can never share the same `(worker_id, ownership_generation)` pair.

---

## 2. Guarded Write Boundaries

All worker write boundaries require the exact predicate:
`TenderProcessingJob.id == job_id AND TenderProcessingJob.status == 'RUNNING' AND TenderProcessingJob.worker_id == worker_id AND TenderProcessingJob.ownership_generation == generation`.

1. **Heartbeat (`_heartbeat_loop`):**
   - Executes conditional `UPDATE tender_processing_jobs SET heartbeat_at=..., lease_expires_at=... WHERE id=:id AND status='RUNNING' AND worker_id=:wid AND ownership_generation=:gen`.
   - If `rowcount == 0`, sets `ownership_lost_event` and `stop_event`, logs structured `OWNERSHIP_LOST` warning, and stops heartbeating immediately.
2. **Stage Progression (`EXTRACTING_PAGES`, step 3):**
   - Conditional `UPDATE` with fencing predicate; if `rowcount == 0`, aborts before running extraction (`return "OWNERSHIP_LOST"`).
3. **Page Persistence (`PERSISTING_PAGES`, step 5):**
   - **No DB transaction held during `asyncio.to_thread(extract_pages_from_pdf, ...)`**.
   - Opens a short transaction, locks/updates `TenderProcessingJob` row with `SELECT ... FOR UPDATE` (or conditional `UPDATE ... RETURNING id`) verifying `(status == 'RUNNING', worker_id == worker_id, ownership_generation == generation)`.
   - Only if ownership is verified does it call `_persist_pages_idempotently(db, doc_id, pages_data)` and `commit()`. Otherwise rolls back and returns `"OWNERSHIP_LOST"`.
4. **Finalization (`SUCCEEDED`, step 6):**
   - Conditional `UPDATE` on `TenderProcessingJob` (`status='SUCCEEDED', ...`) with fencing predicate.
   - Only if `rowcount == 1` does it update `TenderDocument.processing_status = 'READY'` in the same transaction and `commit()`; otherwise rolls back and returns `"OWNERSHIP_LOST"`.
5. **Failure Handling (`_handle_job_failure`):**
   - Locks/selects or conditionally updates `TenderProcessingJob` with `(id == job_id, status == 'RUNNING', worker_id == worker_id, ownership_generation == generation)`.
   - If not matched (`None` / `rowcount == 0`), logs structured `OWNERSHIP_LOST` event and returns `"OWNERSHIP_LOST"` without touching `retry_count`, `status`, `error_code`, or `TenderDocument.processing_status`.
6. **Graceful Shutdown (`CancelledError`):**
   - Conditional `UPDATE` with fencing predicate (`status='QUEUED', current_stage='QUEUED', worker_id=None, lease_expires_at=None, ownership_generation=ownership_generation + 1`).
   - Only updates `TenderDocument.processing_status = 'QUEUED'` if `rowcount == 1`.

---

## 3. PostgreSQL RLS & Backward Compatibility

- `0009_job_ownership_generation` is strictly additive (`ADD COLUMN ownership_generation INTEGER NOT NULL DEFAULT 0`).
- Existing `0008_tender_jobs_and_pages` RLS policies (`tenant_isolation_tender_processing_jobs`, `tenant_isolation_tender_document_pages`) and `bidguard_app` privileges remain unchanged.
- `TenderProcessingJobResponse` can optionally expose `ownership_generation: Optional[int] = None` (or keep internal; exposing or keeping it non-sensitive is safe, and existing API contracts remain 100% backward-compatible).
