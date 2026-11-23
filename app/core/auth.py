"""Bearer-token authentication.

`user_id` is derived from a validated token only. Two validators exist:
`EntraTokenValidator` (production) and `LocalDevTokenValidator` (local/test only).
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWK

from app.core.config import AuthMode, Settings
from app.core.telemetry import get_tracer

LOCAL_DEV_ISSUER = "insurebot-local-dev"
LOCAL_DEV_AUDIENCE = "insurebot-local-dev"
_ENTRA_ALGORITHMS = ["RS256"]
_MIN_JWKS_REFRESH_SECONDS = 30.0

_tracer = get_tracer(__name__)


class AuthError(Exception):
    """Raised when a token is missing or invalid. The message is safe to log, not to return."""


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller."""

    user_id: str


class TokenValidator(Protocol):
    """Validates a raw bearer token."""

    async def validate(self, token: str) -> Principal: ...


class JwksCache:
    """Caches a JWKS document with a TTL; refreshes on unknown `kid` (rate limited)."""

    def __init__(self, url: str, client: httpx.AsyncClient, ttl_seconds: int) -> None:
        self._url = url
        self._client = client
        self._ttl = ttl_seconds
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> PyJWK:
        """Return the signing key for `kid`, refreshing the cache when needed."""
        age = None if self._fetched_at is None else time.monotonic() - self._fetched_at
        stale = age is None or age >= self._ttl
        unknown = kid not in self._keys and age is not None and age > _MIN_JWKS_REFRESH_SECONDS
        if stale or unknown:
            await self._refresh()
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthError("unknown signing key") from None

    async def _refresh(self) -> None:
        async with self._lock:
            resp = await self._client.get(self._url)
            resp.raise_for_status()
            self._keys = {k["kid"]: PyJWK(k) for k in resp.json().get("keys", []) if "kid" in k}
            self._fetched_at = time.monotonic()


def _extract_user_id(claims: dict[str, Any]) -> str:
    user_id = claims.get("oid") or claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("token has no subject")
    return user_id


class EntraTokenValidator:
    """Validates Entra ID access tokens: signature (JWKS), issuer, audience, expiry."""

    def __init__(self, settings: Settings, jwks: JwksCache) -> None:
        self._issuer = settings.entra_issuer
        self._audience = settings.entra_audience
        self._leeway = settings.jwt_leeway_seconds
        self._jwks = jwks

    async def validate(self, token: str) -> Principal:
        """Return the principal for a valid token or raise AuthError."""
        with _tracer.start_as_current_span("auth.validate"):
            try:
                header = jwt.get_unverified_header(token)
                kid = header.get("kid")
                if not kid:
                    raise AuthError("missing kid")
                key = await self._jwks.get_key(kid)
                claims = jwt.decode(
                    token,
                    key.key,
                    algorithms=_ENTRA_ALGORITHMS,
                    issuer=self._issuer,
                    audience=self._audience,
                    leeway=self._leeway,
                    options={"require": ["exp", "iss", "aud"]},
                )
            except jwt.PyJWTError as exc:
                raise AuthError(f"invalid token: {type(exc).__name__}") from exc
            except httpx.HTTPError as exc:
                raise AuthError("jwks unavailable") from exc
            return Principal(user_id=_extract_user_id(claims))


class LocalDevTokenValidator:
    """HS256 validator for local development and tests. Never constructed in production."""

    def __init__(self, settings: Settings) -> None:
        self._key = settings.local_dev_signing_key.get_secret_value()

    async def validate(self, token: str) -> Principal:
        """Return the principal for a valid local-dev token or raise AuthError."""
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=["HS256"],
                issuer=LOCAL_DEV_ISSUER,
                audience=LOCAL_DEV_AUDIENCE,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {type(exc).__name__}") from exc
        return Principal(user_id=_extract_user_id(claims))


def mint_local_dev_token(settings: Settings, user_id: str, ttl_seconds: int = 3600) -> str:
    """Create a signed test token. Refuses unless local-dev mode is active."""
    if settings.auth_mode is not AuthMode.LOCAL_DEV:
        raise RuntimeError("local-dev tokens can only be minted in LOCAL_DEV auth mode")
    now = int(time.time())
    payload = {
        "oid": user_id,
        "iss": LOCAL_DEV_ISSUER,
        "aud": LOCAL_DEV_AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, settings.local_dev_signing_key.get_secret_value(), algorithm="HS256")


def build_validator(settings: Settings, client: httpx.AsyncClient) -> TokenValidator:
    """Pick the validator for the configured auth mode."""
    if settings.auth_mode is AuthMode.LOCAL_DEV:
        return LocalDevTokenValidator(settings)
    jwks = JwksCache(settings.entra_jwks_url, client, settings.jwks_cache_ttl_seconds)
    return EntraTokenValidator(settings, jwks)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_principal(request: Request) -> Principal:
    """FastAPI dependency: authenticate the request from its Authorization header."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    validator: TokenValidator = request.app.state.validator
    try:
        return await validator.validate(token.strip())
    except AuthError:
        raise _unauthorized() from None
