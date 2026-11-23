"""OpenTelemetry setup, exporting to Azure Monitor when a connection string is configured."""

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


def setup_telemetry(settings: Settings) -> bool:
    """Enable Azure Monitor export. Returns False (no-op) when not configured."""
    conn = settings.applicationinsights_connection_string.get_secret_value()
    if not conn:
        log.info("telemetry_disabled", reason="no connection string")
        return False
    configure_azure_monitor(connection_string=conn)
    return True


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer for manual spans (auth, router, tools, upstream calls)."""
    return trace.get_tracer(name)
