"""
errors.py — Manejo seguro de errores HTTP.

Centraliza el patrón "logear el detalle en el servidor, devolver mensaje
genérico al cliente" para evitar filtrar stack traces, nombres de tablas,
rutas internas u otra información sensible vía respuestas HTTP.

Exporta:
    - safe_http_error(): helper para routers.
    - register_exception_handlers(): red de seguridad global para excepciones
      no capturadas (devuelve 500 genérico en lugar del stack trace por defecto
      de FastAPI/Starlette cuando DEBUG=False).
"""
from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def safe_http_error(
    status_code: int,
    client_message: str,
    log_detail: str,
    exc: Exception | None = None,
) -> NoReturn:
    """Registra el detalle real en el log del servidor y eleva HTTPException con
    un mensaje genérico que NO revela internals (exc, exc.orig, rutas, etc.).

    Uso típico en routers (reemplaza `raise HTTPException(500, f"...: {exc}")`):

        try:
            ...
        except Exception as exc:
            await db.rollback()
            logger.error("Error en check-in: %s", exc)   # opcional, ya lo hace safe_http_error
            safe_http_error(
                status_code=500,
                client_message="Error interno del servidor",
                log_detail="Error en check-in",
                exc=exc,
            )

    Args:
        status_code: código HTTP a devolver al cliente (ej. 500, 400).
        client_message: mensaje seguro a mostrar al cliente (sin internals).
        log_detail: descripción contextual para el log del servidor.
        exc: excepción original (opcional). Se registra con logger.error para
            preservar el traceback completo en el servidor.
    """
    if exc is not None:
        # logger.exception añade el traceback; logger.error con %s solo el str.
        # Usamos logger.error para no duplicar si el caller ya logueó, pero
        # incluimos el detalle contextual.
        logger.error("%s — %s", log_detail, exc)
    else:
        logger.error(log_detail)
    raise HTTPException(status_code=status_code, detail=client_message)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra handlers globales para impedir fugas de información.

    1. Exception (catch-all): cualquier excepción no HTTPException se convierte
       en HTTP 500 con mensaje genérico. El traceback se registra en el servidor
       vía logger.exception(), pero NO se incluye en la respuesta JSON.
    2. RequestValidationError: se conserva el comportamiento estándar (422) pero
       sin revelar internals; los detalles de validación son útiles para el
       cliente legítimo y no exponen secretos.
    """

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Registramos el traceback completo en el servidor para diagnóstico.
        logger.exception(
            "Excepción no controlada en %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # Las HTTPException (incluidas las de safe_http_error) ya tienen un
        # detail seguro. Las pasamos sin modificar.
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Errores de validación de Pydantic: son útiles para el cliente y no
        # exponen secretos. Se conservan los detalles (comportamiento estándar).
        logger.warning(
            "Validación fallida en %s %s: %s",
            request.method,
            request.url.path,
            exc.errors(),
        )
        return JSONResponse(status_code=422, content={"detail": exc.errors()})