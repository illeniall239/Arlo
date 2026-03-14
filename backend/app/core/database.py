from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    # Import all models so their tables are registered on Base.metadata
    import app.models.scrape_job      # noqa: F401
    import app.models.scrape_result   # noqa: F401
    import app.models.settings        # noqa: F401
    import app.models.agent_run       # noqa: F401
    import app.models.schedule        # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Add columns introduced after initial schema (safe to run multiple times)
        for sql in [
            "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS context TEXT",
        ]:
            await conn.execute(__import__("sqlalchemy").text(sql))
