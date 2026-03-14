"""
Jina AI Reader fetch service.

Fetches any URL via https://r.jina.ai/{url} and returns clean markdown.
Jina handles JS rendering, Cloudflare, and anti-bot protections automatically.
No fetcher type selection, no Playwright, no Scrapling — one call works on
any publicly accessible URL.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RAW_HTML_SIZE_LIMIT = 2 * 1024 * 1024   # 2 MB cap


async def fetch_jina(url: str) -> str:
    """
    Fetch a URL via Jina Reader (r.jina.ai) and return clean markdown.

    Returns markdown with links preserved as [text](url).
    Returns empty string on failure.
    """
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "X-Return-Format": "markdown",
    }
    if settings.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers=headers)
            resp.raise_for_status()
            content = resp.text
            logger.info("Jina fetch: %s → %d chars", url, len(content))
            return content
    except Exception as exc:
        logger.error("Jina fetch failed for %s: %s", url, exc)
        return ""


async def fetch_raw(url: str) -> str:
    """
    Fetch raw HTML using curl_cffi with Chrome TLS fingerprint impersonation.

    Bypasses TLS/JA3 fingerprint detection that blocks standard Python HTTP
    clients (requests, httpx) at the handshake level before any headers are
    checked. Returns raw HTML with all <script> tags intact — required for
    embedded data extraction (window.mosaic, __NEXT_DATA__, JSON-LD, etc).
    Returns empty string on failure (caller falls back to Jina).
    """
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome120") as session:
            resp = await session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Upgrade-Insecure-Requests": "1",
                },
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.text
            logger.info("fetch_raw: %s → %d chars", url, len(text))
            return text
    except Exception as exc:
        logger.warning("fetch_raw failed for %s: %s", url, exc)
        return ""


async def fetch_plain(url: str) -> str:
    """
    Plain HTTP GET — used for JSON API endpoints, RSS feeds, sitemaps.
    Does not use Jina; returns raw response body.
    Returns empty string on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CareerAI/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("fetch_plain failed for %s: %s", url, exc)
        return ""
