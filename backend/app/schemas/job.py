import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.models.scrape_job import FetcherType, JobStatus


_DEFAULT_PROMPT = "Extract all structured data, links, and meaningful content from this page."


class JobCreateRequest(BaseModel):
    prompt: str = _DEFAULT_PROMPT
    url: str
    fetcher_type: FetcherType = FetcherType.AUTO
    max_pages: int = 5

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class BatchCreateRequest(BaseModel):
    prompt: str
    urls: list[str]
    fetcher_type: FetcherType = FetcherType.AUTO
    max_pages: int = 5

    @field_validator("prompt")
    @classmethod
    def prompt_min_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Prompt must be at least 10 characters")
        return v.strip()

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one URL is required")
        if len(v) > 20:
            raise ValueError("Maximum 20 URLs per batch")
        for url in v:
            if not url.strip().startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL: {url}")
        return [u.strip() for u in v]


class JobSummaryResponse(BaseModel):
    id: str
    prompt: str
    url: str
    status: JobStatus
    fetcher_type: FetcherType
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    retry_count: int
    batch_id: str | None = None

    model_config = {"from_attributes": True}


class JobDetailResponse(JobSummaryResponse):
    selectors: str | None  # raw JSON string
    pagination_strategy: str | None
    error: str | None
    parent_job_id: str | None


class BatchCreateResponse(BaseModel):
    batch_id: str
    jobs: list[JobDetailResponse]


class PaginatedJobsResponse(BaseModel):
    data: list[JobSummaryResponse]
    meta: dict[str, Any]
