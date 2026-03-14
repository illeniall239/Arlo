import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schedule import Schedule
from app.models.scrape_job import JobStatus, ScrapeJob
from app.models.scrape_result import ScrapeResult

router = APIRouter()

VALID_INTERVALS = {60, 1440, 10080}  # hourly, daily, weekly


class ScheduleCreate(BaseModel):
    url: str
    prompt: str
    fetcher_type: str = "auto"
    max_pages: int = 5
    interval_minutes: int = 1440


class SchedulePatch(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None


@router.get("/")
async def list_schedules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Schedule).order_by(Schedule.created_at.desc())
    )
    schedules = result.scalars().all()

    out = []
    for s in schedules:
        # Attach last job status if available
        last_status = None
        if s.last_job_id:
            jr = await db.execute(
                select(ScrapeJob.status).where(ScrapeJob.id == s.last_job_id)
            )
            row = jr.one_or_none()
            last_status = row[0] if row else None

        out.append({
            "id":               s.id,
            "url":              s.url,
            "prompt":           s.prompt,
            "fetcher_type":     s.fetcher_type,
            "max_pages":        s.max_pages,
            "interval_minutes": s.interval_minutes,
            "enabled":          s.enabled,
            "last_run_at":      s.last_run_at,
            "next_run_at":      s.next_run_at,
            "last_job_id":      s.last_job_id,
            "last_status":      last_status,
            "created_at":       s.created_at,
        })
    return out


@router.post("/", status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if body.interval_minutes not in VALID_INTERVALS:
        raise HTTPException(
            status_code=422,
            detail=f"interval_minutes must be one of {sorted(VALID_INTERVALS)}",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    schedule = Schedule(
        url=body.url,
        prompt=body.prompt,
        fetcher_type=body.fetcher_type,
        max_pages=max(1, min(50, body.max_pages)),
        interval_minutes=body.interval_minutes,
        enabled=True,
        # First run fires immediately
        next_run_at=now,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    # Trigger the first run right away
    background_tasks.add_task(_run_schedule_now, schedule.id)

    return schedule


@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: SchedulePatch,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.enabled is not None:
        schedule.enabled = body.enabled
    if body.interval_minutes is not None:
        if body.interval_minutes not in VALID_INTERVALS:
            raise HTTPException(
                status_code=422,
                detail=f"interval_minutes must be one of {sorted(VALID_INTERVALS)}",
            )
        schedule.interval_minutes = body.interval_minutes
        # Recalculate next run based on last run
        if schedule.last_run_at:
            schedule.next_run_at = schedule.last_run_at + timedelta(
                minutes=body.interval_minutes
            )

    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(schedule)
    await db.commit()


@router.get("/{schedule_id}/runs")
async def schedule_runs(
    schedule_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Return the last N jobs spawned for a schedule (matched by URL + prompt hash)."""
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    import hashlib
    prompt_hash = hashlib.sha256(
        f"{schedule.prompt.strip()}{schedule.url.strip()}".encode()
    ).hexdigest()

    jobs_result = await db.execute(
        select(ScrapeJob)
        .where(ScrapeJob.prompt_hash == prompt_hash)
        .order_by(ScrapeJob.created_at.desc())
        .limit(limit)
    )
    jobs = jobs_result.scalars().all()

    out = []
    for job in jobs:
        # Attach diff if result exists
        diff = None
        if job.status == JobStatus.COMPLETED:
            rr = await db.execute(
                select(ScrapeResult).where(ScrapeResult.job_id == job.id)
            )
            sr = rr.scalar_one_or_none()
            if sr and sr.diff_json:
                try:
                    diff = json.loads(sr.diff_json)
                except Exception:
                    pass

        out.append({
            "id":           job.id,
            "status":       job.status,
            "created_at":   job.created_at,
            "completed_at": job.completed_at,
            "row_count":    job.result.row_count if job.result else None,
            "diff":         diff,
        })
    return out


# ── Internal helper ────────────────────────────────────────────────────────────

async def _run_schedule_now(schedule_id: str):
    """Create + fire a job for the given schedule immediately."""
    import asyncio
    import hashlib
    from app.core.database import AsyncSessionLocal
    from app.services.job_runner import run_job

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
        schedule = result.scalar_one_or_none()
        if not schedule:
            return

        job = ScrapeJob(
            prompt=schedule.prompt,
            url=schedule.url,
            fetcher_type=schedule.fetcher_type,
            max_pages=schedule.max_pages,
            prompt_hash=hashlib.sha256(
                f"{schedule.prompt.strip()}{schedule.url.strip()}".encode()
            ).hexdigest(),
            status=JobStatus.PENDING,
        )
        db.add(job)
        await db.flush()

        schedule.last_run_at = now
        schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
        schedule.last_job_id = job.id
        job_id = job.id

        await db.commit()

    asyncio.create_task(run_job(job_id))
