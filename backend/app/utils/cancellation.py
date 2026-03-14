"""
CancellationRegistry — cooperative cancellation for background scrape jobs.

The background task checks cancel_event.is_set() between pipeline stages.
The DELETE /jobs/{id} endpoint sets the event to signal cancellation.

MVP: in-process dict. Scale: swap to Redis SETEX keys.
"""

import asyncio

_registry: dict[str, asyncio.Event] = {}


def register(job_id: str) -> asyncio.Event:
    event = asyncio.Event()
    _registry[job_id] = event
    return event


def cancel(job_id: str) -> bool:
    """Signal cancellation. Returns True if the job was found."""
    event = _registry.get(job_id)
    if event:
        event.set()
        return True
    return False


def is_cancelled(job_id: str) -> bool:
    event = _registry.get(job_id)
    return event.is_set() if event else False


def cleanup(job_id: str) -> None:
    _registry.pop(job_id, None)
