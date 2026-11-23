import json

import pytest
from app.core.logging import REDACTED, configure_logging, get_logger, redact_text, redact_value


@pytest.mark.parametrize(
    "text",
    [
        "mail me at jane.doe@example.com please",
        "card 4111 1111 1111 1111 expired",
        "call +1 (415) 555-0132 now",
        "Authorization: Bearer abc.def.ghi",
        "tok eyJhbGciOi.eyJzdWIiOi.sig123",
    ],
)
def test_pii_redacted(text: str) -> None:
    out = redact_text(text)
    assert REDACTED in out
    assert "example.com" not in out
    assert "4111" not in out
    assert "555" not in out
    assert "abc.def.ghi" not in out


def test_sensitive_keys_and_nesting() -> None:
    out = redact_value({"password": "x", "n": {"api_key": "y", "ok": "fine"}, "l": ["a@b.co"]})
    assert out["password"] == REDACTED
    assert out["n"] == {"api_key": REDACTED, "ok": "fine"}
    assert out["l"] == [REDACTED]


def test_json_output_is_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    get_logger("t").info("hello", user_email="bob@example.com", authorization="Bearer zzz")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "hello"
    assert line["user_email"] == REDACTED
    assert line["authorization"] == REDACTED
    assert line["level"] == "info"
