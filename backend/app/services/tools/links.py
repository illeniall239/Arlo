"""Extract hyperlinks from a web page."""

import logging
import re
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CareerAI/1.0)",
}


async def get_links(url: str, max_links: int = 40) -> list[dict]:
    """
    Fetch a page and return all unique absolute hyperlinks found in <a href>.
    Returns list of {url, text} dicts.
    """
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("get_links fetch failed for %s: %s", url, exc)
        return []

    seen: set[str] = set()
    results: list[dict] = []

    for m in re.finditer(r'<a\b[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        href = m.group(1).strip()
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()

        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_url = urljoin(url, href)
        if not abs_url.startswith("http") or abs_url in seen:
            continue

        seen.add(abs_url)
        results.append({"url": abs_url, "text": text})
        if len(results) >= max_links:
            break

    logger.info("get_links %s → %d links", url, len(results))
    return results
