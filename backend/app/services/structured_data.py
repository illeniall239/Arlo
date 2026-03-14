"""
Structured data extraction — runs on raw HTML before LLM extraction.

Priority order (highest quality first):
  1. JSON-LD / Schema.org  — embedded in <script> tags, zero extra requests,
                             standardized field names, required by Google for
                             rich results → every serious site has it.
  2. RSS / Atom feeds      — full item lists, one extra HTTP request to feed URL,
                             perfect for listing pages (job boards, news, etc.)

OpenGraph is intentionally NOT used as a primary record source — it yields
exactly one record per page and the LLM does better on full page text.

These two extractors together eliminate LLM extraction calls for a large
fraction of pages: every ATS (Greenhouse, Lever, Workday), every job board
that wants Google for Jobs placement, and every site with an RSS feed.
"""

import asyncio
import json
import logging
import re
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# ── Utilities ─────────────────────────────────────────────────────────────────

def _domain_of(url: str) -> str:
    return url.split("/")[2] if url.count("/") >= 2 else url


def _str(val) -> str:
    """Safely extract a string from a possibly-nested Schema.org value."""
    if not val:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        # Try common text-carrying keys in order
        for key in ("name", "value", "text", "@value", "@id"):
            if val.get(key):
                return _str(val[key])
        return ""
    if isinstance(val, list):
        return _str(val[0]) if val else ""
    return str(val).strip()


def _strip_html(text: str) -> str:
    """Strip HTML tags from a string (used for feed descriptions)."""
    return re.sub(r"<[^>]+>", " ", text).strip()


# ── 1. JSON-LD / Schema.org ───────────────────────────────────────────────────

def extract_jsonld(html: str, page_url: str = "") -> list[dict]:
    """
    Extract and normalize all Schema.org JSON-LD blocks from raw HTML.

    Handles:
      - Multiple <script type="application/ld+json"> blocks per page
      - Top-level arrays: [{...}, {...}]
      - @graph arrays: {"@graph": [{...}, {...}]}
      - Nested objects (e.g. NewsArticle containing author Person)

    Skips navigation/structural types (WebPage, BreadcrumbList, etc.) that
    carry no extractable data.
    """
    _SKIP_TYPES = {
        "WebPage", "WebSite", "BreadcrumbList", "SiteNavigationElement",
        "SearchAction", "ItemList", "ListItem", "ReadAction",
    }

    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    records: list[dict] = []
    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.debug("json-ld parse error on %s: %s", _domain_of(page_url), exc)
            continue

        for obj in _iter_jsonld(data):
            schema_type = obj.get("@type", "")
            if isinstance(schema_type, list):
                schema_type = schema_type[0] if schema_type else ""
            if schema_type in _SKIP_TYPES:
                continue
            record = _normalize_jsonld_obj(obj, page_url)
            if record and any(v for v in record.values()):
                record["_schema_type"] = schema_type
                records.append(record)

    if records:
        logger.info(
            "json-ld: %s → %d records (%s)",
            _domain_of(page_url), len(records),
            ", ".join(set(r.get("_schema_type", "?") for r in records)),
        )
    return records


