"""Unified error contract: {"detail": {"code": snake_case, "message": str, "fields": {...}|null}}."""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Domain error carrying an HTTP status and a stable machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


def error_payload(code: str, message: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"detail": {"code": code, "message": message, "fields": fields or None}}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.fields),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
            fields[loc or "__root__"] = str(err.get("msg", "invalid"))
        return JSONResponse(
            status_code=422,
            content=error_payload("validation_error", "Request validation failed", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {400: "bad_request", 404: "not_found", 405: "method_not_allowed"}
        code = code_map.get(exc.status_code, f"http_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(status_code=exc.status_code, content=error_payload(code, message))
