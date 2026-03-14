import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from app.utils.sse_manager import sse_manager

router = APIRouter()
logger = logging.getLogger(__name__)

KEEPALIVE_INTERVAL = 25  # seconds


@router.get("/{job_id}/stream")
async def stream_job_status(job_id: str, request: Request):
    """
    SSE endpoint: streams real-time job status events to the browser.

    Event types:
      status   — text log line (message field)
      progress — rows_found count update
      done     — job completed (result_id, rows)
      error    — job failed (detail)

    Keepalive comments (: keepalive) sent every 25s to prevent proxy timeouts.
    """

    async def event_generator():
        queue = await sse_manager.subscribe(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("SSE client disconnected for job %s", job_id)
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            await sse_manager.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
