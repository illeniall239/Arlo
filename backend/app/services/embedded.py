"""
embedded.py — Extract pre-rendered structured data from page HTML.

Many sites embed their full dataset in <script> tags to speed up initial
page render (avoids a second round-trip for data). When present, we skip
Gemini entirely — the data is already structured.

Extraction priority (highest confidence first):
  1. Indeed        window.mosaic.providerData   — job cards
  2. Glassdoor     apolloState                  — GraphQL job cache
  3. JSON-LD       application/ld+json          — schema.org (any site)
  4. Next.js       __NEXT_DATA__                — any Next.js app
  5. Nuxt.js       __NUXT__ / __NUXT_DATA__     — any Nuxt.js app

Returns (records: list[dict], source: str) where source names the extractor.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _try_parse(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import json_repair
            result = json_repair.repair_json(text, return_objects=True)
            return result if result not in (None, "", [], {}) else None
        except Exception:
            return None


def _script_tags(html: str, type_attr: str) -> list[str]:
    pattern = (
        r'<script[^>]+type=["\']'
        + re.escape(type_attr)
        + r'["\'][^>]*>(.*?)</script>'
    )
    return re.findall(pattern, html, re.DOTALL | re.IGNORECASE)


def _extract_balanced(html: str, pattern: str) -> Any:
    """
    Find `pattern` in html, then extract the complete JSON object that starts
    immediately after by counting braces. Handles arbitrarily nested objects.
    """
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        return None

    start = m.end()
    # Find the opening brace
    brace_pos = html.find('{', start)
    if brace_pos == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(brace_pos, len(html)):
        ch = html[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return _try_parse(html[brace_pos:i + 1])

    return None


# ── 1. Indeed ─────────────────────────────────────────────────────────────────

def _extract_indeed(html: str) -> list[dict]:
    data = _extract_balanced(
        html,
        r'mosaic-provider-jobcards["\]]+\s*=\s*'
    )
    if not isinstance(data, dict):
        return []

    cards = (
        data.get("jobCards")
        or data.get("jobcards")
        or data.get("results")
        or []
    )

    records = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        # jobCardData is the nested payload in newer versions
        d = card.get("jobCardData") or card

        title    = d.get("jobTitle") or d.get("title", "")
        company  = d.get("companyName") or d.get("company", "")
        location = d.get("formattedLocation") or d.get("location", "")
        snippet  = d.get("snippet") or d.get("jobSnippet", "")

        sal = d.get("extractedSalary") or d.get("salarySnippet") or {}
        salary = (sal.get("text") or sal.get("label", "")) if isinstance(sal, dict) else str(sal)

        jk = d.get("jobkey") or d.get("jobKey") or d.get("jk", "")
        url = f"https://www.indeed.com/viewjob?jk={jk}" if jk else d.get("jobUrl", "")

        record = {k: v for k, v in {
            "title": title, "company": company, "location": location,
            "salary": salary, "description": snippet, "url": url,
        }.items() if v}

        if record.get("title"):
            records.append(record)

    return records


# ── 2. Glassdoor (Apollo GraphQL cache) ───────────────────────────────────────

def _resolve_apollo(cache: dict, val: Any, depth: int = 0) -> Any:
    """Follow Apollo __ref pointers to reconstruct full objects."""
    if depth > 8:
        return val
    if isinstance(val, dict):
        if "__ref" in val:
            return _resolve_apollo(cache, cache.get(val["__ref"], {}), depth + 1)
        return {k: _resolve_apollo(cache, v, depth + 1) for k, v in val.items()}
    if isinstance(val, list):
        return [_resolve_apollo(cache, i, depth + 1) for i in val]
    return val


def _extract_glassdoor(html: str) -> list[dict]:
    cache = _extract_balanced(html, r'"apolloState"\s*:\s*')
    if not isinstance(cache, dict):
        return []

    records = []
    for key, obj in cache.items():
        if not isinstance(obj, dict):
            continue
        if not any(t in key for t in ("JobListing", "JobPosting", "JobView")):
            continue

        resolved = _resolve_apollo(cache, obj)
        header = (
            resolved.get("header")
            or resolved.get("jobViewHeader")
            or resolved
        )

        title   = header.get("jobTitleText") or header.get("title") or resolved.get("jobTitle", "")
        company = header.get("employerNameFromSearch") or header.get("employerName", "")
        loc     = header.get("locationName") or header.get("location") or resolved.get("location", "")
        salary  = header.get("salaryText") or resolved.get("salaryText", "")
        rating  = str(header.get("starRating") or resolved.get("starRating", ""))

        lid = resolved.get("listingId") or resolved.get("jobListingId", "")
        url = f"https://www.glassdoor.com/job-listing/j?jl={lid}" if lid else ""

        record = {k: v for k, v in {
            "title": title, "company": company, "location": loc,
            "salary": salary, "rating": rating, "url": url,
        }.items() if v and v != "0"}

        if record.get("title"):
            records.append(record)

    return records


# ── 3. JSON-LD (schema.org) ───────────────────────────────────────────────────

_USEFUL_TYPES = {
    "JobPosting", "Product", "Offer", "AggregateOffer",
    "Article", "NewsArticle", "BlogPosting", "Event",
    "LocalBusiness", "Person",
    "Course", "Book", "Movie", "TVSeries", "Recipe",
}


def _flatten_json_ld(item: dict) -> dict:
    """Flatten a schema.org object into a simple key→value dict."""
    record: dict = {}

    def _val(v: Any) -> str:
        if isinstance(v, str): return v
        if isinstance(v, (int, float)): return str(v)
        if isinstance(v, dict):
            return (v.get("name") or v.get("@value") or v.get("text") or
                    v.get("value") or v.get("url") or "")
        if isinstance(v, list):
            return ", ".join(_val(i) for i in v if _val(i))
        return ""

    for k, v in item.items():
        if k.startswith("@"):
            continue
        key = re.sub(r'([A-Z])', r'_\1', k).lower().strip("_")
        record[key] = _val(v)

    return {k: v for k, v in record.items() if v}


def _extract_json_ld(html: str) -> list[dict]:
    records = []
    for content in _script_tags(html, "application/ld+json"):
        data = _try_parse(content)
        if not data:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            # Unwrap @graph
            if "@graph" in item:
                graph = item["@graph"]
                items_inner = graph if isinstance(graph, list) else [graph]
                for sub in items_inner:
                    if isinstance(sub, dict) and sub.get("@type") in _USEFUL_TYPES:
                        records.append(_flatten_json_ld(sub))
            elif item.get("@type") in _USEFUL_TYPES:
                records.append(_flatten_json_ld(item))

    return records


# ── 4. Next.js __NEXT_DATA__ ─────────────────────────────────────────────────

def _best_list(obj: Any, depth: int = 0) -> list[dict]:
    """Walk a nested object and return the largest list of dicts found."""
    if depth > 6:
        return []
    if isinstance(obj, list):
        dicts = [i for i in obj if isinstance(i, dict)]
        return dicts
    if isinstance(obj, dict):
        best: list[dict] = []
        for v in obj.values():
            candidate = _best_list(v, depth + 1)
            if len(candidate) > len(best):
                best = candidate
        return best
    return []


def _extract_next_data(html: str) -> list[dict]:
    from app.utils.normalizer import flatten_record
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return []
    data = _try_parse(m.group(1))
    if not isinstance(data, dict):
        return []

    page_props = data.get("props", {}).get("pageProps", {})
    records = [flatten_record(r) for r in _best_list(page_props)]
    # Require at least 3 similar-looking records to avoid false positives
    return records if len(records) >= 3 else []


# ── 5. Nuxt.js __NUXT__ ──────────────────────────────────────────────────────

def _extract_nuxt(html: str) -> list[dict]:
    # __NUXT_DATA__ (Nuxt 3) is a JSON array used to hydrate the app state
    m = re.search(
        r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        # Nuxt 2 inline style: window.__NUXT__={...}
        m = re.search(r'window\.__NUXT__\s*=\s*', html)
        if not m:
            return []
        data = _extract_balanced(html, r'window\.__NUXT__\s*=\s*')
    else:
        data = _try_parse(m.group(1))

    if not data:
        return []

    from app.utils.normalizer import flatten_record
    records = [flatten_record(r) for r in _best_list(data)]
    return records if len(records) >= 3 else []


# ── Content quality validation ────────────────────────────────────────────────

# Fields that indicate a record is actual page content rather than site metadata.
# Site-level schema.org blocks (Organization, Product-as-site) typically only
# carry name / url / logo / aggregateRating — none of these content fields.
_CONTENT_FIELDS = {
    "description", "summary", "body", "content", "text",
    "date_posted", "published", "start_date", "valid_through",
    "base_salary", "salary", "price", "low_price", "high_price",
    "job_location", "location", "address", "work_location",
    "hiring_organization", "company", "employer",
    "author", "creator", "byline",
    "requirements", "qualifications", "skills", "education_requirements",
    "employment_type", "industry", "occupational_category",
    "image", "thumbnail", "article_body",
    "duration", "end_date", "event_status",
}


def _looks_like_content(records: list[dict]) -> bool:
    """
    Return True only when the extracted records appear to be real page content
    (job listings, articles, products with prices, events, …) rather than
    site-level metadata (Organization schema, a Product block that just holds
    the site name and aggregate rating, WebSite descriptors, etc.).

    Heuristic: at least half the records must contain at least one field from
    _CONTENT_FIELDS.  A single stray JobPosting with a description passes; two
    Organization blocks with only name/url/logo do not.
    """
    if not records:
        return False
    hits = sum(1 for r in records if _CONTENT_FIELDS.intersection(r.keys()))
    return hits >= max(1, len(records) // 2)


# ── Public API ────────────────────────────────────────────────────────────────

# (name, extractor_fn, min_records_to_trust)
_EXTRACTORS: list[tuple[str, Any, int]] = [
    ("indeed",    _extract_indeed,    1),
    ("glassdoor", _extract_glassdoor, 1),
    ("json-ld",   _extract_json_ld,   3),  # High bar: 1-2 records is often just site metadata
    ("next.js",   _extract_next_data, 3),
    ("nuxt.js",   _extract_nuxt,      3),
]


def extract_embedded(html: str, url: str = "") -> tuple[list[dict], str]:
    """
    Try all embedded data extractors on the raw HTML.

    Returns (records, source_name) on success.
    Returns ([], "") if no embedded data is found or all results fail the
    content-quality check (e.g. only site-metadata schema.org blocks).

    The caller should try this before any LLM extraction — if records are
    returned, no Gemini call is needed for this page.
    """
    for name, extractor, min_count in _EXTRACTORS:
        try:
            records = extractor(html)
            if records and len(records) >= min_count and _looks_like_content(records):
                logger.info("Embedded [%s]: %d records from %s", name, len(records), url or "?")
                return records, name
        except Exception as exc:
            logger.debug("Embedded extractor [%s] failed: %s", name, exc)

    return [], ""
