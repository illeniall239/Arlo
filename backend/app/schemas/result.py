from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ResultResponse(BaseModel):
    id: str
    job_id: str
    structured_data: list[dict[str, Any]]
    row_count: int
    schema_detected: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}
