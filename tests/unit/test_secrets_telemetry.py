from types import SimpleNamespace
from typing import Any

import pytest
from app.core import telemetry
from app.core.config import Settings
from app.core.secrets import apply_key_vault_secrets

from tests.conftest import with_overrides


class FakeVault:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = data

    def get_secret(self, name: str) -> Any:
        if name not in self.data:
            raise KeyError(name)
        return SimpleNamespace(value=self.data[name])


async def test_no_vault_url_returns_same_settings(local_settings: Settings) -> None:
    assert await apply_key_vault_secrets(local_settings) is local_settings


async def test_vault_overrides_secrets(local_settings: Settings) -> None:
    s = with_overrides(local_settings, **{"key_vault_url": "https://kv.invalid"})
    out = await apply_key_vault_secrets(s, FakeVault({"redis-url": "redis://kv-host:6379/0"}))
    assert out.redis_url.get_secret_value() == "redis://kv-host:6379/0"
    assert out.database_url.get_secret_value() == ""  # missing secret keeps env value


def test_telemetry_noop_without_connection_string(local_settings: Settings) -> None:
    assert telemetry.setup_telemetry(local_settings) is False


def test_telemetry_configures_azure_monitor(
    local_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        telemetry,
        "configure_azure_monitor",
        lambda connection_string: calls.append(connection_string),
    )
    s = with_overrides(
        local_settings, **{"applicationinsights_connection_string": "InstrumentationKey=fake"}
    )
    assert telemetry.setup_telemetry(s) is True
    assert calls == ["InstrumentationKey=fake"]
