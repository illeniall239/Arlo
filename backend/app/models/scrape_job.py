import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(str, enum.Enum):
    PENDING      = "pending"
    PLANNING     = "planning"
    RUNNING      = "running"
    STRUCTURING  = "structuring"
    COMPLETED    = "completed"
    FAILED       = "failed"
    CANCELLED    = "cancelled"


class FetcherType(str, enum.Enum):
    FETCHER  = "Fetcher"
    STEALTHY = "StealthyFetcher"
    DYNAMIC  = "DynamicFetcher"
    AUTO     = "auto"


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False
    )
    fetcher_type: Mapped[FetcherType] = mapped_column(
        SAEnum(FetcherType), default=FetcherType.AUTO, nullable=False
    )
    # JSON-encoded list of selector objects from Gemini
    selectors: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded pagination config from Gemini
    pagination_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_pages: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Points to the original job if this is a retry/rerun
    parent_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Groups jobs created together in a batch
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # SHA256(prompt + url) for deduplication checks
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    result: Mapped["ScrapeResult"] = relationship(  # noqa: F821
        "ScrapeResult",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )
