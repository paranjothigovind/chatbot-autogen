"""Shared fixtures. All secrets here are fake test values."""

import pytest
from app.core.config import AuthMode, Environment, Settings

TEST_SIGNING_KEY = "test-signing-key-0123456789-abcdefghij"


def with_overrides(settings: Settings, **overrides: object) -> Settings:
    """Return validated settings with fields replaced (model_copy skips validation)."""
    return Settings.model_validate({**settings.model_dump(), **overrides})


@pytest.fixture
def local_settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        auth_mode=AuthMode.LOCAL_DEV,
        local_dev_signing_key=TEST_SIGNING_KEY,  # type: ignore[arg-type]
    )
