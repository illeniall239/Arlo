"""
AI pipeline — Jina Reader + Gemini extraction.

extract():  Receives Jina markdown (or raw HTML), converts to plain text,
            sends to Gemini for structured extraction + pagination detection.

No CSS selectors. No Scrapling. No Playwright. Works on any public URL via Jina.
"""

import asyncio
import json
import logging
import re
from google import genai
from google.genai import types

from app.core.config import settings
from app.utils.normalizer import normalize_records

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ── Retry wrapper ────────────────────────────────────────────────────────────

async def _generate_with_retry(model: str, contents, config, retries: int = 3):
    for attempt in range(retries):
        try:
            return _client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            msg = str(exc)
            if attempt < retries - 1 and any(c in msg for c in ("503", "500", "UNAVAILABLE", "overloaded")):
                wait = 2 ** attempt + 1
                logger.warning("Gemini unavailable — retrying in %ds (attempt %d/%d)", wait, attempt + 1, retries)
                await asyncio.sleep(wait)
            else:
                raise


# ── JSON parser ──────────────────────────────────────────────────────────────

def _salvage_truncated(text: str) -> str:
    """
    Walk the JSON character by character to find the last complete
    object, then close the outer structure cleanly.

    Handles both plain arrays  [{"a":1}, {"b":2}, ...]
    and wrapped objects        {"records": [{"a":1}, ...], ...}
    """
    stripped = text.lstrip()
    outer_is_array = stripped.startswith("[")
    target_depth = 0 if outer_is_array else 1

    last_obj_end = -1
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == target_depth:
                last_obj_end = i

    if last_obj_end == -1:
        return text

    if outer_is_array:
        return text[: last_obj_end + 1] + "]"
    else:
        return text[: last_obj_end + 1] + '], "next_page_url": null, "next_button_selector": null}'


def _parse_json(raw: str):
    """
    Parse JSON from a Gemini response.

    Tier 1 — standard parse (fast path, works when Gemini output is clean).
    Tier 2 — _salvage_truncated (fixes responses cut off mid-stream).
    Tier 3 — json_repair (handles anything else: missing commas, bad quotes, etc.)
    """
    import json_repair  # lazy import — only needed on failure

    # Strip markdown fences
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Tier 1: clean parse
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # Tier 2: truncation salvage
    try:
        salvaged = _salvage_truncated(text)
        result = json.loads(salvaged, strict=False)
        logger.warning("JSON salvaged from truncated response")
        return result
    except json.JSONDecodeError:
        pass

    # Tier 3: json_repair
    try:
        repaired = json_repair.repair_json(text, return_objects=True)
        if repaired not in (None, "", [], {}):
            logger.warning("JSON repaired by json_repair")
            return repaired
    except Exception:
        pass

    logger.error("JSON parse failed entirely. Raw (first 600 chars):\n%s", raw[:600])
    raise json.JSONDecodeError("All parse attempts failed", text, 0)


# ── Text conversion helpers ──────────────────────────────────────────────────

def _strip_tracking_params(url: str) -> str:
    """
    Strip URL query strings that are clearly tracking/encoding blobs (> 150 chars).
    Short, meaningful queries like ?_nkw=laptops or ?page=2 are kept intact.
    """
    q = url.find('?')
    if q != -1 and len(url) - q > 150:
        return url[:q]
    return url


