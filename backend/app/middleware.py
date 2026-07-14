"""Middleware global de errores para la API.

Captura excepciones no manejadas y retorna respuestas JSON
consistentes en lugar del HTML por defecto de FastAPI.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler para excepciones no capturadas — retorna JSON 500."""
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
            "detail": "Error interno del servidor",
            "code": "INTERNAL_ERROR",
        },
    )


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    """Handler para HTTPException — asegura formato JSON consistente."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": None,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Registra los handlers de error globales en la app."""
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
                "detail": "Error de validación",
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
        # En debug, incluir traceback; en producción, solo mensaje genérico
        from app.config import settings

        detail = str(exc) if settings.debug else "Error interno del servidor"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "code": "INTERNAL_ERROR"},
        )
