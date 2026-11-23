import httpx
import pytest
import respx
from app.core import readiness
from app.core.config import Settings

from tests.conftest import with_overrides


async def test_checks_fail_when_unconfigured(local_settings: Settings) -> None:
    async with httpx.AsyncClient() as client:
        for name, check in readiness.build_checks(local_settings, client).items():
            assert await readiness.run_check(check, 0.5) is False, name


async def test_azure_openai_reachable(local_settings: Settings) -> None:
    s = with_overrides(local_settings, **{"azure_openai_endpoint": "https://aoai.example.invalid"})
    with respx.mock() as mock:
        mock.get("https://aoai.example.invalid").respond(404)
        async with httpx.AsyncClient() as client:
            await readiness.check_azure_openai(s, client)


async def test_azure_openai_unreachable(local_settings: Settings) -> None:
    s = with_overrides(local_settings, **{"azure_openai_endpoint": "https://aoai.example.invalid"})
    with respx.mock() as mock:
        mock.get("https://aoai.example.invalid").mock(side_effect=httpx.ConnectError("x"))
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.ConnectError):
                await readiness.check_azure_openai(s, client)
