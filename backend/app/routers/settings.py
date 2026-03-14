import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.settings import AppSettings
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest

router = APIRouter()


async def _get_or_create_settings(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    settings_row = result.scalar_one_or_none()
    if not settings_row:
        settings_row = AppSettings(id=1)
        db.add(settings_row)
        await db.commit()
        await db.refresh(settings_row)
    return settings_row


@router.get("/", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    s = await _get_or_create_settings(db)
    return SettingsResponse(
        proxy_list=json.loads(s.proxy_list) if s.proxy_list else [],
        default_fetcher=s.default_fetcher,
        concurrency_limit=s.concurrency_limit,
        rate_limit_delay=s.rate_limit_delay,
        respect_robots_txt=s.respect_robots_txt,
    )


@router.put("/", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    s = await _get_or_create_settings(db)

    if body.proxy_list is not None:
        s.proxy_list = json.dumps(body.proxy_list)
    if body.default_fetcher is not None:
        s.default_fetcher = body.default_fetcher
    if body.concurrency_limit is not None:
        s.concurrency_limit = body.concurrency_limit
    if body.rate_limit_delay is not None:
        s.rate_limit_delay = body.rate_limit_delay
    if body.respect_robots_txt is not None:
        s.respect_robots_txt = body.respect_robots_txt

    await db.commit()
    await db.refresh(s)

    return SettingsResponse(
        proxy_list=json.loads(s.proxy_list) if s.proxy_list else [],
        default_fetcher=s.default_fetcher,
        concurrency_limit=s.concurrency_limit,
        rate_limit_delay=s.rate_limit_delay,
        respect_robots_txt=s.respect_robots_txt,
    )
