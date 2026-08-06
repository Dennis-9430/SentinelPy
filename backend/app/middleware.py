"""Global error middleware for the API.

Catches unhandled exceptions and returns consistent JSON responses
instead of FastAPI's default HTML.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for uncaught exceptions — returns JSON 500."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    """Handler for HTTPException — ensures a consistent JSON format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": None,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register the global error handlers on the app."""
    from fastapi.exceptions import HTTPException, RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(HTTPException)
    async def fastapi_http_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": None},
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc.detail), "code": None},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = " → ".join(str(part) for part in err.get("loc", []))
            errors.append(f"{loc}: {err.get('msg', '')}")
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "code": "VALIDATION_ERROR",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        # In debug, include the traceback; in production, only a generic message
        from app.config import settings

        detail = str(exc) if settings.debug else "Error interno del servidor"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "code": "INTERNAL_ERROR"},
        )
