"""
Background scheduler — fires scheduled scrape jobs when they come due.
Polls every 60 seconds. No external dependencies (no APScheduler, no cron lib).
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.schedule import Schedule
from app.models.scrape_job import JobStatus, ScrapeJob

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def start():
    """Start the scheduler background task. Call once from app lifespan."""
    global _task
    _task = asyncio.create_task(_loop())
    logger.info("Scheduler started")


def stop():
    """Cancel the scheduler background task."""
    global _task
    if _task:
        _task.cancel()
        _task = None


async def _loop():
    while True:
        await asyncio.sleep(60)
        try:
            await _fire_due()
        except Exception as exc:
            logger.error("Scheduler error: %s", exc, exc_info=True)


async def _fire_due():
    from app.services.job_runner import run_job

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Schedule).where(
                Schedule.enabled == True,
                Schedule.next_run_at <= now,
            )
        )
        schedules = result.scalars().all()
        if not schedules:
            return

        for schedule in schedules:
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

            logger.info(
                "Scheduler firing job %s for schedule %s (%s)",
                job.id, schedule.id, schedule.url,
            )

        job_ids = [j.id for j in db.new if isinstance(j, ScrapeJob)]
        await db.commit()

        for job_id in job_ids:
            asyncio.create_task(run_job(job_id))


# ── Diff computation ───────────────────────────────────────────────────────────

def compute_diff(old_records: list[dict], new_records: list[dict]) -> dict:
    """
    Compare two lists of records. Returns:
      { added, removed, added_records (up to 100), removed_records (up to 100) }

    Keyed by 'url' or 'profile_url' if present; otherwise by content hash.
    """
    def _key(r: dict) -> str:
        url = r.get("url") or r.get("profile_url") or r.get("link") or ""
        if url:
            return url
        return hashlib.md5(
            json.dumps(r, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    old_map = {_key(r): r for r in old_records}
    new_map = {_key(r): r for r in new_records}

    added   = [r for k, r in new_map.items() if k not in old_map]
    removed = [r for k, r in old_map.items() if k not in new_map]

    # Field-level changes for records present in both snapshots
    changed_records = []
    for k in old_map:
        if k not in new_map:
            continue
        old_r, new_r = old_map[k], new_map[k]
        changes = {}
        for field in set(old_r) | set(new_r):
            ov, nv = old_r.get(field), new_r.get(field)
            if ov != nv:
                changes[field] = {"from": ov, "to": nv}
        if changes:
            changed_records.append({"key": k, "changes": changes})

    return {
        "added":           len(added),
        "removed":         len(removed),
        "changed":         len(changed_records),
        "added_records":   added[:100],
        "removed_records": removed[:100],
        "changed_records": changed_records[:100],
    }
