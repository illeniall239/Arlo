import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScrapeResult(Base):
    __tablename__ = "scrape_results"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("scrape_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Raw HTML — nullable, capped at 500KB before insert
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array string of cleaned structured records (Gemini output)
    structured_data: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # JSON array of field names Gemini detected in the data
    schema_detected: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON diff vs previous result for same URL: {added, removed, added_records, removed_records}
    diff_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    job: Mapped["ScrapeJob"] = relationship(  # noqa: F821
        "ScrapeJob",
        back_populates="result",
    )
