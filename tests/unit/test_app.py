import asyncio

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

from tests.conftest import with_overrides


async def _ok() -> None:
    return None


async def _fail() -> None:
    raise ConnectionError("db password=hunter2 host=internal")


def test_healthz_needs_no_auth(local_settings: Settings) -> None:
    with TestClient(create_app(local_settings, readiness_checks={})) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
        assert "x-request-id" in r.headers


def test_readyz_ok(local_settings: Settings) -> None:
    checks = {"redis": _ok, "postgres": _ok, "azure_openai": _ok}
    with TestClient(create_app(local_settings, readiness_checks=checks)) as c:
        r = c.get("/readyz")
        assert r.status_code == 200
        assert r.json()["checks"] == {"redis": True, "postgres": True, "azure_openai": True}


def test_readyz_unavailable_hides_error_detail(local_settings: Settings) -> None:
    checks = {"redis": _ok, "postgres": _fail, "azure_openai": _ok}
    with TestClient(create_app(local_settings, readiness_checks=checks)) as c:
        r = c.get("/readyz")
        assert r.status_code == 503
        assert r.json()["checks"]["postgres"] is False
        assert "hunter2" not in r.text


def test_readyz_times_out_slow_check(local_settings: Settings) -> None:
    async def slow() -> None:
        await asyncio.sleep(5)

    s = with_overrides(local_settings, **{"readiness_timeout_seconds": 0.05})
    with TestClient(create_app(s, readiness_checks={"redis": slow})) as c:
        assert c.get("/readyz").status_code == 503


def test_unhandled_error_returns_generic_body(local_settings: Settings) -> None:
    app = create_app(local_settings, readiness_checks={})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals /srv/app.py")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal server error"}
        assert "secret" not in r.text
