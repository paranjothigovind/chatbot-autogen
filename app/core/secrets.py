"""Key Vault secret loading (Azure only; local dev uses .env)."""

import asyncio
from typing import Protocol

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Settings field -> Key Vault secret name.
SECRET_MAP: dict[str, str] = {
    "database_url": "database-url",
    "redis_url": "redis-url",
    "applicationinsights_connection_string": "applicationinsights-connection-string",
    "local_dev_signing_key": "local-dev-signing-key",
}


class SecretReader(Protocol):
    """Minimal interface of the Key Vault client."""

    def get_secret(self, name: str) -> "_Secret": ...


class _Secret(Protocol):
    value: str | None


def build_secret_client(vault_url: str) -> SecretReader:
    """Create a Key Vault client using managed identity (or developer credentials)."""
    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())  # type: ignore[return-value]


def _fetch(client: SecretReader) -> dict[str, SecretStr]:
    """Fetch mapped secrets; missing secrets are skipped, not fatal."""
    found: dict[str, SecretStr] = {}
    for field, name in SECRET_MAP.items():
        try:
            secret = client.get_secret(name)
        except Exception:
            log.warning("key_vault_secret_unavailable", secret=name)
            continue
        if secret.value:
            found[field] = SecretStr(secret.value)
    return found


async def apply_key_vault_secrets(
    settings: Settings, client: SecretReader | None = None
) -> Settings:
    """Return settings with secret fields overridden from Key Vault, if configured."""
    if not settings.key_vault_url:
        return settings
    reader = client or build_secret_client(settings.key_vault_url)
    overrides = await asyncio.to_thread(_fetch, reader)
    return Settings.model_validate({**settings.model_dump(), **overrides})
