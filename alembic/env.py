import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import context

# Ensure project root is on path when Alembic loads this file.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401 — register models on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build URL here and pass it straight into the engine. Do not use
# config.set_main_option("sqlalchemy.url", ...): ConfigParser treats "%"
# as interpolation, so URL-encoded passwords (e.g. %40 for @) break.
_db_url = (
    f"postgresql+asyncpg://{settings.DB_USERNAME}:"
    f"{quote_plus(settings.DB_PASSWORD)}@"
    f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=settings.DB_SCHEMA,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Migrations are often run without starting FastAPI (no lifespan schema step).
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"'))

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=settings.DB_SCHEMA,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        _db_url,
        poolclass=NullPool,
        connect_args={
            "server_settings": {"search_path": f'"{settings.DB_SCHEMA}"'}
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        # Required: otherwise __aexit__ rolls back the whole connection txn and
        # migrations vanish (tables missing, alembic_version unchanged).
        await connection.commit()

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
