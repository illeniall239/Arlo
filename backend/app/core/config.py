from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-pro"

    TAVILY_API_KEY: str = ""

    UPSTASH_REDIS_URL: str = ""

    JINA_API_KEY: str = ""

    DATABASE_URL: str = "postgresql+asyncpg://localhost/arlo"
    DB_ECHO: bool = False

    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]


settings = Settings()
