"""Liveness and readiness endpoints (unauthenticated, no sensitive detail)."""

import asyncio

from fastapi import APIRouter, Request, Response, status

from app.core.logging import get_logger
from app.core.readiness import Check, run_check

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, object]:
    """Readiness: Redis, Postgres and Azure OpenAI are reachable."""
    checks: dict[str, Check] = request.app.state.readiness_checks
    timeout: float = request.app.state.settings.readiness_timeout_seconds
    results = await asyncio.gather(*(run_check(c, timeout) for c in checks.values()))
    report = dict(zip(checks, results, strict=True))
    ready = all(report.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        log.warning("not_ready", failing=[k for k, ok in report.items() if not ok])
    return {"status": "ready" if ready else "unavailable", "checks": report}
