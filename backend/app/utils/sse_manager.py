"""
SSEManager — pub/sub bridge between background tasks and SSE endpoints.

Redis mode (default when UPSTASH_REDIS_URL is set):
  publish()   → Redis PUBLISH sse:{job_id}
                + RPUSH sse_buf:{job_id} for late-join replay (TTL 5 min)
  subscribe() → replay buffered events, then Redis SUBSCRIBE sse:{job_id}

In-process fallback (when Redis is unavailable):
  publish()   → put_nowait into each subscriber's asyncio.Queue
  subscribe() → register asyncio.Queue directly

The interface is the same in both modes: callers get an asyncio.Queue and
await events from it.  stream.py and agents.py use `await sse_manager.subscribe(job_id)`.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

_BUF_KEY      = "sse_buf:{}"   # RPUSH buffer for late-join replay
_BUF_TTL      = 300            # 5 minutes
_BUF_MAX_LEN  = 500            # hard cap to prevent unbounded growth


class SSEManager:
    def __init__(self) -> None:
        # In-process fallback queues (used when Redis is unavailable)
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        # Active Redis listener tasks keyed by (job_id, queue id)
        self._tasks:  dict[tuple[str, int], asyncio.Task] = {}

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        """
        Subscribe to events for job_id.  Returns an asyncio.Queue that will
        receive event dicts.  Always await this before iterating.

        If Redis is available, buffered events are replayed first so late-joining
        clients don't miss events published before they connected.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=500)

        from app.core.redis import get_redis
        redis = await get_redis()

        if redis:
            # Replay any events buffered before this client connected
            await self._replay_buffer(job_id, q, redis)
            task = asyncio.create_task(self._redis_listener(job_id, q, redis))
            self._tasks[(job_id, id(q))] = task
        else:
            self._queues[job_id].append(q)

        return q

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        """Clean up when the SSE client disconnects."""
        key = (job_id, id(queue))
        task = self._tasks.pop(key, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            self._queues[job_id].remove(queue)
        except ValueError:
            pass
        if not self._queues[job_id]:
            self._queues.pop(job_id, None)

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers for job_id."""
        from app.core.redis import get_redis
        redis = await get_redis()

        if redis:
            payload = json.dumps(event)
            try:
                buf_key = _BUF_KEY.format(job_id)
                pipe = redis.pipeline()
                pipe.rpush(buf_key, payload)
                pipe.ltrim(buf_key, -_BUF_MAX_LEN, -1)   # keep last N
                pipe.expire(buf_key, _BUF_TTL)
                pipe.publish(f"sse:{job_id}", payload)
                await pipe.execute()
                return
            except Exception as exc:
                logger.warning("Redis publish failed for job %s: %s — using in-process", job_id, exc)

        # In-process fallback
        for q in list(self._queues.get(job_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # ── internals ─────────────────────────────────────────────────────────────

    async def _replay_buffer(
        self, job_id: str, queue: asyncio.Queue, redis: Any
    ) -> None:
        """Drain the replay buffer into the queue before starting the live listener."""
        buf_key = _BUF_KEY.format(job_id)
        try:
            items = await redis.lrange(buf_key, 0, -1)
            for raw in items:
                try:
                    await queue.put(json.loads(raw))
                except Exception:
                    pass
            if items:
                logger.debug("SSE replay %d buffered events for job %s", len(items), job_id)
        except Exception as exc:
            logger.warning("SSE replay failed for job %s: %s", job_id, exc)

    async def _redis_listener(
        self, job_id: str, queue: asyncio.Queue, redis: Any
    ) -> None:
        """Background task: forward live Redis pub/sub messages into the local queue."""
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"sse:{job_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                    await queue.put(event)
                except Exception as exc:
                    logger.warning("SSE Redis listener parse error: %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("SSE Redis listener error for job %s: %s", job_id, exc)
        finally:
            try:
                await pubsub.unsubscribe(f"sse:{job_id}")
                await pubsub.aclose()
            except Exception:
                pass


# Module-level singleton — imported by both job_runner and stream router
sse_manager = SSEManager()
