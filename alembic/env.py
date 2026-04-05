"""
Alembic uses a *sync* PostgreSQL driver (psycopg v3) on purpose.

Async engines + ``async with connect()`` can roll back the whole connection on
exit unless you remember ``commit()``, which silently undoes migrations. Sync
``connect`` + Alembic's ``begin_transaction()`` matches upstream Alembic docs.
"""
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, pool, text

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401 — register models on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# psycopg v3 URL — do not pass through ConfigParser (breaks on % in passwords).
SYNC_DB_URL = (
    f"postgresql+psycopg://{settings.DB_USERNAME}:"
    f"{quote_plus(settings.DB_PASSWORD)}@"
    f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=SYNC_DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=False,
        compare_server_default=False, 
        version_table_schema=settings.DB_SCHEMA,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(SYNC_DB_URL, poolclass=pool.NullPool)

    with engine.connect() as connection:
        connection.execute(
            text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"')
        )
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=False,
            compare_server_default=False, 
            version_table_schema=settings.DB_SCHEMA,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
