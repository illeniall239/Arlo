from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limiter import limiter
from app.models.scrape_result import ScrapeResult
from app.services.export import to_csv_bytes, to_json_bytes

router = APIRouter()


@router.get("/{result_id}/export")
@limiter.limit("30/minute")
async def export_result(
    request: Request,
    result_id: str,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScrapeResult).where(ScrapeResult.id == result_id)
    )
    scrape_result = result.scalar_one_or_none()
    if not scrape_result:
        raise HTTPException(status_code=404, detail="Result not found")

    if format == "csv":
        content = to_csv_bytes(scrape_result.structured_data)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="scrape_{result_id}.csv"'
            },
        )
    else:
        content = to_json_bytes(scrape_result.structured_data)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="scrape_{result_id}.json"'
            },
        )
