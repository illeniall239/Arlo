import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentStatus(str, enum.Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id:           Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    goal:         Mapped[str]           = mapped_column(Text, nullable=False)
    status:       Mapped[AgentStatus]   = mapped_column(SAEnum(AgentStatus), default=AgentStatus.PENDING, nullable=False)
    # JSON array of {iteration, tool, args, result_preview, timestamp}
    trace:        Mapped[str | None]    = mapped_column(Text, nullable=True)
    # JSON array of final extracted records
    result:       Mapped[str | None]    = mapped_column(Text, nullable=True)
    summary:      Mapped[str | None]    = mapped_column(Text, nullable=True)
    iterations:   Mapped[int]           = mapped_column(Integer, default=0, nullable=False)
    created_at:   Mapped[datetime]      = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    error:              Mapped[str | None]    = mapped_column(Text, nullable=True)
    formatted_response: Mapped[str | None]    = mapped_column(Text, nullable=True)
    context:            Mapped[str | None]    = mapped_column(Text, nullable=True)  # prior conversation context
