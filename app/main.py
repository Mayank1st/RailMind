from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.router import router as api_router
from app.config import settings
from app.ai.router import router as ai_router
from app.db.db_init import (
    create_database_if_not_exists,
    create_schema_if_not_exists,
)
from app.core.exceptions import RailMindException
from app.core.exception_handlers import (
    railmind_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import add_pagination

from app.dependencies import get_db
from app.utils.helpers import get_utc_timezone


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting application...")
    await create_database_if_not_exists()
    await create_schema_if_not_exists()
    print("✅ Database & Schema ready.")
    yield
    print("🛑 Shutting down application...")


app = FastAPI(lifespan=lifespan, redirect_slashes=False)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_exception_handler(RailMindException, railmind_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router, prefix="/api")
app.include_router(ai_router, prefix="/api/v1")

# Enables fastapi-pagination across all routers (page/size resolution).
add_pagination(app)


@app.get("/", tags=["Home"])
async def home_route():
    return {
        "Name": "RailMind-BE",
        "Version": "1.0",
        "Creator": "Mayank Kumar",
        "Time": get_utc_timezone(),
    }


@app.get("/db-test")
async def db_test(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"status": "connected", "result": result.scalar()}