def _markdown_to_text(md: str, base_url: str = "") -> str:
    """
    Convert Jina Reader markdown to plain text with [LINK:url] markers.

    Jina returns links as [text](url). This converts them to our convention
    so Gemini can find them with the same prompt instructions as HTML-derived text.

    Relative URLs (e.g. /catalogue/item_1000/index.html) are resolved against
    base_url so they become absolute before the https?:// regex runs.
    """
    from urllib.parse import urljoin

    def _clean_url(url: str) -> str:
        """Strip optional Markdown link title from URL: url "Title" → url"""
        return re.sub(r'''\s+["'][^"']*["']$''', '', url).strip()

    # Resolve relative URLs to absolute before any other processing
    if base_url:
        def _resolve(m):
            text, url = m.group(1), _clean_url(m.group(2))
            if not url.startswith(("http://", "https://", "#", "mailto:")):
                url = urljoin(base_url, url)
            return f'[{text}]({url})'
        md = re.sub(r'\[([^\]]*)\]\(([^\)]{1,500})\)', _resolve, md)

    # Convert [text](url) → text [LINK:url], stripping tracking params from long URLs
    def _md_link(m):
        text, url = m.group(1), _clean_url(m.group(2))
        return f'{text} [LINK:{_strip_tracking_params(url)}]'
    md = re.sub(r'\[([^\]]*)\]\((https?://[^\)]{1,500})\)', _md_link, md)
    # Second pass: catch outer URLs from nested image links like [![img](img_url)](product_url)
    # After first pass the inner link becomes [LINK:...] leaving ](product_url) unmatched
    md = re.sub(
        r'\]\((https?://[^\)]{1,500})\)',
        lambda m: f'] [LINK:{_strip_tracking_params(m.group(1))}]',
        md,
    )
    # Strip markdown headings, bold, italic, code —
    # but protect [LINK:...] markers so URL underscores/tildes survive.
    md = re.sub(r'^#{1,6}\s+', '', md, flags=re.MULTILINE)
    parts = re.split(r'(\[LINK:[^\]]*\])', md)
    md = ''.join(
        part if i % 2 == 1 else re.sub(r'[*_`~]', '', part)
        for i, part in enumerate(parts)
    )
    # Collapse whitespace
    md = re.sub(r'[ \t]+', ' ', md)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def _html_to_text(html: str) -> str:
    """
    Strip tags, scripts, styles and collapse whitespace.
    Keeps visible text and href attributes so Gemini can still find pagination links.
    URLs with long tracking query strings are cleaned to their base path.
    """
    # Preserve href values from anchor tags — strip tracking params first
    html = re.sub(
        r'<a\b[^>]*href=["\']([^"\']{1,500})["\'][^>]*>',
        lambda m: f'[LINK:{_strip_tracking_params(m.group(1))}] ',
        html,
        flags=re.IGNORECASE,
    )
    # Remove script / style blocks entirely
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.IGNORECASE | re.DOTALL)
    # Strip all remaining tags
    html = re.sub(r'<[^>]+>', ' ', html)
    # Decode common HTML entities
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')):
        html = html.replace(entity, char)
    # Collapse whitespace
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


# ── Deterministic URL enrichment ─────────────────────────────────────────────

def _build_link_map(md: str, base_url: str = "") -> dict[str, str]:
    """
    Extract all [text](url) pairs from raw Jina markdown.

    Returns {anchor_text_lower: absolute_url}.
    Built BEFORE any text conversion so we capture the original link structure.
    Used to validate / repair URLs in Gemini records post-hoc.
    """
    from urllib.parse import urljoin

    link_map: dict[str, str] = {}

    for m in re.finditer(r'\[([^\]]{1,200})\]\(([^\)]{1,500})\)', md):
        text, url = m.group(1).strip(), m.group(2).strip()
        if not text or not url:
            continue
        # Strip optional Markdown link title: [text](url "Title") or [text](url 'Title')
        url = re.sub(r'''\s+["'][^"']*["']$''', '', url).strip()
        # Resolve relative URLs
        if base_url and not url.startswith(("http://", "https://", "#", "mailto:")):
            url = urljoin(base_url, url)
        if not url.startswith(("http://", "https://")):
            continue
        # Skip image URLs
        if re.search(r'\.(jpg|jpeg|png|gif|webp|svg|ico)(\?|$)', url, re.IGNORECASE):
            continue
        # Skip utility URLs
        if re.search(r'/(cart|signin|login|watchlist|share|report|email|subscribe)(\b|/|$)', url, re.IGNORECASE):
            continue
        key = text.lower()
        if key not in link_map:
            link_map[key] = url

    return link_map


def _validate_urls(records: list[dict], valid_urls: set[str]) -> list[dict]:
    """
    Remove any URL field that isn't a real link from the page.

    Gemini reads URLs directly from [LINK:...] markers in the text — those
    markers are now generated correctly (underscores preserved, Markdown title
    attributes stripped). This function is a final sanity check: if the URL
    Gemini output isn't in the page's actual link set, it's a hallucination
    and we delete it rather than keep a wrong value.

    We deliberately do NOT attempt to assign URLs via title matching — that
    approach causes false matches with navigation/category links on the page.
    """
    for rec in records:
        url = rec.get("url")
        if url and url not in valid_urls:
            del rec["url"]
    return records


