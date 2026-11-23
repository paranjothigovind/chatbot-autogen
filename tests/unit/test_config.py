from pathlib import Path

import pytest
from app.core.config import AuthMode, Environment, Settings, load_settings
from pydantic import ValidationError

KEY = "k" * 32


@pytest.mark.parametrize("env", [Environment.PRODUCTION, Environment.STAGING])
def test_local_dev_refused_outside_local(env: Environment) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        Settings(environment=env, auth_mode=AuthMode.LOCAL_DEV, local_dev_signing_key=KEY)  # type: ignore[arg-type]


def test_local_dev_needs_long_key() -> None:
    with pytest.raises(ValidationError, match="32"):
        Settings(
            environment=Environment.LOCAL,
            auth_mode=AuthMode.LOCAL_DEV,
            local_dev_signing_key="short",  # type: ignore[arg-type]
        )


def test_entra_requires_settings_in_production() -> None:
    with pytest.raises(ValidationError, match="Entra auth requires"):
        Settings(environment=Environment.PRODUCTION, auth_mode=AuthMode.ENTRA)


def test_entra_valid_in_production() -> None:
    s = Settings(
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.ENTRA,
        entra_tenant_id="t",
        entra_audience="a",
        entra_issuer="i",
        entra_jwks_url="https://example.invalid/keys",
    )
    assert s.auth_mode is AuthMode.ENTRA


def test_env_file_ignored_in_production(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(f"AUTH_MODE=local_dev\nLOCAL_DEV_SIGNING_KEY={KEY}\n")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENTRA_TENANT_ID", "t")
    monkeypatch.setenv("ENTRA_AUDIENCE", "a")
    monkeypatch.setenv("ENTRA_ISSUER", "i")
    monkeypatch.setenv("ENTRA_JWKS_URL", "https://example.invalid/keys")
    assert load_settings(str(env)).auth_mode is AuthMode.ENTRA


def test_env_file_cannot_smuggle_local_dev_into_production(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"ENVIRONMENT=production\nAUTH_MODE=local_dev\nLOCAL_DEV_SIGNING_KEY={KEY}\n")
    with pytest.raises(ValidationError):
        load_settings(str(env))


def test_env_file_loaded_locally(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"ENVIRONMENT=local\nAUTH_MODE=local_dev\nLOCAL_DEV_SIGNING_KEY={KEY}\n")
    assert load_settings(str(env)).auth_mode is AuthMode.LOCAL_DEV
