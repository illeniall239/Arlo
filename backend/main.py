import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, init_db
from app.core.limiter import limiter
from app.core.redis import close_redis
from app.routers import agents, jobs, results, stream, schedules as schedules_router
from app.routers import settings as settings_router
from app.services import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup validation ──────────────────────────────────────────────────
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required but not set")
    if not settings.TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set — web search will be unavailable")
    if not getattr(settings, "UPSTASH_REDIS_URL", ""):
        logger.warning("UPSTASH_REDIS_URL not set — Redis caching/pub-sub disabled")

    await init_db()

    # Idempotent column migrations for existing DBs
    async with engine.begin() as conn:
        for stmt in [
            "ALTER TABLE agent_runs ADD COLUMN formatted_response TEXT",
            "ALTER TABLE scrape_results ADD COLUMN diff_json TEXT",
            "ALTER TABLE scrape_jobs ADD COLUMN batch_id TEXT",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists

    # Warm up Redis connection so first request doesn't pay the connection cost
    from app.core.redis import get_redis
    await get_redis()

    scheduler.start()

    yield

    scheduler.stop()
    await close_redis()


app = FastAPI(
    title="AI Web Scraper",
    version="1.0.0",
    description="Natural language → structured scraped data, powered by Gemini + Jina Reader.",
    lifespan=lifespan,
)

# ── Rate limiting ──────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(jobs.router,               prefix="/jobs",      tags=["Jobs"])
app.include_router(stream.router,             prefix="/jobs",      tags=["Stream"])
app.include_router(results.router,            prefix="/results",   tags=["Results"])
app.include_router(settings_router.router,    prefix="/settings",  tags=["Settings"])
app.include_router(agents.router,             prefix="/agents",    tags=["Agents"])
app.include_router(schedules_router.router,   prefix="/schedules", tags=["Schedules"])


@app.get("/health", tags=["Health"])
async def health():
    from app.core.redis import get_redis

    redis_ok = False
    redis = await get_redis()
    if redis:
        try:
            await redis.ping()
            redis_ok = True
        except Exception:
            pass

    tavily_ok = bool(settings.TAVILY_API_KEY)
    gemini_ok = bool(settings.GEMINI_API_KEY)

    overall = "ok" if (gemini_ok) else "degraded"
    return {
        "status":    overall,
        "gemini":    gemini_ok,
        "tavily":    tavily_ok,
        "redis":     redis_ok,
    }
