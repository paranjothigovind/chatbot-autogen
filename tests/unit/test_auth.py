import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import jwt
import pytest
import respx
from app.core.auth import (
    LOCAL_DEV_AUDIENCE,
    LOCAL_DEV_ISSUER,
    AuthError,
    EntraTokenValidator,
    JwksCache,
    LocalDevTokenValidator,
    build_validator,
    mint_local_dev_token,
)
from app.core.config import AuthMode, Environment, Settings
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

JWKS_URL = "https://login.example.invalid/keys"
ISSUER = "https://login.example.invalid/tenant/v2.0"
AUDIENCE = "api://insurebot-test"
KID = "kid-1"


def _entra_settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        auth_mode=AuthMode.ENTRA,
        entra_tenant_id="tenant",
        entra_audience=AUDIENCE,
        entra_issuer=ISSUER,
        entra_jwks_url=JWKS_URL,
    )


def _keypair() -> tuple[Any, dict[str, Any]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update(kid=KID, use="sig", alg="RS256")
    return private, jwk


PRIVATE, JWK = _keypair()
OTHER_PRIVATE, _ = _keypair()


def _token(key: Any = PRIVATE, **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {"oid": "user-a", "iss": ISSUER, "aud": AUDIENCE, "exp": now + 600}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
async def validator() -> AsyncIterator[EntraTokenValidator]:
    async with httpx.AsyncClient() as client:
        yield EntraTokenValidator(_entra_settings(), JwksCache(JWKS_URL, client, 3600))


@pytest.fixture
def jwks_route() -> Iterator[respx.Route]:
    with respx.mock(assert_all_called=False) as mock:
        yield mock.get(JWKS_URL).respond(json={"keys": [JWK]})


async def test_valid_token(validator: EntraTokenValidator, jwks_route: respx.Route) -> None:
    assert (await validator.validate(_token())).user_id == "user-a"


async def test_sub_used_when_no_oid(
    validator: EntraTokenValidator, jwks_route: respx.Route
) -> None:
    assert (await validator.validate(_token(oid=None, sub="sub-1"))).user_id == "sub-1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 3600},
        {"iss": "https://evil.invalid"},
        {"aud": "api://other"},
        {"exp": None},
        {"oid": None},
    ],
)
async def test_bad_claims_rejected(
    validator: EntraTokenValidator, jwks_route: respx.Route, overrides: dict[str, Any]
) -> None:
    with pytest.raises(AuthError):
        await validator.validate(_token(**overrides))


async def test_bad_signature_rejected(
    validator: EntraTokenValidator, jwks_route: respx.Route
) -> None:
    with pytest.raises(AuthError):
        await validator.validate(_token(key=OTHER_PRIVATE))


async def test_hs256_confusion_rejected(
    validator: EntraTokenValidator, jwks_route: respx.Route
) -> None:
    forged = jwt.encode(
        {"oid": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        "secret" * 8,
        algorithm="HS256",
        headers={"kid": KID},
    )
    with pytest.raises(AuthError):
        await validator.validate(forged)


async def test_garbage_and_missing_kid_rejected(
    validator: EntraTokenValidator, jwks_route: respx.Route
) -> None:
    with pytest.raises(AuthError):
        await validator.validate("not-a-jwt")
    no_kid = jwt.encode({"oid": "x"}, PRIVATE, algorithm="RS256")
    with pytest.raises(AuthError):
        await validator.validate(no_kid)


async def test_unknown_kid_rejected(
    validator: EntraTokenValidator, jwks_route: respx.Route
) -> None:
    token = jwt.encode(
        {"oid": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        PRIVATE,
        algorithm="RS256",
        headers={"kid": "other"},
    )
    with pytest.raises(AuthError):
        await validator.validate(token)


async def test_jwks_cached(validator: EntraTokenValidator, jwks_route: respx.Route) -> None:
    await validator.validate(_token())
    await validator.validate(_token())
    assert jwks_route.call_count == 1


async def test_jwks_refetched_after_ttl(jwks_route: respx.Route) -> None:
    async with httpx.AsyncClient() as client:
        v = EntraTokenValidator(_entra_settings(), JwksCache(JWKS_URL, client, 0))
        await v.validate(_token())
        await v.validate(_token())
    assert jwks_route.call_count == 2


async def test_jwks_outage_is_auth_error() -> None:
    with respx.mock() as mock:
        mock.get(JWKS_URL).respond(status_code=503)
        async with httpx.AsyncClient() as client:
            v = EntraTokenValidator(_entra_settings(), JwksCache(JWKS_URL, client, 3600))
            with pytest.raises(AuthError):
                await v.validate(_token())


async def test_local_dev_roundtrip(local_settings: Settings) -> None:
    token = mint_local_dev_token(local_settings, "dev-user")
    assert (await LocalDevTokenValidator(local_settings).validate(token)).user_id == "dev-user"


async def test_local_dev_rejects_wrong_key_expired_and_entra_style(
    local_settings: Settings,
) -> None:
    v = LocalDevTokenValidator(local_settings)
    now = int(time.time())
    base = {"oid": "u", "iss": LOCAL_DEV_ISSUER, "aud": LOCAL_DEV_AUDIENCE, "exp": now + 60}
    key = local_settings.local_dev_signing_key.get_secret_value()
    with pytest.raises(AuthError):
        await v.validate(jwt.encode(base, "x" * 40, algorithm="HS256"))
    with pytest.raises(AuthError):
        await v.validate(jwt.encode({**base, "exp": now - 60}, key, algorithm="HS256"))
    with pytest.raises(AuthError):
        await v.validate(_token())


def test_mint_refused_outside_local_dev() -> None:
    with pytest.raises(RuntimeError):
        mint_local_dev_token(_entra_settings(), "u")


def test_build_validator_picks_by_mode(local_settings: Settings) -> None:
    client = httpx.AsyncClient()
    assert isinstance(build_validator(local_settings, client), LocalDevTokenValidator)
    assert isinstance(build_validator(_entra_settings(), client), EntraTokenValidator)


def test_endpoint_requires_valid_token(local_settings: Settings) -> None:
    with TestClient(create_app(local_settings, readiness_checks={})) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/me", headers={"Authorization": "Basic abc"}).status_code == 401
        assert client.get("/api/me", headers={"Authorization": "Bearer junk"}).status_code == 401
        token = mint_local_dev_token(local_settings, "user-a")
        ok = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200
        assert ok.json() == {"user_id": "user-a"}


def test_user_id_not_taken_from_request(local_settings: Settings) -> None:
    with TestClient(create_app(local_settings, readiness_checks={})) as client:
        token = mint_local_dev_token(local_settings, "user-a")
        resp = client.get(
            "/api/me?user_id=user-b",
            headers={"Authorization": f"Bearer {token}", "X-User-Id": "user-b"},
        )
        assert resp.json() == {"user_id": "user-a"}
