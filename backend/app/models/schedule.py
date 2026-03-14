import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    fetcher_type: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Interval in minutes: 60 = hourly, 1440 = daily, 10080 = weekly
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ID of the most recently spawned job for this schedule
    last_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
