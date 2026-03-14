"""
DuckDuckGo web search — no API key required.
Uses the DDG HTML endpoint via httpx.
"""

import logging
import re
from urllib.parse import quote_plus, unquote

import httpx

logger = logging.getLogger(__name__)

DDG_URL = "https://html.duckduckgo.com/html/?q={query}&kl=us-en"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


async def web_search(query: str, num_results: int = 8) -> list[dict]:
    """Fetch DuckDuckGo HTML results and parse title/url/snippet."""
    url = DDG_URL.format(query=quote_plus(query))
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("DDG fetch failed: %s", exc)
        return []

    results: list[dict] = []
    seen: set[str] = set()

    # Parse result links — DDG encodes real URL as ?uddg=...
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL
    ):
        if len(results) >= num_results:
            break
        href = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        # Decode real URL from ?uddg= param
        ud = re.search(r'uddg=([^&]+)', href)
        real_url = unquote(ud.group(1)) if ud else href
        if not real_url.startswith("http") or real_url in seen:
            continue
        seen.add(real_url)
        results.append({"url": real_url, "title": title, "snippet": ""})

    # Attach snippets
    snippets = re.findall(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, re.IGNORECASE | re.DOTALL
    )
    for i, snip in enumerate(snippets):
        if i < len(results):
            results[i]["snippet"] = re.sub(r'<[^>]+>', '', snip).strip()

    logger.info("DDG search '%s' → %d results", query, len(results))
    return results
