"""
Agents router — CRUD + SSE stream for agentic scraper runs.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agent_run import AgentRun, AgentStatus
from app.schemas.agent import AgentCreateRequest, AgentRunDetail, AgentRunResponse
from app.services.agent_runner import run_agent
from app.utils import cancellation
from app.utils.sse_manager import sse_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=AgentRunResponse, status_code=201)
async def create_agent_run(
    body: AgentCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    run = AgentRun(goal=body.goal, status=AgentStatus.PENDING, context=body.context)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    background_tasks.add_task(run_agent, run.id)
    return run


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[AgentRunResponse])
async def list_agent_runs(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(AgentRun).order_by(desc(AgentRun.created_at)).limit(limit).offset(offset)
    )
    return res.scalars().all()


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{run_id}", response_model=AgentRunDetail)
async def get_agent_run(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Agent run not found")
    return run


# ── Cancel ────────────────────────────────────────────────────────────────────

@router.delete("/{run_id}", status_code=204)
async def cancel_agent_run(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Agent run not found")
    if run.status not in (AgentStatus.PENDING, AgentStatus.RUNNING):
        raise HTTPException(400, f"Cannot cancel a run in status '{run.status}'")
    cancellation.cancel(run_id)


# ── SSE Stream ────────────────────────────────────────────────────────────────

@router.get("/{run_id}/stream")
async def stream_agent_run(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Agent run not found")

    queue = await sse_manager.subscribe(run_id)

    async def event_stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue

                yield f"data: {json.dumps(event)}\n\n"

                if event.get("type") in ("done", "error"):
                    break
        finally:
            await sse_manager.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
