"""Parse RSS / Atom feeds via feedparser."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def read_feed(url: str, max_entries: int = 20) -> list[dict]:
    """
    Parse an RSS or Atom feed.
    Returns list of {title, url, summary, published} dicts.
    """
    def _sync() -> list[dict]:
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser not installed")
            return []

        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("read_feed failed for %s: %s", url, exc)
            return []

        results: list[dict] = []
        for entry in feed.entries[:max_entries]:
            results.append({
                "title":     entry.get("title", ""),
                "url":       entry.get("link", ""),
                "summary":   (entry.get("summary") or "")[:300],
                "published": entry.get("published", ""),
            })

        return results

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _sync)
    logger.info("read_feed %s → %d entries", url, len(result))
    return result
