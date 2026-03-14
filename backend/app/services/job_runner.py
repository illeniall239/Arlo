"""
Job runner — three-tier fetch + extraction pipeline.

  Tier 1  fetch_raw()      — curl_cffi with Chrome TLS fingerprinting.
                             Preserves <script> tags for embedded data extraction.
                             Bypasses JA3/TLS fingerprint blocking (Indeed, Glassdoor, etc.)

  Tier 2  Embedded extract — Pulls pre-rendered JSON from script tags.
                             Works for Indeed (window.mosaic), Glassdoor (apolloState),
                             any JSON-LD site, Next.js, Nuxt.js apps.
                             Zero Gemini calls when embedded data is found.

  Tier 3  Jina + Gemini    — Universal fallback. Jina renders any JS site and
                             returns clean markdown. Gemini extracts structured records.

Each page tries Tier 1→2 first. Falls back to Tier 3 only when needed.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.scrape_job import JobStatus, ScrapeJob
from app.models.scrape_result import ScrapeResult
from app.services import ai_pipeline, scraper
from app.utils import cancellation
from app.utils.sse_manager import sse_manager

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _scan_next_page_url(content: str, current_url: str) -> str | None:
    """
    Find the next-page URL from any content format (raw HTML or Jina markdown).

    Extracts links from both formats, then applies four checks in priority order:

      1. rel="next"          — standard HTML pagination attribute, unambiguous
      2. "next" link text    — anchor text is a recognised next-page label
      3. Query-param math    — same path, one param incremented by 1 (Case A)
                               or one new param with value 2 (Case B)
                               Param-name agnostic: works for page, p, pgn, offset, etc.
      4. Path-number-increment — same domain, path differs only in one integer +1
                               Handles /catalogue/page-2.html → page-3.html style URLs
    """
    parsed   = urlparse(current_url)
    base_key = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    cur_qs   = parse_qs(parsed.query, keep_blank_values=True)
    cur_keys = set(cur_qs.keys())

    # ── Extract all (href, link_text) pairs from both HTML and markdown ───────
    # HTML: <a href="...">text</a>  (attribute order may vary)
    html_pairs: list[tuple[str, str]] = []
    for m in re.finditer(
        r'<a\b[^>]*href=["\']([^"\']{1,500})["\'][^>]*>([^<]{0,80})</a>',
        content, re.IGNORECASE,
    ):
        html_pairs.append((m.group(1), m.group(2).strip()))
    # href after text  e.g. <a class="...">Next</a href="..."> (malformed but exists)
    for m in re.finditer(
        r'<a\b[^>]*>([^<]{0,80})</a[^>]*href=["\']([^"\']{1,500})["\']',
        content, re.IGNORECASE,
    ):
        html_pairs.append((m.group(2), m.group(1).strip()))

    # HTML: bare href attributes without text context (links, area, etc.)
    bare_hrefs = re.findall(r'href=["\']([^"\']{1,500})["\']', content)

    # Markdown: [text](url)
    md_pairs = re.findall(r'\[([^\]]{0,80})\]\(([^\)\s]{1,500})\)', content)

    # ── Resolve all candidates to absolute URLs, same domain only ─────────────
    def _resolve(raw: str) -> str | None:
        try:
            resolved = urljoin(current_url, raw.split()[0])
            if urlparse(resolved).netloc == parsed.netloc:
                return resolved
        except Exception:
            pass
        return None

    # ── Check 1: rel="next" ───────────────────────────────────────────────────
    for m in re.finditer(
        r'<[^>]+\brel=["\'][^"\']*\bnext\b[^"\']*["\'][^>]*\bhref=["\']([^"\']+)["\']'
        r'|<[^>]+\bhref=["\']([^"\']+)["\'][^>]*\brel=["\'][^"\']*\bnext\b[^"\']*["\']',
        content, re.IGNORECASE,
    ):
        href = m.group(1) or m.group(2)
        resolved = _resolve(href)
        if resolved:
            return resolved

    # ── Check 2: "next" anchor text ───────────────────────────────────────────
    _NEXT_LABELS = {"next", "next »", "next page", "»", "›", "→", ">"}

    for href, text in html_pairs:
        if text.lower() in _NEXT_LABELS:
            resolved = _resolve(href)
            if resolved:
                return resolved

    for text, href in md_pairs:
        if text.lower() in _NEXT_LABELS:
            resolved = _resolve(href)
            if resolved:
                return resolved

    # ── Checks 3 & 4: URL math on all same-domain candidates ─────────────────
    all_hrefs = (
        [h for h, _ in html_pairs]
        + bare_hrefs
        + [h for _, h in md_pairs]
    )
    cur_path_nums = [int(m.group()) for m in re.finditer(r'\d+', parsed.path)]

    for raw in all_hrefs:
        candidate = _resolve(raw)
        if not candidate:
            continue
        cp = urlparse(candidate)
        cq = parse_qs(cp.query, keep_blank_values=True)
        cq_keys = set(cq.keys())
        cp_base = f"{cp.scheme}://{cp.netloc}{cp.path}"

        # Check 3: query-param math (same path, different params)
        if cp_base == base_key:
            if cq_keys == cur_keys:
                # Case A: same params, one incremented by 1
                changed = [k for k in cur_keys if cq.get(k) != cur_qs.get(k)]
                if len(changed) == 1:
                    k = changed[0]
                    try:
                        if int(cq[k][0]) == int(cur_qs[k][0]) + 1:
                            return candidate
                    except (ValueError, IndexError):
                        pass
            elif cur_keys.issubset(cq_keys) and len(cq_keys) - len(cur_keys) == 1:
                # Case B: one new param with value 2 (first page had none)
                new_key = next(iter(cq_keys - cur_keys))
                try:
                    if int(cq[new_key][0]) == 2:
                        return candidate
                except (ValueError, IndexError):
                    pass

        # Check 4: path-number-increment (e.g. /page-2.html → /page-3.html)
        cand_path_nums = [int(m.group()) for m in re.finditer(r'\d+', cp.path)]

        if len(cur_path_nums) == len(cand_path_nums) and len(cur_path_nums) >= 1:
            diffs = [
                (c, n)
                for c, n in zip(cur_path_nums, cand_path_nums)
                if c != n
            ]
            if len(diffs) == 1 and diffs[0][1] == diffs[0][0] + 1:
                return candidate

        # Edge case: current URL has no page number, candidate introduces "2"
        # (e.g. / → /catalogue/page-2.html) — only accept if paths share a prefix
        if not cur_path_nums and len(cand_path_nums) == 1 and cand_path_nums[0] == 2:
            # Require candidate path to start with the same directory as current
            cur_dir = parsed.path.rsplit("/", 1)[0]
            if cp.path.startswith(cur_dir):
                return candidate

    return None


def _increment_page_param(url: str) -> str | None:
    """
    Increment whichever query param looks like a page number (small integer > 0).
    Used as a last resort when no next-page link is found in content.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    for k, vs in qs.items():
        try:
            val = int(vs[0])
            if 1 <= val <= 9999:
                qs[k] = [str(val + 1)]
                return urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()})))
        except (ValueError, IndexError):
            continue
    return None



