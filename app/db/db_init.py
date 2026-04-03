from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def create_database_if_not_exists():
    default_db_url = (
        f"postgresql+asyncpg://{settings.DB_USERNAME}:"
        f"{quote_plus(settings.DB_PASSWORD)}@"
        f"{settings.DB_HOST}:{settings.DB_PORT}/postgres"
    )

    engine = create_async_engine(default_db_url, isolation_level="AUTOCOMMIT")

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:dbname"),
            {"dbname": settings.DB_NAME},
        )
        exists = result.scalar()

        if not exists:
            print(f"Creating database {settings.DB_NAME}...")
            await conn.execute(text(f'CREATE DATABASE "{settings.DB_NAME}"'))
        else:
            print(f"Database {settings.DB_NAME} already exists.")

    await engine.dispose()


async def create_schema_if_not_exists():
    db_url = (
        f"postgresql+asyncpg://{settings.DB_USERNAME}:"
        f"{quote_plus(settings.DB_PASSWORD)}@"
        f"{settings.DB_HOST}:{settings.DB_PORT}/"
        f"{settings.DB_NAME}"
    )

    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        await conn.execute(
            text(f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"')
        )
        print(f'Schema "{settings.DB_SCHEMA}" ensured.')

    await engine.dispose()
