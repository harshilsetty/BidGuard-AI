import os
import pytest
from app.core.config import settings


def pytest_configure(config):
    """Verify pytest targets an isolated test database rather than live dev gem_compliance."""
    db_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    db_name = db_url.rsplit("/", 1)[-1].split("?")[0].lower()
    if db_name == "gem_compliance" and os.environ.get("ALLOW_LIVE_DEV_DB_TESTS") != "1":
        raise pytest.UsageError(
            "Refusing to run pytest against live development database 'gem_compliance'. "
            "Set DATABASE_URL to an isolated test database (e.g. .../bidguard_fresh_test) "
            "or set ALLOW_LIVE_DEV_DB_TESTS=1 only when no live worker is running."
        )
