"""Conversión centralizada de excepciones al formato `{"error": {"code","message","details"}}`."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_service.core.errors import (
    AppError,
    DocumentNotFound,
    FeatureNotImplemented,
    GenerationInProgress,
    GenerationNotFound,
)

logger = logging.getLogger(__name__)

_STATUS_BY_ERROR: dict[type[AppError], int] = {
    DocumentNotFound: 404,
    GenerationNotFound: 404,
    GenerationInProgress: 409,
    FeatureNotImplemented: 501,
}

# Errores HTTP del framework (rutas inexistentes, métodos no permitidos, etc.).
_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    404: ("NOT_FOUND", "El recurso solicitado no existe."),
    405: ("METHOD_NOT_ALLOWED", "Método no permitido para este recurso."),
}

_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Construye una respuesta de error con el formato común."""
    body = {"error": {"code": code, "message": message, "details": details if details is not None else {}}}
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body), headers=headers)


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    details = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ())]
        if len(location) > 1 and location[0] in _LOCATION_PREFIXES:
            location = location[1:]
        details.append({"path": ".".join(location), "message": str(error.get("msg", "Valor inválido."))})
    return details


async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        400, "VALIDATION_ERROR", "La solicitud contiene datos inválidos.", _validation_details(exc)
    )


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    status_code = _STATUS_BY_ERROR.get(type(exc), 500)
    if status_code == 500:
        logger.error("AppError sin estado HTTP asignado: %s", type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "Ocurrió un error interno.")
    return error_response(status_code, exc.code, exc.message, exc.details)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normaliza 404/405 y demás errores HTTP del framework, conservando estado y cabeceras."""
    code, message = _HTTP_ERRORS.get(exc.status_code, ("HTTP_ERROR", "No se pudo procesar la solicitud."))
    headers = dict(exc.headers) if exc.headers else None
    return error_response(exc.status_code, code, message, headers=headers)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return error_response(500, "INTERNAL_ERROR", "Ocurrió un error interno.")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores globales en la aplicación."""
    app.add_exception_handler(RequestValidationError, _handle_validation)  # type: ignore[arg-type]
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
