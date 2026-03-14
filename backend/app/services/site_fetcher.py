"""
site_fetcher.py — Smart Fetch Orchestrator

Single entry point for all web fetching in the agent pipeline.

Cascade (cheapest/fastest first):
  1. API Discovery   — probe JSON API endpoints for the domain
  2. Feed Discovery  — detect RSS / Atom feeds from <link> tags
  3. Jina Reader     — universal fallback (handles JS, Cloudflare, anti-bot)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_MAX_JSON_CHARS = 300_000   # raw JSON from API
_MAX_TEXT_CHARS = 200_000   # text sent to LLM


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FetchResult:
    url:      str
    text:     str                    # what gets sent to the LLM
    strategy: str                    # "api" | "feed" | "jina" | "error"
    records:  list[dict] = field(default_factory=list)  # pre-parsed records if available
    error:    str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    return url.split("/")[2] if url.count("/") >= 2 else url


def _base(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _is_json_body(text: str) -> bool:
    s = text.lstrip()
    return s.startswith(("{", "["))


# ─────────────────────────────────────────────────────────────────────────────
# Level 1: API Discovery
# ─────────────────────────────────────────────────────────────────────────────

_GENERIC_API_PROBES = [
    "/api",
    "/api.json",
    "/api/v1",
    "/api/v2",
    "/.json",
    "?format=json",
    "?output=json",
    "?type=json",
]

_KNOWN_API_PATTERNS: dict[str, list[str]] = {
    "remoteok.com": [
        "https://remoteok.com/api?tag={keyword}",
        "https://remoteok.com/api",
    ],
    "reddit.com": [
        "{url}.json",
    ],
    "hacker-news.firebaseio.com": [
        "https://hn.algolia.com/api/v1/search?query={keyword}&tags=story",
    ],
    "news.ycombinator.com": [
        "https://hn.algolia.com/api/v1/search?query={keyword}&tags=story",
    ],
    "github.com": [
        "https://api.github.com/search/repositories?q={keyword}",
    ],
}


async def _try_api(url: str, keyword: str, sem: asyncio.Semaphore) -> FetchResult | None:
    from app.services import scraper as _scraper

    domain = _domain(url)
    base   = _base(url)
    kw     = keyword.replace(" ", "+") if keyword else ""

    candidates: list[str] = []

    for pat_domain, templates in _KNOWN_API_PATTERNS.items():
        if pat_domain in domain:
            for tmpl in templates:
                candidates.append(tmpl.replace("{keyword}", kw).replace("{url}", url.rstrip("/")))

    for probe in _GENERIC_API_PROBES:
        if probe.startswith("?"):
            candidates.append(url.split("?")[0] + probe)
        else:
            candidates.append(base + probe)

    for api_url in candidates:
        try:
            async with sem:
                raw = await _scraper.fetch_plain(api_url)
            if not raw or len(raw) < 50:
                continue
            stripped = raw.strip()
            if not _is_json_body(stripped):
                continue
            try:
                parsed = json.loads(stripped[:50_000])
            except json.JSONDecodeError:
                continue
            has_data = False
            if isinstance(parsed, list) and len(parsed) > 1:
                has_data = True
            elif isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list) and len(v) > 1:
                        has_data = True
                        break
            if not has_data:
                continue

            text = stripped[:_MAX_JSON_CHARS]
            raw_list = parsed if isinstance(parsed, list) else next(
                (v for v in parsed.values() if isinstance(v, list) and len(v) > 1), []
            )
            records: list[dict] = []
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                item_url = item.get("url") or item.get("link") or item.get("href") or ""
                if item_url and not item_url.startswith("http"):
                    item_url = urljoin(base + "/", item_url.lstrip("/"))
                if item_url:
                    item = dict(item)
                    item["url"] = item_url
                records.append(item)
            logger.info("fetch [api OK] %s → %d records (via %s)", domain, len(records), api_url)
            return FetchResult(url=api_url, text=text, strategy="api", records=records)

        except Exception as exc:
            logger.debug("api probe failed %s: %s", api_url, exc)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Level 2: Feed Discovery
# ─────────────────────────────────────────────────────────────────────────────

async def _try_feed(url: str, sem: asyncio.Semaphore) -> FetchResult | None:
    """
    Detect RSS/Atom feeds from advertised <link rel="alternate"> tags only.
    Fetches the landing page via Jina to find the feed URL, then parses it.
    """
    try:
        import feedparser
    except ImportError:
        return None

    from app.services import scraper as _scraper

    domain = _domain(url)
    base   = _base(url)

    # Only look for feeds on root/homepage URLs — not deep content pages
    path_segments = [s for s in urlparse(url).path.rstrip("/").split("/") if s]
    if len(path_segments) >= 2:
        return None

    # Fetch landing page to discover advertised feeds
    async with sem:
        landing = await _scraper.fetch_plain(url)

    if not landing:
        return None

    # Parse <link rel="alternate" type="application/rss+xml"> tags
    pat = re.compile(
        r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']([^"\']*)["\'][^>]+href=["\']([^"\']*)["\']',
        re.IGNORECASE,
    )
    candidates: list[str] = []
    for m in pat.finditer(landing):
        mime, href = m.group(1), m.group(2)
        if any(t in mime.lower() for t in ("rss", "atom", "xml")):
            candidates.append(href if href.startswith("http") else urljoin(url, href))

    if not candidates:
        return None

    for feed_url in candidates[:4]:
        try:
            async with sem:
                raw = await _scraper.fetch_plain(feed_url)
            if not raw or len(raw) < 200:
                continue
            feed = feedparser.parse(raw)
            if not feed.entries:
                continue

            records: list[dict] = []
            for entry in feed.entries:
                r: dict[str, Any] = {}
                if getattr(entry, "title", None):     r["title"]     = entry.title
                if getattr(entry, "link", None):
                    link = entry.link
                    if link and not link.startswith("http"):
                        link = urljoin(base + "/", link.lstrip("/"))
                    r["url"] = link
                if getattr(entry, "published", None): r["published"] = entry.published
                elif getattr(entry, "updated", None): r["published"] = entry.updated
                if getattr(entry, "summary", None):
                    r["summary"] = re.sub(r"<[^>]+>", " ", entry.summary).strip()[:400]
                if getattr(entry, "author", None):    r["author"]    = entry.author
                if r:
                    records.append(r)

            if records:
                text = json.dumps(records, ensure_ascii=False)[:_MAX_JSON_CHARS]
                logger.info("fetch [feed OK] %s → %d entries (via %s)", domain, len(records), feed_url)
                return FetchResult(url=feed_url, text=text, strategy="feed", records=records)

        except Exception as exc:
            logger.debug("feed probe failed %s: %s", feed_url, exc)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Level 3: Jina Reader (universal fallback)
# ─────────────────────────────────────────────────────────────────────────────

async def _try_jina(url: str, sem: asyncio.Semaphore) -> FetchResult | None:
    from app.services import scraper as _scraper
    from app.services.ai_pipeline import _markdown_to_text

    domain = _domain(url)
    try:
        async with sem:
            md = await _scraper.fetch_jina(url)
        if not md or len(md.strip()) < 200:
            return None
        text = _markdown_to_text(md)[:_MAX_TEXT_CHARS]
        logger.info("fetch [jina OK] %s → %d chars", domain, len(text))
        return FetchResult(url=url, text=text, strategy="jina")
    except Exception as exc:
        logger.debug("jina fetch failed %s: %s", url, exc)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def smart_fetch(
    url:         str,
    keyword:     str = "",
    sem:         asyncio.Semaphore | None = None,
    progress_cb  = None,
    try_api:     bool = True,
    try_feed:    bool = True,
) -> FetchResult:
    """
    Unified fetch entry point for the agent pipeline.

    Tries each strategy in ascending cost order and returns the first success.
    The caller (agent tool) passes the result directly to the LLM.

    Args:
        url:         Target URL
        keyword:     Search keyword (used to build API query parameters)
        sem:         Shared concurrency semaphore
        progress_cb: Unused; kept for API compatibility
        try_api:     Set False to skip API discovery
        try_feed:    Set False to skip feed discovery
    """
    if sem is None:
        sem = asyncio.Semaphore(3)

    t0 = time.monotonic()

    if try_api:
        result = await _try_api(url, keyword, sem)
        if result:
            return result

    if try_feed:
        result = await _try_feed(url, sem)
        if result:
            return result

    result = await _try_jina(url, sem)
    if result:
        return result

    elapsed = time.monotonic() - t0
    logger.warning("fetch [ALL FAILED] %s (%.1fs)", _domain(url), elapsed)
    return FetchResult(url=url, text="", strategy="error", error=f"Failed to fetch {url}")
