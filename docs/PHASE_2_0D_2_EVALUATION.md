# Phase 2.0D.2 Verification & Evaluation Results

**Repository:** `harshilsetty/BidGuard-AI`  
**Isolated Test Database:** `bidguard_fresh_test` (PostgreSQL 16, Alembic `0012_audit_immutability_sync`)

---

## 1. Command & Verification Matrix

| Suite / Check | Database / Environment | Collected | Passed | Failed | Skipped | Duration |
|---|---|---:|---:|---:|---:|---:|
| `python -m pytest test_phase2_0d_2_remediation.py -v --tb=short` | `bidguard_fresh_test` | 3 | 3 | 0 | 0 | `5.71s` |
| `python -m pytest test_enterprise_org_invitations.py -v --tb=short` | `bidguard_fresh_test` | 3 | 3 | 0 | 0 | `12.05s` |
| **Complete Backend Suite** (`python -m pytest -v --tb=short`) | `bidguard_fresh_test` | **343** | **343** | **0** | **0** | **`303.22s`** (`0:05:03`) |
| `conftest.py` isolation guard (`--collect-only` on `gem_compliance`) | `gem_compliance` | Aborted safely | — | — | — | `<1s` |
| Frontend (`npx tsc --noEmit; npm test; npm run build`) | Node.js / Next.js 15 | 13 unit + build | 13 | 0 | 0 | `112.97ms` (`npm test`) |

---

## 2. Golden Demo Comparison (Unchanged)

All 4 `test_golden_demo_frozen_regression.py` checks passed inside the 343-test run with frozen fixtures and outputs unchanged:

| Bidder | PASS | FAIL | REVIEW | Standalone | Fused |
|---|---:|---:|---:|---:|---:|
| EnterpriseTech Solutions | 11 | 0 | 0 | `100.00` | `90.45` |
| Legacy Hardware | 1 | 9 | 1 | `53.41` | `40.45` |
| Apex Systems | 3 | 5 | 3 | `47.95` | `34.77` |
