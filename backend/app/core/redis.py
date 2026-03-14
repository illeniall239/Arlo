"""
Shared async Redis client (Upstash or any Redis).

Falls back gracefully if UPSTASH_REDIS_URL is not set or the server
is unreachable — callers must handle `None` returns.
"""

import logging

logger = logging.getLogger(__name__)

_redis = None


async def get_redis():
    """Return the shared async Redis client, or None if unavailable."""
    global _redis

    # Ping existing connection — reset if it has dropped
    if _redis is not None:
        try:
            await _redis.ping()
            return _redis
        except Exception:
            logger.warning("Redis connection lost — reconnecting")
            _redis = None

    from app.core.config import settings

    url = getattr(settings, "UPSTASH_REDIS_URL", "")
    if not url:
        return None

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(url, decode_responses=True)
        await client.ping()
        _redis = client
        logger.info("Redis connected (%s)", url.split("@")[-1] if "@" in url else url)
    except Exception as exc:
        logger.warning("Redis unavailable — caching/pub-sub disabled: %s", exc)
        _redis = None

    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