# ── Prompts ──────────────────────────────────────────────────────────────────

_EXTRACT_SYSTEM = """You are a data extraction expert.
You receive the visible text content of a webpage (all HTML tags stripped), its URL, and a user goal.

Return a JSON object with exactly these fields:
{
  "records": [ ...every matching item as a flat object with snake_case keys... ],
  "has_next_page": true or false,
  "next_button_selector": "button.next" or null
}

Rules for "records":
- Extract EVERY item matching the goal — do not stop early.
- Ignore navigation menus, sidebars, breadcrumbs, headers, footers, and category/tag listings
  unless the goal explicitly asks for them. Only extract items from the main content area.
- snake_case key names that describe the data intuitively (title, price, url, description, rating, location, etc.)
- All field values must be plain scalars (strings, numbers, or booleans). Never produce nested objects or arrays — join list values with ", ".
- URLs appear in the text as [LINK:https://...] markers. When a [LINK:...] marker appears directly
  adjacent to an item, extract it into a "url" field. Only use URLs that are explicitly present as
  [LINK:...] markers in the text — never fabricate, guess, or construct a URL. Skip utility URLs
  (cart, signin, watchlist, share, report, email).
- Empty array only if truly nothing on the page matches the goal.

Rules for pagination:
- has_next_page: true if a "Next", "Next page", or numbered next page link/button is visible. false otherwise.
- next_button_selector: ONLY set when a JS "Load More" / "Next" button exists with no real href link
  (i.e. clicking it loads content dynamically without navigating). Return its CSS selector.
  Leave null when a real href link exists — the URL will be detected automatically.

Return ONLY the JSON object — no markdown, no explanation."""

_EXTRACT_USER = """URL: {url}
Goal: {goal}

PAGE TEXT:
{html}"""


# ── Public API ───────────────────────────────────────────────────────────────

async def extract(url: str, goal: str, html: str) -> tuple[list[dict], bool, str | None]:
    """
    Extract records from a page using clean text input.

    Auto-detects Jina markdown vs raw HTML and converts appropriately.
    Sends plain text to Gemini — low token usage, high extraction accuracy.

    Returns (records, has_next_page, next_button_selector).
    Pagination URLs are intentionally NOT returned — callers derive them
    from raw page content to avoid Gemini URL mutation bugs.
    """
    # Auto-detect: Jina returns markdown (no < tags); raw HTML starts with <
    is_markdown = not html.lstrip().startswith('<')
    if is_markdown:
        # Build link_map from raw markdown BEFORE any text conversion.
        # This gives us a ground-truth {title → url} dictionary we use
        # post-hoc to fix/validate any URL Gemini outputs.
        link_map = _build_link_map(html, base_url=url)
        text_content = _markdown_to_text(html, base_url=url)[:300_000]
    else:
        link_map = {}
        text_content = _html_to_text(html)[:300_000]

    user_msg = _EXTRACT_USER.format(
        url=url,
        goal=goal,
        html=text_content.replace("{", "{{").replace("}", "}}"),
    )

    response = await _generate_with_retry(
        model=settings.GEMINI_MODEL,
        contents=user_msg,
        config=types.GenerateContentConfig(
            system_instruction=_EXTRACT_SYSTEM,
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=16384,
            # Disable thinking — extraction is deterministic pattern-matching,
            # not reasoning. Thinking tokens eat into the output budget.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    data = _parse_json(response.text)

    if isinstance(data, dict):
        records = data.get("records", [])
        has_next = bool(data.get("has_next_page", False))
        next_selector = data.get("next_button_selector") or None
        if not isinstance(records, list):
            records = []
    elif isinstance(data, list):
        records = data
        has_next = False
        next_selector = None
    else:
        records = []
        has_next = False
        next_selector = None

    # Validate URLs: remove any URL Gemini hallucinated that isn't on the page.
    # Gemini should now read correct URLs from [LINK:...] markers (underscores
    # preserved, Markdown titles stripped). Validation catches edge-case fabrications.
    if link_map:
        records = _validate_urls(records, set(link_map.values()))

    logger.info("Extraction: %d records, has_next=%s, next_selector=%s", len(records), has_next, next_selector)
    return records[:500], has_next, next_selector
