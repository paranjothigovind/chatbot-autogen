"""Pure-ASGI request middleware (safe for SSE streaming)."""

import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.core.metrics import Metrics

log = get_logger(__name__)


class RequestContextMiddleware:
    """Assigns a request id, binds it to logs, and records latency/error metrics."""

    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = str(getattr(scope.get("route"), "path", scope["path"]))
            duration_ms = (time.perf_counter() - started) * 1000
            self.metrics.record_request(route, scope["method"], status_code, duration_ms)
            log.info(
                "request",
                method=scope["method"],
                route=route,
                status=status_code,
                duration_ms=round(duration_ms, 1),
            )
            structlog.contextvars.clear_contextvars()
