"""Dependency reachability checks for /readyz."""

import asyncio
from collections.abc import Awaitable, Callable

import asyncpg
import httpx
from redis.asyncio import Redis

from app.core.config import Settings

Check = Callable[[], Awaitable[None]]


async def check_redis(settings: Settings) -> None:
    """Ping Redis."""
    url = settings.redis_url.get_secret_value()
    if not url:
        raise RuntimeError("redis not configured")
    client = Redis.from_url(url)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_postgres(settings: Settings) -> None:
    """Run SELECT 1 against Postgres."""
    url = settings.database_url.get_secret_value()
    if not url:
        raise RuntimeError("database not configured")
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()


async def check_azure_openai(settings: Settings, client: httpx.AsyncClient) -> None:
    """Confirm the Azure OpenAI endpoint answers HTTP (any status means reachable)."""
    if not settings.azure_openai_endpoint:
        raise RuntimeError("azure openai not configured")
    await client.get(settings.azure_openai_endpoint)


def build_checks(settings: Settings, client: httpx.AsyncClient) -> dict[str, Check]:
    """Default readiness checks."""
    return {
        "redis": lambda: check_redis(settings),
        "postgres": lambda: check_postgres(settings),
        "azure_openai": lambda: check_azure_openai(settings, client),
    }


async def run_check(check: Check, timeout_seconds: float) -> bool:
    """Run one check with a timeout; True when healthy."""
    try:
        async with asyncio.timeout(timeout_seconds):
            await check()
    except Exception:
        return False
    return True
