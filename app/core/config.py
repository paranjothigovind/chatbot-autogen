"""Application settings. All configuration comes from here; nothing is hardcoded elsewhere."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    """How bearer tokens are validated."""

    ENTRA = "entra"
    LOCAL_DEV = "local_dev"


class Settings(BaseSettings):
    """Typed settings loaded from environment variables (and .env in local dev only)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    # Auth
    auth_mode: AuthMode = AuthMode.ENTRA
    entra_tenant_id: str = ""
    entra_audience: str = ""
    entra_issuer: str = ""
    entra_jwks_url: str = ""
    jwks_cache_ttl_seconds: int = Field(default=3600, ge=60)
    jwt_leeway_seconds: int = Field(default=30, ge=0, le=300)
    local_dev_signing_key: SecretStr = SecretStr("")

    # Backing services
    database_url: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("")
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = ""
    readiness_timeout_seconds: float = Field(default=2.0, gt=0)

    # Secrets and telemetry
    key_vault_url: str = ""
    applicationinsights_connection_string: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def _validate_auth(self) -> "Settings":
        """Fail fast on unsafe or incomplete auth configuration."""
        if self.auth_mode is AuthMode.LOCAL_DEV:
            if self.environment in (Environment.PRODUCTION, Environment.STAGING):
                raise ValueError("AUTH_MODE=local_dev is not allowed outside local/test")
            if len(self.local_dev_signing_key.get_secret_value()) < 32:
                raise ValueError("LOCAL_DEV_SIGNING_KEY must be at least 32 characters")
        elif self.environment is not Environment.TEST:
            missing = [
                name
                for name in ("entra_tenant_id", "entra_audience", "entra_issuer", "entra_jwks_url")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"Entra auth requires: {', '.join(missing)}")
        return self


class _EnvProbe(BaseSettings):
    """Reads only ENVIRONMENT from the process env, so .env use can be decided before validation."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    environment: Environment = Environment.LOCAL


def load_settings(env_file: str | None = None) -> Settings:
    """Build settings; `.env` is honoured only when the environment is not production."""
    if env_file and _EnvProbe().environment in (Environment.LOCAL, Environment.TEST):
        return Settings(_env_file=env_file)
    return Settings(_env_file=None)


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton (immutable configuration, not mutable state)."""
    return load_settings(".env")
