"""FastAPI application factory and static frontend mounting."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from minicode.web import __version__
from minicode.web.api import create_api_router
from minicode.web.runner import WebSessionRunner


logger = logging.getLogger(__name__)


def _error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    retryable: bool = False,
    trace_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "traceId": trace_id or f"trace-{uuid.uuid4().hex[:12]}",
                "retryable": retryable,
            }
        },
    )


def create_app(
    *,
    workspace: str | Path | None = None,
    runner: WebSessionRunner | None = None,
    frontend_dir: str | Path | None = None,
) -> FastAPI:
    active_runner = runner or WebSessionRunner(workspace or Path.cwd())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        active_runner.close()

    app = FastAPI(
        title="MiniCode Local Web API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.runner = active_runner
    app.include_router(create_api_router(active_runner))

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return _error_response(
            code=str(detail.get("code", "HTTP_ERROR")),
            message=str(detail.get("message", "The request could not be completed.")),
            status_code=exc.status_code,
            retryable=bool(detail.get("retryable", False)),
            trace_id=str(detail.get("traceId", "")) or None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(item) for item in first.get("loc", []) if item != "body")
        message = f"Invalid request field: {location or 'body'}."
        return _error_response(
            code="VALIDATION_ERROR",
            message=message,
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        logger.exception("Unhandled Web API error [%s]", trace_id)
        return _error_response(
            code="INTERNAL_ERROR",
            message="The local Web service encountered an unexpected error.",
            status_code=500,
            trace_id=trace_id,
        )

    dist = Path(frontend_dir) if frontend_dir else Path(__file__).parents[2] / "web" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="web-assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str) -> Any:
            candidate = (dist / path).resolve()
            try:
                candidate.relative_to(dist.resolve())
            except ValueError:
                candidate = dist / "index.html"
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def development_info() -> dict[str, str]:
            return {
                "service": "MiniCode Local Web API",
                "version": __version__,
                "frontend": "Run `cd web && npm run dev` or build the frontend first.",
            }

    return app


def create_default_app() -> FastAPI:
    return create_app(workspace=Path.cwd())
