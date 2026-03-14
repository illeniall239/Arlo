"""Parse sitemap.xml → list of page URLs."""

import logging
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CareerAI/1.0)"}


async def read_sitemap(url: str, max_urls: int = 60) -> list[str]:
    """
    Fetch and parse a sitemap.xml.
    Pass a homepage URL — auto-detects /sitemap.xml.
    Handles sitemap index files (recurses one level) and leaf sitemaps.
    """
    sitemap_url = url if url.endswith(".xml") else url.rstrip("/") + "/sitemap.xml"
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []

    async def _parse_one(target_url: str, depth: int = 0) -> None:
        if len(urls) >= max_urls or depth > 1:
            return
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
                resp = await client.get(target_url)
                resp.raise_for_status()
                content = resp.content
            root = ElementTree.fromstring(content)

            # Sitemap index — recurse into child sitemaps
            for sitemap_loc in root.findall(".//sm:sitemap/sm:loc", ns):
                if sitemap_loc.text and len(urls) < max_urls:
                    await _parse_one(sitemap_loc.text.strip(), depth + 1)

            # Leaf sitemap — collect page URLs
            for loc in root.findall(".//sm:url/sm:loc", ns):
                if loc.text and loc.text.strip().startswith("http"):
                    urls.append(loc.text.strip())
                    if len(urls) >= max_urls:
                        return
        except Exception as exc:
            logger.warning("sitemap parse failed for %s: %s", target_url, exc)

    await _parse_one(sitemap_url)
    logger.info("read_sitemap %s → %d urls", sitemap_url, len(urls))
    return urls
