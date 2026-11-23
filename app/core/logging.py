"""Structured JSON logging with PII and secret redaction."""

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = re.compile(
    r"(authorization|password|passwd|secret|token|api[_-]?key|cookie|connection[_-]?string)",
    re.IGNORECASE,
)
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # email
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),  # bearer tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),  # JWTs
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # card-like numbers
    re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d\b"),  # phone numbers
)


def redact_text(value: str) -> str:
    """Replace PII-looking substrings in free text."""
    for pattern in _PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact_value(value: Any, key: str | None = None) -> Any:
    """Recursively redact a log value; sensitive keys are blanked entirely."""
    if key and _SENSITIVE_KEYS.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {k: redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [redact_value(v) for v in value]
    return value


def redaction_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor that redacts every field of the event."""
    return {k: redact_value(v, k) for k, v in event_dict.items()}


def _stdout_logger(*_args: Any) -> structlog.PrintLogger:
    """Resolve sys.stdout at log time so a swapped or closed stream is never held."""
    return structlog.PrintLogger(file=sys.stdout)


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog and stdlib logging to emit JSON lines on stdout."""
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        redaction_processor,
        structlog.processors.JSONRenderer(),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=_stdout_logger,
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(level=level.upper(), stream=sys.stdout, format="%(message)s", force=True)


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Return a bound logger."""
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
