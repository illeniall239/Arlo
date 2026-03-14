"""
Exponential backoff decorator for async functions.

Usage:
    @async_retry(max_attempts=3, exceptions=(httpx.NetworkError,))
    async def fetch_something():
        ...
"""

import asyncio
import random
from functools import wraps
from typing import Callable, Type


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    jitter = random.uniform(0, delay * 0.1)
                    wait = delay + jitter
                    await asyncio.sleep(wait)
                    delay = min(delay * 2, max_delay)

        return wrapper

    return decorator
