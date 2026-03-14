import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limiter import limiter
from app.models.scrape_job import FetcherType, JobStatus, ScrapeJob
from app.schemas.job import (
    BatchCreateRequest,
    BatchCreateResponse,
    JobCreateRequest,
    JobDetailResponse,
    JobSummaryResponse,
    PaginatedJobsResponse,
)
from app.services.job_runner import run_job
from app.utils import cancellation

router = APIRouter()


def _normalize_url(url: str) -> str:
    """
    Sanitize a user-supplied URL before storing or fetching.
    - Strip leading/trailing whitespace and accidental newlines
    - Ensure a scheme is present (default https)
    - Remove URL-encoded whitespace (%20, +) from the end of the path
    """
    from urllib.parse import urlparse, urlunparse, unquote
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # Decode any percent-encoding so we can clean the raw string
    url = unquote(url).strip()
    # Re-strip in case decoding revealed trailing spaces
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip()
    return urlunparse(parsed._replace(path=clean_path))


def _hash_prompt(prompt: str, url: str) -> str:
    return hashlib.sha256(f"{prompt.strip()}{_normalize_url(url)}".encode()).hexdigest()


@router.post("/", status_code=201, response_model=JobDetailResponse)
@limiter.limit("10/minute")
async def create_job(
    request: Request,
    body: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    url = _normalize_url(body.url)
    prompt_hash = _hash_prompt(body.prompt, url)

    job = ScrapeJob(
        prompt=body.prompt,
        url=url,
        fetcher_type=body.fetcher_type,
        max_pages=max(1, min(50, body.max_pages)),
        prompt_hash=prompt_hash,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(run_job, job.id)

    return job


@router.post("/batch", status_code=201, response_model=BatchCreateResponse)
@limiter.limit("5/minute")
async def create_batch(
    request: Request,
    body: BatchCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    batch_id = str(uuid.uuid4())
    jobs = []
    for raw_url in body.urls:
        url = _normalize_url(raw_url)
        job = ScrapeJob(
            prompt=body.prompt,
            url=url,
            fetcher_type=body.fetcher_type,
            max_pages=max(1, min(50, body.max_pages)),
            prompt_hash=_hash_prompt(body.prompt, url),
            batch_id=batch_id,
            status=JobStatus.PENDING,
        )
        db.add(job)
        jobs.append(job)

    await db.commit()
    for job in jobs:
        await db.refresh(job)
        background_tasks.add_task(run_job, job.id)

    return BatchCreateResponse(
        batch_id=batch_id,
        jobs=[JobDetailResponse.model_validate(j) for j in jobs],
    )


@router.get("/batch/{batch_id}")
async def get_batch(batch_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScrapeJob)
        .where(ScrapeJob.batch_id == batch_id)
        .order_by(ScrapeJob.created_at.asc())
    )
    jobs = result.scalars().all()
    if not jobs:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {
        "batch_id": batch_id,
        "jobs": [JobSummaryResponse.model_validate(j) for j in jobs],
    }


@router.get("/", response_model=PaginatedJobsResponse)
async def list_jobs(
    status: JobStatus | None = None,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    batch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    page_size = min(page_size, 100)
    query = select(ScrapeJob).order_by(ScrapeJob.created_at.desc())

    if status:
        query = query.where(ScrapeJob.status == status)
    if search:
        query = query.where(ScrapeJob.prompt.ilike(f"%{search}%"))
    if batch_id:
        query = query.where(ScrapeJob.batch_id == batch_id)

    count_result = await db.execute(select(ScrapeJob.id).filter(query.whereclause))  # type: ignore[arg-type]
    total = len(count_result.all())

    offset = (page - 1) * page_size
    paginated = await db.execute(query.offset(offset).limit(page_size))
    jobs = paginated.scalars().all()

    return PaginatedJobsResponse(
        data=[JobSummaryResponse.model_validate(j) for j in jobs],
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),
        },
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}", status_code=204)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=409, detail="Job is already in a terminal state")

    cancellation.cancel(job_id)
    job.status = JobStatus.CANCELLED
    await db.commit()


@router.post("/{job_id}/retry", status_code=201, response_model=JobDetailResponse)
async def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Job not found")

    new_job = ScrapeJob(
        prompt=original.prompt,
        url=original.url,
        fetcher_type=original.fetcher_type,
        max_pages=original.max_pages,
        prompt_hash=original.prompt_hash,
        retry_count=original.retry_count + 1,
        parent_job_id=original.parent_job_id or original.id,
        status=JobStatus.PENDING,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    background_tasks.add_task(run_job, new_job.id)
    return new_job


@router.get("/{job_id}/results")
async def get_job_results(job_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.scrape_result import ScrapeResult

    result = await db.execute(
        select(ScrapeResult).where(ScrapeResult.job_id == job_id)
    )
    scrape_result = result.scalar_one_or_none()
    if not scrape_result:
        raise HTTPException(status_code=404, detail="Results not found for this job")

    return {
        "id": scrape_result.id,
        "job_id": scrape_result.job_id,
        "structured_data": json.loads(scrape_result.structured_data),
        "row_count": scrape_result.row_count,
        "schema_detected": json.loads(scrape_result.schema_detected)
        if scrape_result.schema_detected
        else [],
        "diff": json.loads(scrape_result.diff_json) if scrape_result.diff_json else None,
        "created_at": scrape_result.created_at,
    }