async def _fetch_page(url: str) -> tuple[str, str]:
    """
    Fetch a page using the best available method.

    Returns (content, mode) where mode is "raw" or "jina".
    "raw"  — real HTML from curl_cffi; script tags intact for embedded extraction.
    "jina" — clean markdown from Jina Reader; used when curl_cffi fails.
    """
    raw = await scraper.fetch_raw(url)
    if raw:
        return raw, "raw"
    jina = await scraper.fetch_jina(url)
    return jina, "jina"


async def _run_paginated_extraction(
    url: str,
    goal: str,
    max_pages: int = 5,
    progress_cb=None,
) -> tuple[list[dict], int]:
    """
    Paginated extraction pipeline — four tiers in priority order:

      Tier 0: Site API       — Indeed GraphQL, LinkedIn REST, Glassdoor GraphQL.
                               Direct structured data, zero HTML/Gemini.
      Tier 1: curl_cffi      — Chrome TLS fingerprint; raw HTML with script tags.
      Tier 2: Embedded data  — Extract pre-rendered JSON from script tags (no Gemini).
      Tier 3: Jina + Gemini  — Universal fallback for everything else.

    Pagination for Tier 0 is handled internally by the API client.
    Pagination for Tiers 1-3 is driven by URL math from raw page content.
    """
    from app.services.embedded import extract_embedded
    from app.services.site_apis import fetch_site_api, is_supported_site

    async def _pub(msg: str):
        if progress_cb:
            await progress_cb(msg)

    # ── Tier 0: Site-specific API ─────────────────────────────────────────────
    if is_supported_site(url):
        await _pub("Site API detected — fetching directly…")
        max_results = min(max_pages * 100, 200)  # cap at 200 — enough for any query; Indeed: 100/page
        try:
            records = await fetch_site_api(url, max_results=max_results)
        except Exception as exc:
            logger.warning("Site API failed for %s: %s — falling back", url, exc)
            records = []
        if records:
            await _pub(f"Site API: {len(records)} records.")
            return records, 1
        await _pub("Site API returned no results — falling back to scraping…")

    all_records: list[dict] = []
    seen_urls:   set[str]   = {url}
    current_url              = url
    pages_scraped            = 0

    for page_num in range(1, max_pages + 1):
        # ── Fetch ────────────────────────────────────────────────────────────
        await _pub(f"Fetching page {page_num}…")
        content, mode = await _fetch_page(current_url)

        if not content:
            await _pub(f"Failed to fetch page {page_num} — stopping.")
            pages_scraped = page_num - 1
            break

        await _pub(f"Page {page_num} fetched ({len(content):,} chars, {mode}). Extracting…")

        # ── Pagination URL scan (before extraction, from raw source) ─────────
        content_next_url = _scan_next_page_url(content, current_url)

        # ── Extract ──────────────────────────────────────────────────────────
        extracted: list[dict] = []
        has_next = False
        next_selector = None

        if mode == "raw":
            # Tier 1+2: try embedded data first — zero Gemini cost
            embedded, source = extract_embedded(content, current_url)
            if embedded:
                extracted = embedded
                logger.info("Page %d: embedded [%s] → %d records", page_num, source, len(extracted))
            else:
                # Tier 3: Jina + Gemini — handles JS, Cloudflare, everything
                jina_content = await scraper.fetch_jina(current_url)
                if jina_content:
                    content_next_url = content_next_url or _scan_next_page_url(jina_content, current_url)
                    extracted, has_next, next_selector = await ai_pipeline.extract(current_url, goal, jina_content)
                else:
                    # Jina failed — use best available HTML with Gemini
                    extracted, has_next, next_selector = await ai_pipeline.extract(current_url, goal, content)
        else:
            # Tier 3: Jina markdown → Gemini
            extracted, has_next, next_selector = await ai_pipeline.extract(current_url, goal, content)

        # ── Accumulate ───────────────────────────────────────────────────────
        if extracted:
            all_records.extend(extracted)
            await _pub(
                f"Page {page_num}: {len(extracted)} records (total: {len(all_records)})"
                + (f" — next: {content_next_url}" if content_next_url else "")
            )

        pages_scraped = page_num

        if len(all_records) >= 500:
            await _pub(f"500 record cap — stopping after {page_num} page(s).")
            break

        if page_num > 1 and not extracted:
            await _pub(f"Page {page_num} returned no records — stopping.")
            break

        # ── Next URL ─────────────────────────────────────────────────────────
        next_url = None

        if content_next_url and content_next_url not in seen_urls:
            next_url = content_next_url
        elif has_next and extracted:
            incremented = _increment_page_param(current_url)
            if incremented and incremented not in seen_urls:
                logger.info("Pagination: has_next=True, no link found — incrementing → %s", incremented)
                next_url = incremented
        elif next_selector:
            logger.info("Pagination: JS button %s — not supported without browser", next_selector)

        if not next_url:
            await _pub(f"No more pages — {page_num} page(s), {len(all_records)} records total.")
            break

        seen_urls.add(next_url)
        current_url = next_url
    else:
        await _pub(f"Reached page limit ({max_pages}) — {len(all_records)} records total.")
        pages_scraped = max_pages

    return all_records, pages_scraped