def _iter_jsonld(data):
    """Yield all top-level Schema.org objects from any JSON-LD structure."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            for item in data["@graph"]:
                yield from _iter_jsonld(item)
        else:
            yield data


def _normalize_jsonld_obj(obj: dict, page_url: str) -> dict:
    """Dispatch to a type-specific normalizer, falling back to generic flatten."""
    schema_type = obj.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = schema_type[0] if schema_type else ""

    if schema_type == "JobPosting":
        return _norm_job_posting(obj, page_url)
    if schema_type in ("Product", "ProductGroup"):
        return _norm_product(obj, page_url)
    if schema_type in ("Article", "NewsArticle", "BlogPosting", "TechArticle"):
        return _norm_article(obj, page_url)
    if schema_type == "Event":
        return _norm_event(obj, page_url)
    if schema_type in ("LocalBusiness", "Restaurant", "Store"):
        return _norm_local_business(obj, page_url)
    if schema_type in ("Course", "CourseInstance"):
        return _norm_course(obj, page_url)

    # Unknown type — generic flatten (skip if no useful fields)
    return _generic_flatten(obj, page_url)


# ── Type-specific normalizers ─────────────────────────────────────────────────

def _norm_job_posting(obj: dict, page_url: str) -> dict:
    record: dict = {}

    record["title"]           = _str(obj.get("title"))
    record["date_posted"]     = _str(obj.get("datePosted"))
    record["employment_type"] = _str(obj.get("employmentType"))
    record["description"]     = _str(obj.get("description") or obj.get("responsibilities"))[:600]
    record["url"]             = _str(obj.get("url") or obj.get("@id") or page_url)

    # Company
    org = obj.get("hiringOrganization")
    if isinstance(org, dict):
        record["company"] = _str(org.get("name"))
    else:
        record["company"] = _str(org)

    # Location — may be a Place, a string, or a list
    loc = obj.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    if isinstance(loc, dict):
        addr = loc.get("address", {})
        if isinstance(addr, dict):
            parts = [
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
                addr.get("addressCountry", ""),
            ]
            record["location"] = ", ".join(p for p in parts if p)
        else:
            record["location"] = _str(addr or loc.get("name"))
    else:
        record["location"] = _str(loc)

    # Remote flag
    job_loc_type = _str(obj.get("jobLocationType"))
    if "remote" in job_loc_type.lower():
        record["location"] = (record["location"] + " (Remote)").strip(" ()")
        if not record["location"] or record["location"] == "(Remote)":
            record["location"] = "Remote"

    # Salary
    salary_obj = obj.get("baseSalary") or obj.get("estimatedSalary")
    if isinstance(salary_obj, dict):
        currency = salary_obj.get("currency", "")
        val      = salary_obj.get("value")
        if isinstance(val, dict):
            lo = val.get("minValue", "")
            hi = val.get("maxValue", "")
            record["salary"] = f"{currency} {lo}–{hi}".strip() if lo or hi else ""
        elif val is not None:
            record["salary"] = f"{currency} {val}".strip()
    elif isinstance(salary_obj, str):
        record["salary"] = salary_obj

    return {k: v for k, v in record.items() if v}


def _norm_product(obj: dict, page_url: str) -> dict:
    record: dict = {
        "name":        _str(obj.get("name")),
        "description": _str(obj.get("description"))[:400],
        "url":         _str(obj.get("url") or obj.get("@id") or page_url),
        "sku":         _str(obj.get("sku") or obj.get("gtin")),
        "image":       _str(obj.get("image")),
    }

    brand = obj.get("brand")
    record["brand"] = _str(brand.get("name") if isinstance(brand, dict) else brand)

    offers = obj.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if isinstance(offers, dict):
        currency            = offers.get("priceCurrency", "")
        price               = offers.get("price")
        record["price"]     = f"{currency} {price}".strip() if price is not None else ""
        record["condition"] = _str(offers.get("itemCondition", "")).split("/")[-1]

    return {k: v for k, v in record.items() if v}


def _norm_article(obj: dict, page_url: str) -> dict:
    pub = obj.get("publisher")
    record: dict = {
        "title":          _str(obj.get("headline") or obj.get("name")),
        "author":         _str(obj.get("author")),
        "date_published": _str(obj.get("datePublished")),
        "date_modified":  _str(obj.get("dateModified")),
        "description":    _str(obj.get("description") or obj.get("abstract"))[:400],
        "url":            _str(obj.get("url") or obj.get("@id") or page_url),
        "publisher":      _str(pub.get("name") if isinstance(pub, dict) else pub),
        "section":        _str(obj.get("articleSection")),
    }
    return {k: v for k, v in record.items() if v}


def _norm_event(obj: dict, page_url: str) -> dict:
    organizer = obj.get("organizer")
    record: dict = {
        "title":       _str(obj.get("name")),
        "start_date":  _str(obj.get("startDate")),
        "end_date":    _str(obj.get("endDate")),
        "description": _str(obj.get("description"))[:400],
        "url":         _str(obj.get("url") or obj.get("@id") or page_url),
        "organizer":   _str(organizer.get("name") if isinstance(organizer, dict) else organizer),
        "status":      _str(obj.get("eventStatus", "")).split("/")[-1],
        "mode":        _str(obj.get("eventAttendanceMode", "")).split("/")[-1],
    }

    location = obj.get("location")
    if isinstance(location, dict):
        record["location"] = _str(location.get("name") or location.get("address"))
    elif isinstance(location, str):
        record["location"] = location

    offer = obj.get("offers")
    if isinstance(offer, list):
        offer = offer[0] if offer else None
    if isinstance(offer, dict):
        price    = offer.get("price")
        currency = offer.get("priceCurrency", "")
        record["price"] = f"{currency} {price}".strip() if price is not None else "Free"

    return {k: v for k, v in record.items() if v}


def _norm_local_business(obj: dict, page_url: str) -> dict:
    record: dict = {
        "name":        _str(obj.get("name")),
        "description": _str(obj.get("description"))[:400],
        "telephone":   _str(obj.get("telephone")),
        "url":         _str(obj.get("url") or obj.get("@id") or page_url),
        "price_range": _str(obj.get("priceRange")),
        "rating":      _str(obj.get("aggregateRating", {}).get("ratingValue")
                            if isinstance(obj.get("aggregateRating"), dict)
                            else obj.get("aggregateRating")),
    }

    address = obj.get("address")
    if isinstance(address, dict):
        parts = [
            address.get("streetAddress", ""),
            address.get("addressLocality", ""),
            address.get("addressRegion", ""),
            address.get("postalCode", ""),
            address.get("addressCountry", ""),
        ]
        record["address"] = ", ".join(p for p in parts if p)
    elif isinstance(address, str):
        record["address"] = address

    return {k: v for k, v in record.items() if v}


def _norm_course(obj: dict, page_url: str) -> dict:
    provider = obj.get("provider") or obj.get("author")
    record: dict = {
        "title":       _str(obj.get("name")),
        "description": _str(obj.get("description"))[:400],
        "url":         _str(obj.get("url") or obj.get("@id") or page_url),
        "provider":    _str(provider.get("name") if isinstance(provider, dict) else provider),
        "language":    _str(obj.get("inLanguage")),
        "level":       _str(obj.get("educationalLevel")),
    }

    offer = obj.get("offers")
    if isinstance(offer, list):
        offer = offer[0] if offer else None
    if isinstance(offer, dict):
        price    = offer.get("price")
        currency = offer.get("priceCurrency", "")
        record["price"] = f"{currency} {price}".strip() if price is not None else "Free"

    return {k: v for k, v in record.items() if v}


def _generic_flatten(obj: dict, page_url: str, _depth: int = 0) -> dict:
    """
    Flatten an unknown Schema.org object to a simple string dict.
    Descends up to 2 levels; stops at known skip keys.
    """
    _SKIP_KEYS = {"@context", "@graph", "sameAs", "potentialAction", "image", "logo"}
    result: dict = {}

    for key, val in obj.items():
        if key in _SKIP_KEYS or key.startswith("@"):
            continue
        if isinstance(val, str) and val.strip():
            result[key] = val.strip()
        elif isinstance(val, (int, float)):
            result[key] = str(val)
        elif isinstance(val, dict) and _depth < 2:
            nested = _generic_flatten(val, page_url, _depth + 1)
            for nk, nv in nested.items():
                result[f"{key}_{nk}"] = nv
        elif isinstance(val, list):
            flat = [_str(v) for v in val if _str(v)]
            if flat:
                result[key] = ", ".join(flat[:5])

    if "url" not in result and page_url:
        result["url"] = page_url

    return result


# ── 2. RSS / Atom feeds ───────────────────────────────────────────────────────

# Standard feed autodiscovery types
_FEED_MIME_TYPES = {"rss", "atom", "xml"}

# Common feed paths to probe (ordered by likelihood)
_FEED_PROBE_PATHS = [
    "/feed",
    "/rss",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/?feed=rss2",           # WordPress
    "/feeds/posts/default",  # Blogger
]


def _find_advertised_feeds(html: str, page_url: str) -> list[str]:
    """
    Find feed URLs advertised via <link rel="alternate" type="..."> in HTML.
    This is the RSS autodiscovery standard — if a site has a feed they want
    people to use, they'll advertise it here.
    """
    # Match both attribute orderings
    patterns = [
        re.compile(
            r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']([^"\']*)["\'][^>]+href=["\']([^"\']*)["\']',
            re.IGNORECASE,
        ),
        re.compile(
            r'<link[^>]+href=["\']([^"\']*)["\'][^>]+type=["\']([^"\']*)["\'][^>]+rel=["\']alternate["\']',
            re.IGNORECASE,
        ),
    ]

    urls: list[str] = []
    for pat in patterns:
        for m in pat.finditer(html):
            a, b = m.group(1), m.group(2)
            # Depending on pattern, (a, b) = (type, href) or (href, type)
            if any(t in a.lower() for t in _FEED_MIME_TYPES):
                href = b
            elif any(t in b.lower() for t in _FEED_MIME_TYPES):
                href = a
            else:
                continue
            if not href.startswith("http"):
                href = urljoin(page_url, href)
            if href not in urls:
                urls.append(href)

    return urls


async def discover_feed(
    url: str,
    html: str,
    fetch_sem: asyncio.Semaphore | None = None,
) -> list[dict]:
    """
    Discover and parse RSS/Atom feeds for a page.

    Strategy:
      1. Check HTML for <link rel="alternate" type="*rss*|*atom*"> (zero requests)
      2. Probe /feed and /rss on the same domain (2 requests max)

    We stop probing once we find a feed with entries.
    Feed content is fetched with the static Fetcher (feeds are plain XML,
    no JS needed) and parsed with feedparser.
    """
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed — RSS discovery disabled")
        return []

    from app.services import scraper

    domain        = _domain_of(url)
    sem           = fetch_sem or asyncio.Semaphore(2)

    # Only use feeds the site explicitly advertises via <link rel="alternate">.
    # Blind path probing causes unnecessary requests + errors on non-feed sites
    # (e-commerce, social, SPAs). Sites that want feeds found WILL advertise them.
    candidates: list[str] = _find_advertised_feeds(html, url)
    if not candidates:
        return []

    for feed_url in candidates[:4]:   # hard cap on attempts
        try:
            async with sem:
                feed_content = await scraper.fetch_plain(feed_url)
            if not feed_content or len(feed_content) < 200:
                continue

            # feedparser.parse() accepts raw XML content as a string
            feed = feedparser.parse(feed_content)

            # bozo=True means malformed; still attempt if entries exist
            if not feed.entries:
                continue

            records: list[dict] = []
            for entry in feed.entries:
                record: dict = {}
                if getattr(entry, "title", None):
                    record["title"] = entry.title
                if getattr(entry, "link", None):
                    record["url"] = entry.link
                if getattr(entry, "published", None):
                    record["date_posted"] = entry.published
                elif getattr(entry, "updated", None):
                    record["date_posted"] = entry.updated
                if getattr(entry, "summary", None):
                    record["description"] = _strip_html(entry.summary)[:500]
                elif getattr(entry, "content", None):
                    record["description"] = _strip_html(entry.content[0].value)[:500]
                if getattr(entry, "author", None):
                    record["author"] = entry.author
                if getattr(entry, "tags", None):
                    record["category"] = ", ".join(
                        t.term for t in entry.tags[:3] if t.term
                    )
                if record:
                    records.append(record)

            if records:
                logger.info(
                    "feed: %s → %d records from %s", domain, len(records), feed_url
                )
                return records

        except Exception as exc:
            logger.debug("feed probe failed for %s: %s", feed_url, exc)

    return []


# ── Main entry point ──────────────────────────────────────────────────────────

async def extract_structured(
    html: str,
    url: str,
    fetch_sem: asyncio.Semaphore | None = None,
) -> list[dict]:
    """
    Try all structured data sources in priority order.
    Returns records if any source succeeds, empty list otherwise.

    Callers should fall back to LLM extraction when this returns [].
    """
    # 1. JSON-LD — no extra requests, highest fidelity
    records = extract_jsonld(html, url)
    if records:
        return records

    # 2. RSS / Atom feeds — one extra request, great for listing pages
    records = await discover_feed(url, html, fetch_sem)
    if records:
        return records

    return []
