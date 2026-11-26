import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.database import Base
import app.models  # Ensure all models are registered

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model MetaData object for 'autogenerate' support
target_metadata = Base.metadata

def get_url() -> str:
    """Retrieve database URL from application settings or environment."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if config.get_main_option("sqlalchemy.url"):
        return config.get_main_option("sqlalchemy.url")
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    target_url = get_url()
    configuration["sqlalchemy.url"] = target_url

    try:
        connectable = async_engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

        await connectable.dispose()
    except Exception as e:
        err_str = str(e).lower()
        is_conn_error = any(k in err_str for k in ["refused", "1225", "10061", "connect", "timeout", "oserror"])
        if "postgresql" in target_url and is_conn_error and settings.ALLOW_SQLITE_FALLBACK:
            sqlite_db = os.path.join(backend_dir, "gem_compliance.db").replace("\\", "/")
            fallback_url = f"sqlite+aiosqlite:///{sqlite_db}"
            configuration["sqlalchemy.url"] = fallback_url
            connectable = async_engine_from_config(
                configuration,
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
            )
            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)
            await connectable.dispose()
        else:
            raise


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
