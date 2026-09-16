# Testing Strategy — BidGuard (SIH26100)

Reliability and deterministic verification are core requirements for BidGuard. This directory contains end-to-end integration tests and test execution coordination.

---

## 1. Test Suite Organization

| Level | Location | Tools | Responsibility / Coverage |
|---|---|---|---|
| **Unit & Service Tests** | `backend/tests/` & `backend/test_*.py` | `pytest`, `pytest-asyncio` | Statutory adapters, temporal debarment, compliance engine, scoring logic, Pydantic contracts |
| **AI Output Verification** | `ai-engine/` tests | `pytest`, `pydantic` | Structured output parsing, prompt schema compliance, deterministic rule overrides |
| **Frontend Verification** | `frontend/` | `npm run build`, `npm run lint` | Next.js compilation, TypeScript types, UI rendering |
| **End-to-End Core Flow** | `tests/e2e/` | `pytest`, `httpx` | Full lifecycle: Tender upload ➔ Clause extraction ➔ Bidder evidence ➔ Matching ➔ PASS/FAIL/REVIEW ➔ Score ➔ Report |

---

## 2. Running Tests Locally

### A. Run Backend Unit & Integration Tests
```bash
cd backend
pytest -v
```

### B. Run End-to-End Flow Tests
```bash
pytest tests/e2e -v
```

### C. Run Frontend Typecheck & Build
```bash
cd frontend
npm run build
```

---

## 3. Mandatory CI Quality Gate

Before submitting any Pull Request:
1. All `pytest` tests must pass.
2. Frontend build must exit with code 0.
3. No secrets or credentials in diff (`git diff --check`).
