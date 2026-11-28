# Phase 2.0E.1 Audit Baseline

**Audit Phase:** 2.0E.1 — Independent Acceptance Audit (Read-Only)  
**Date:** 2026-11-27  
**Repository:** `harshilsetty/BidGuard-AI`  

---

## 1. Git Repository State
- **Branch:** `main`
- **HEAD:** `2c3a9b1abbf0a752a7ca69f973525f06956b9d38`
- **Modified Files (Uncommitted, Preserved):**
  - `.github/workflows/ci.yml`
  - `backend/app/api/v1/tenders.py`
  - `backend/app/models/__init__.py`
  - `backend/app/models/tender.py`
  - `backend/app/schemas/tender.py`
  - `frontend/src/app/tenders/[id]/clauses/page.tsx`
  - `frontend/src/lib/api-client.ts`
  - `frontend/src/lib/types.ts`
- **Untracked Files (Preserved):**
  - `backend/alembic/versions/0012_audit_immutability_sync.py`
  - `backend/alembic/versions/0013_human_review_decisions.py`
  - `backend/app/services/review_service.py`
  - `backend/conftest.py`
  - `backend/test_phase2_0d_2_remediation.py`
  - `backend/test_phase2_0e_human_review.py`
  - `docs/AUDIT_IMMUTABILITY_AND_RETENTION_DESIGN.md`
  - `docs/HUMAN_REVIEW_DOMAIN_DESIGN.md`
  - `docs/PHASE_2_0D_2_*`, `docs/PHASE_2_0E_*`, `docs/REVIEW_*`
  - `frontend/src/components/TenderReviewWorkspace.tsx`

---

## 2. Database & Migration State

| Database | Alembic Revision | `bidguard_app` Role |
|---|---|---|
| `gem_compliance` | `0013_human_review_decisions` | `rolsuper=False`, `rolbypassrls=False`, `rolcanlogin=True` |
| `bidguard_fresh_test` | `0013_human_review_decisions` | `rolsuper=False`, `rolbypassrls=False`, `rolcanlogin=True` |

### RLS Enablement & FORCE Status (Verified on Both Databases)
- `audit_logs`: `relrowsecurity=True`, `relforcerowsecurity=True`
- `review_decisions`: `relrowsecurity=True`, `relforcerowsecurity=True`
- `tender_requirements`: `relrowsecurity=True`, `relforcerowsecurity=True`
- `tender_requirement_sources`: `relrowsecurity=True`, `relforcerowsecurity=True`
- `tender_requirement_conflicts`: `relrowsecurity=True`, `relforcerowsecurity=True`
- `tender_requirement_evidence`: `relrowsecurity=True`, `relforcerowsecurity=True`

### Immutability Trigger (`review_decisions`)
Verified on both `gem_compliance` and `bidguard_fresh_test`:
- **Trigger:** `trg_review_decisions_immutable` (`tgenabled=b'O'`), `BEFORE DELETE OR UPDATE ON public.review_decisions FOR EACH ROW EXECUTE FUNCTION prevent_review_decision_mutation()`
- **Function:** `prevent_review_decision_mutation()` raises exception `'review_decisions is append-only: % operations are forbidden', TG_OP`.

---

## 3. Active Processes
- `PID 34200` (`python.exe`, started `11/27/2026 12:59:42 AM`) and `PID 37468` (`python.exe`, started `11/27/2026 2:25:01 AM`) — live development server / background processes preserved untouched.
- All audit tests and probes ran exclusively against `bidguard_fresh_test`.
