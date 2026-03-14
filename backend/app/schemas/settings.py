from pydantic import BaseModel


class SettingsResponse(BaseModel):
    proxy_list: list[str]
    default_fetcher: str
    concurrency_limit: int
    rate_limit_delay: float
    respect_robots_txt: bool

    model_config = {"from_attributes": True}


class SettingsUpdateRequest(BaseModel):
    proxy_list: list[str] | None = None
    default_fetcher: str | None = None
    concurrency_limit: int | None = None
    rate_limit_delay: float | None = None
    respect_robots_txt: bool | None = None
