"""FastAPI application factory. Run with `uvicorn app.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import health, me
from app.core.auth import build_validator
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import Metrics
from app.core.middleware import RequestContextMiddleware
from app.core.readiness import Check, build_checks
from app.core.secrets import apply_key_vault_secrets
from app.core.telemetry import setup_telemetry

log = get_logger(__name__)

_OUTBOUND_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)


async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
    """Never leak internals: log the error, return a generic body."""
    log.error("unhandled_exception", error_type=type(exc).__name__, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def create_app(
    settings: Settings | None = None,
    readiness_checks: dict[str, Check] | None = None,
) -> FastAPI:
    """Build the application. Dependencies are injectable for tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = await apply_key_vault_secrets(settings or get_settings())
        configure_logging(resolved.log_level)
        setup_telemetry(resolved)
        client = httpx.AsyncClient(timeout=_OUTBOUND_TIMEOUT)
        app.state.settings = resolved
        app.state.http_client = client
        app.state.validator = build_validator(resolved, client)
        app.state.readiness_checks = readiness_checks or build_checks(resolved, client)
        log.info("startup", environment=resolved.environment, auth_mode=resolved.auth_mode)
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(title="insurebot", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware, metrics=Metrics())
    app.add_exception_handler(Exception, _unhandled)
    app.include_router(health.router)
    app.include_router(me.router)
    return app
