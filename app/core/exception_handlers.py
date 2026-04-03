from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import RailMindException
from app.core.response import json_error, validation_error
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


async def railmind_exception_handler(request: Request, exc: RailMindException) -> JSONResponse:
    return json_error(exc.message, status_code=exc.status_code, code=exc.code)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = validation_error(exc.errors())
    return JSONResponse(status_code=422, content=jsonable_encoder(body))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return json_error("An unexpected error occurred", status_code=500, code="RM-GEN-001")