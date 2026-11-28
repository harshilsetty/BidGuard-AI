# Phase 2.0D.2 Test Isolation Design

## 1. Problem

Running `pytest` against `gem_compliance` while a local `uvicorn` dev server (`TenderProcessingWorkerManager`) is running causes the live server worker to claim `QUEUED` jobs created by `test_phase2_0b_async_processing.py`.

## 2. Safeguards (`backend/conftest.py`)

1. **Dedicated Test Database:** `backend/conftest.py` verifies `DATABASE_URL` during `pytest` collection/session startup.
2. **Live-Worker Contention Guard:** If `DATABASE_URL` points to `gem_compliance` (non-test DB) and `ALLOW_LIVE_DEV_DB_TESTS != "1"`, `pytest` aborts safely before running tests unless `DATABASE_URL` targets an isolated test database (`bidguard_fresh_test` or SQLite test DB), preventing accidental mutation of live dev state or worker race conditions.
3. **Supported Test Command (PowerShell):**
   ```powershell
   cd backend
   $env:DATABASE_URL="postgresql+asyncpg://postgres:postgrespassword@127.0.0.1:5432/bidguard_fresh_test"
   python -m pytest -v --tb=short
   ```
   *(Replace password with your local `.env` PostgreSQL password.)*
