# Reviewer Assignment Authorization Design

## Server-Side Rules (`TenderReviewService.assign_reviewer`)
1. **Caller Authorization:** Enforced at endpoint `POST /api/v1/tenders/{tender_id}/review-assignments` via `require_permission("user:manage")` and `get_authorized_tender`.
2. **Assignee Validation (when `assignee_user_id` is not `None`):**
   - Must exist in `users` with `User.organization_id == tender.organization_id` and `User.is_active == True`.
   - Live RBAC roles and permissions are loaded from `UserRole -> Role -> RolePermission -> Permission`.
   - Assignee must hold `evaluation:override` permission (or `SUPER_ADMIN` role). Otherwise raises `403 Forbidden`.
3. **Unassignment (`assignee_user_id is None`):** Permitted for `user:manage` callers to clear `assigned_reviewer_id`.
4. **Concurrency & Audit:** Uses conditional `UPDATE ... WHERE review_version = :expected_version`, increments `review_version`, records `ASSIGN` in `ReviewDecision` (keeping `previous_status == new_status`) and `REVIEW_ASSIGNED` in `AuditLog`. Assignment never alters review statuses or grants permissions.
