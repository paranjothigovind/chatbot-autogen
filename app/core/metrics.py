"""OpenTelemetry metric instruments. Instruments are created lazily from the active meter."""

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram

_METER_NAME = "insurebot"


class Metrics:
    """Holds the application's metric instruments."""

    def __init__(self) -> None:
        meter = metrics.get_meter(_METER_NAME)
        self.request_latency: Histogram = meter.create_histogram(
            "http.server.request.duration", unit="ms", description="Request latency"
        )
        self.request_errors: Counter = meter.create_counter(
            "app.request.errors", description="Requests that ended in a 5xx"
        )
        self.tokens: Counter = meter.create_counter(
            "app.llm.tokens", description="LLM tokens consumed, per user"
        )
        self.cost: Counter = meter.create_counter(
            "app.llm.cost", unit="USD", description="Estimated LLM cost, per user"
        )

    def record_request(self, route: str, method: str, status: int, duration_ms: float) -> None:
        """Record latency, and an error count for 5xx responses."""
        attrs: dict[str, str | int] = {
            "http.route": route,
            "http.method": method,
            "http.status_code": status,
        }
        self.request_latency.record(duration_ms, attrs)
        if status >= 500:
            self.request_errors.add(1, attrs)

    def record_usage(
        self, user_id: str, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> None:
        """Record per-user token and cost usage."""
        self.tokens.add(prompt_tokens, {"user_id": user_id, "kind": "prompt"})
        self.tokens.add(completion_tokens, {"user_id": user_id, "kind": "completion"})
        self.cost.add(cost, {"user_id": user_id})
