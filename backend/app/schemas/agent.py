from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.agent_run import AgentStatus


class AgentCreateRequest(BaseModel):
    goal: str
    context: str | None = None  # prior conversation history for multi-turn


class AgentRunResponse(BaseModel):
    id:           str
    goal:         str
    status:       AgentStatus
    summary:      str | None
    iterations:   int
    created_at:   datetime
    completed_at: datetime | None
    error:        str | None

    model_config = {"from_attributes": True}


class AgentRunDetail(AgentRunResponse):
    trace:              str | None  # raw JSON string
    result:             str | None  # raw JSON string
    formatted_response: str | None  # Markdown narrative
