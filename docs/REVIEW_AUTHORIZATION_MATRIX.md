# Review Authorization Matrix (Phase 2.0E)

| Action / Endpoint | `SUPER_ADMIN` | `ORG_ADMIN` | `PROCUREMENT_OFFICER` | `AUDITOR` | `BIDDER` |
|---|---|---|---|---|---|
| View review queue, details, workload, decision history (`tender:read` + `audit:read`) | Yes (all orgs) | Yes (own org) | Yes (own org) | Yes (own org, read-only) | **403 Denied** |
| Submit review decision (`CONFIRM`, `REJECT`, `REQUEST_CLARIFICATION`, `DISMISS`, `RESOLVE`) (`evaluation:override`) | Yes | Yes (own org) | Yes (own org) | **403 Denied** | **403 Denied** |
| Reopen reviewed item (`evaluation:override`) | Yes | Yes (own org) | Yes (own org) | **403 Denied** | **403 Denied** |
| Assign / Reassign reviewer (`user:manage`) | Yes | Yes (own org) | **403 Denied** | **403 Denied** | **403 Denied** |

- All endpoints enforce `get_authorized_tender(tender_id, current_user, db)` and PostgreSQL `FORCE ROW LEVEL SECURITY`.
- Reviewer identity is always taken from `current_user.id` (never from request payloads).
- Assignment validates that `assignee_user_id` belongs to the same organization and `is_active == True`.