async def _update_job(db: AsyncSession, job_id: str, **kwargs) -> None:
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        await db.commit()


async def run_job(job_id: str) -> None:
    cancel_event = cancellation.register(job_id)
    async with AsyncSessionLocal() as db:
        try:
            await _execute_pipeline(db, job_id, cancel_event)
        except Exception as exc:
            logger.exception("Unhandled error in job %s", job_id)
            await _update_job(db, job_id,
                              status=JobStatus.FAILED,
                              error=str(exc),
                              completed_at=_now())
            await sse_manager.publish(job_id, {"type": "error", "detail": str(exc)})
        finally:
            cancellation.cleanup(job_id)


async def _publish(job_id: str, message: str, kind: str = "status") -> None:
    await sse_manager.publish(job_id, {"type": kind, "message": message})


def _cancelled(cancel_event) -> bool:
    return cancel_event.is_set()



def _clean_url(url: str) -> str:
    """Normalize a URL: strip whitespace, decode percent-encoded spaces, ensure scheme."""
    from urllib.parse import unquote, urlparse, urlunparse
    url = unquote(url).strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=parsed.path.rstrip()))


async def _execute_pipeline(db: AsyncSession, job_id: str, cancel_event) -> None:
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return

    # Normalize URL at runtime — handles jobs stored before the router-level fix
    url = _clean_url(job.url)

    await _update_job(db, job_id, status=JobStatus.RUNNING, started_at=_now())

    # ── Paginated extraction (three-tier: curl_cffi → embedded → Jina+Gemini) ─
    if _cancelled(cancel_event):
        await _update_job(db, job_id, status=JobStatus.CANCELLED, completed_at=_now())
        return

    await _update_job(db, job_id, status=JobStatus.STRUCTURING)

    max_pages = getattr(job, "max_pages", 5) or 5
    all_records: list[dict] = []

    async def _pub_cb(msg: str):
        await sse_manager.publish(job_id, {"type": "progress", "rows_found": len(all_records), "message": msg})

    records, _ = await _run_paginated_extraction(
        url=url,
        goal=job.prompt,
        max_pages=max_pages,
        progress_cb=_pub_cb,
    )
    all_records = records

    if not records:
        await _update_job(db, job_id,
                          status=JobStatus.FAILED,
                          error="No records extracted. The page may require authentication or have no matching content.",
                          completed_at=_now())
        await sse_manager.publish(job_id, {"type": "error", "detail": "No records extracted."})
        return

    # ── Compute diff vs previous run ─────────────────────────────────────────
    diff_json: str | None = None
    try:
        from app.services.scheduler import compute_diff
        prev = await db.execute(
            select(ScrapeResult)
            .join(ScrapeJob, ScrapeResult.job_id == ScrapeJob.id)
            .where(
                ScrapeJob.url == url,
                ScrapeJob.status == JobStatus.COMPLETED,
                ScrapeJob.id != job_id,
            )
            .order_by(ScrapeResult.created_at.desc())
            .limit(1)
        )
        prev_result = prev.scalar_one_or_none()
        if prev_result:
            old_records = json.loads(prev_result.structured_data)
            diff = compute_diff(old_records, records)
            diff_json = json.dumps(diff, ensure_ascii=False)
            logger.info("Job %s diff: +%d -%d", job_id, diff["added"], diff["removed"])
    except Exception as exc:
        logger.warning("Diff computation failed for job %s: %s", job_id, exc)

    # ── Normalize & Filter: flatten nested dicts, strip HTML, discard brand rows ──
    from app.utils.normalizer import flatten_record
    records = [flatten_record(r) for r in records]

    # Filter out brand/header rows (e.g. "Remote OK") that are missing core data
    # compared to the rest of the set. Use a universal set of core fields.
    if len(records) > 2:
        def _score(r: dict) -> int:
            return sum(1 for k in r.keys() if k in {
                "title", "name", "company", "brand", "location", "salary", 
                "price", "description", "date_posted", "url", "image", 
                "sku", "type", "author", "id"
            })
        avg_score = sum(_score(r) for r in records) / len(records)
        # Discard records that have significantly less structured detail than average
        records = [r for r in records if _score(r) >= max(1, avg_score * 0.4)]

    # ── Save result ──────────────────────────────────────────────────────────
    # Compute schema from ALL records, not just the first one, to ensure all cols render
    unique_keys = []
    seen_keys = set()
    for r in records:
        for k in r.keys():
            if k not in seen_keys:
                seen_keys.add(k)
                unique_keys.append(k)

    scrape_result = ScrapeResult(
        job_id=job_id,
        raw_html="",
        structured_data=json.dumps(records, ensure_ascii=False),
        row_count=len(records),
        schema_detected=json.dumps(unique_keys) if unique_keys else None,
        diff_json=diff_json,
    )
    db.add(scrape_result)
    await _update_job(db, job_id, status=JobStatus.COMPLETED, completed_at=_now())
    await db.commit()
    await db.refresh(scrape_result)

    await sse_manager.publish(job_id, {
        "type": "done",
        "result_id": scrape_result.id,
        "rows": len(records),
        "message": f"Done! {len(records)} records extracted.",
    })
    logger.info("Job %s completed: %d records", job_id, len(records))
