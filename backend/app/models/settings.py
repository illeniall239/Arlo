from sqlalchemy import String, Text, Integer, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    # Singleton row — always id=1
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # JSON array of proxy URL strings, e.g. ["http://user:pass@host:port"]
    proxy_list: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_fetcher: Mapped[str] = mapped_column(
        String(32), default="auto", nullable=False
    )
    concurrency_limit: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )
    # Minimum seconds between requests to the same domain
    rate_limit_delay: Mapped[float] = mapped_column(
        Float, default=2.0, nullable=False
    )
    respect_robots_txt: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
