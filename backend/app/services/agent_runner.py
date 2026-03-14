"""
Agentic scraper — Gemini function-calling loop.

Phase 1: Plan  — one LLM call → extraction schema + initial search queries
Phase 2: Agent — Gemini calls tools iteratively until done() or MAX_AGENT_ITERATIONS

Tools available to the agent:
  web_search     — Tavily web search
  fetch_html     — Smart cascade fetch for listing/root pages (API → Feed → Jina Reader)
  fetch_content  — Direct page read for articles/content (no API/feed probing)
  scrape_listing — Paginated multi-page extraction from any listing/category/search page
  get_links      — Extract <a href> links from a page
  read_sitemap   — Parse sitemap.xml to discover all page URLs on a site
  read_feed      — Parse RSS / Atom feed
  add_records    — Incrementally persist collected records
  done           — Signal completion with summary
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.agent_run import AgentRun, AgentStatus
from app.services import site_fetcher
from app.services.ai_pipeline import _generate_with_retry, _html_to_text, _parse_json
from app.services.structured_data import extract_structured
from app.utils import cancellation
from app.utils.sse_manager import sse_manager

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

FETCH_CONCURRENCY    = 3
MAX_AGENT_ITERATIONS = 25
_MAX_CONTENTS_TURNS  = 12   # keep last N model+tool turn pairs in active context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _domain_of(url: str) -> str:
    return url.split("/")[2] if url.count("/") >= 2 else url


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)




# ── Phase 1: Planner ──────────────────────────────────────────────────────────

async def _plan(goal: str) -> dict:
    """One LLM call → structured params + schema."""
    prompt = f"""You are a web research planner. Extract structured parameters for a scraping goal.

Goal: {goal}

Return a JSON object with these fields:

{{
  "search_queries": ["2-4 targeted search queries to find the best sources"],
  "response_format": "tabular | prose",
  "extraction_schema": {{"field_name": "what this field contains"}},
  "plan_summary": "one sentence describing what will be collected"
}}

response_format rules (pick exactly one):
- "tabular" → goal wants a COLLECTION of similar structured items: products, listings, articles,
               prices, events, repos, jobs, profiles. Output is naturally a table/list.
- "prose"   → goal wants a SYNTHESIZED ANSWER: summaries, explanations, analysis, comparisons,
               "what is X", "how does Y work", "tell me about Z", "explain", "summarize".

Schema examples:
- listings:  {{"title": "item title", "url": "item URL", "price": "price", "description": "description"}}
- articles:  {{"title": "article title", "url": "article URL", "summary": "brief description", "published": "date"}}
- products:  {{"name": "product name", "price": "price", "url": "product URL", "description": "description"}}
- profiles:  {{"name": "full name", "title": "job title", "company": "employer", "url": "profile URL"}}

Return ONLY the JSON object, no explanation."""

    try:
        response = await _generate_with_retry(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=1024,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        plan = _parse_json(response.text)
        if not isinstance(plan, dict):
            raise ValueError(f"expected dict, got {type(plan).__name__}")
        plan["goal_type"] = "web_research"
        if not plan.get("search_queries"):
            plan["search_queries"] = [goal]
        plan.setdefault("extraction_schema", {"data": "relevant information"})
        plan.setdefault("plan_summary", f"Searching for: {goal}")
        plan.setdefault("response_format", "tabular")
        if plan["response_format"] not in ("tabular", "prose"):
            plan["response_format"] = "tabular"
        logger.info("plan OK — schema: %s", list(plan["extraction_schema"].keys()))
        return plan
    except Exception as exc:
        logger.error("plan FAILED — %s", exc, exc_info=True)
        return {
            "goal_type":         "web_research",
            "response_format":   "tabular",
            "search_queries":    [goal],
            "extraction_schema": {"data": "relevant information matching the goal"},
            "plan_summary":      f"Searching for: {goal}",
        }




# ── Shared record helpers ─────────────────────────────────────────────────────

def _merge_records(target: list[dict], new_records: list[dict]) -> int:
    """Append new_records into target, deduplicating by url/profile_url. Returns count added."""
    existing_keys: set[str] = {
        r.get("url") or r.get("profile_url")
        for r in target
        if r.get("url") or r.get("profile_url")
    }
    added = 0
    for r in new_records:
        if not isinstance(r, dict):
            continue
        key = r.get("url") or r.get("profile_url")
        if key and key in existing_keys:
            continue
        if key:
            existing_keys.add(key)
        target.append(r)
        added += 1
    return added




# ── Tool declarations (Gemini function-calling schema) ────────────────────────

def _build_tools() -> types.Tool:
    S = types.Schema
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="web_search",
            description=(
                "Search the web and return a list of {url, title, snippet} results. "
                "Use this to discover relevant pages, sources, or URLs for any topic. "
                "Start here for any new subject — then fetch the most promising URLs."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "query":       S(type="STRING",  description="Search query string"),
                    "num_results": S(type="INTEGER", description="Results to return (default 8, max 10)"),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="fetch_html",
            description=(
                "Fetch a listing, search, or root URL and extract structured records. "
                "Cascade order (cheapest first): API endpoint → RSS/Atom feed → static HTML → stealth → JS render. "
                "Use for: job boards, product listings, search result pages, site homepages, APIs. "
                "Pass `keyword` so the API layer builds the correct query — e.g. remoteok.com/api?tag=python. "
                "Do NOT use for specific articles or content pages — use fetch_content instead."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url":     S(type="STRING", description="Full URL to fetch"),
                    "keyword": S(type="STRING", description="Main search term for API discovery (strongly recommended for listing/job sites)"),
                },
                required=["url"],
            ),
        ),
        types.FunctionDeclaration(
            name="fetch_content",
            description=(
                "Read the full text of a specific page — article, news story, blog post, report, "
                "funding announcement, documentation page, etc. "
                "Goes directly to the page without API or feed probing. "
                "Use this whenever you need to READ the content of a URL you already know "
                "(e.g. from search results, feed entries, or a listing page). "
                "Do NOT use for listing/search/root pages — use fetch_html for those."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url": S(type="STRING", description="Full URL of the page to read"),
                },
                required=["url"],
            ),
        ),
        types.FunctionDeclaration(
            name="scrape_listing",
            description=(
                "Scrape ALL items from a product listing, category, or search result page — "
                "automatically paginating through multiple pages and using the fastest available "
                "extraction strategy. Use this when you have the URL of a listing/category page "
                "and need to collect everything from it (products, articles, events, etc.). "
                "Do NOT use for single article pages — use fetch_content for those."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url":       S(type="STRING",  description="URL of the listing/category/search result page"),
                    "goal":      S(type="STRING",  description="What to extract, e.g. 'cameras under $5000'"),
                    "max_pages": S(type="INTEGER", description="Max pages to paginate through (default 5, max 20)"),
                },
                required=["url", "goal"],
            ),
        ),
        types.FunctionDeclaration(
            name="fetch_structured",
            description=(
                "Extract hidden structured metadata (JSON-LD, RSS, schemas) from a URL. "
                "Returns a list of structured records. Use ONLY if fetch_html fails to provide "
                "the necessary data. Warning: often contains generic or incomplete data."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url": S(type="STRING", description="Full URL to fetch"),
                },
                required=["url"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_links",
            description=(
                "Extract all hyperlinks from a page. Returns list of {url, text} objects. "
                "Useful for finding pagination links, detail pages, or category navigation."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url": S(type="STRING", description="Page URL to extract links from"),
                },
                required=["url"],
            ),
        ),
        types.FunctionDeclaration(
            name="read_sitemap",
            description=(
                "Parse a website's sitemap.xml to discover all page URLs. "
                "Pass the homepage URL — auto-detects /sitemap.xml. "
                "Good for finding listing/category pages on structured sites."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url": S(type="STRING", description="Homepage or direct sitemap.xml URL"),
                },
                required=["url"],
            ),
        ),
        types.FunctionDeclaration(
            name="read_feed",
            description=(
                "Parse an RSS or Atom feed. Returns list of {title, url, summary, published} entries. "
                "Use for news sites, blogs, and job boards that publish feeds."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "url": S(type="STRING", description="RSS or Atom feed URL"),
                },
                required=["url"],
            ),
        ),
        types.FunctionDeclaration(
            name="add_records",
            description=(
                "Save extracted records to the results buffer immediately. "
                "Call this after EVERY tool call that yields useful data — do NOT wait until done(). "
                "Records are persisted as you go; none will be lost if the session ends early. "
                "Duplicates (same url or profile_url) are automatically ignored."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "records_json": S(
                        type="STRING",
                        description=(
                            'JSON array of records matching the extraction schema, e.g. '
                            '[{"title": "...", "url": "..."}]'
                        ),
                    ),
                },
                required=["records_json"],
            ),
        ),
        types.FunctionDeclaration(
            name="done",
            description=(
                "Call this when research is complete and all records have been saved via add_records(). "
                "Only pass a one-sentence summary — records are already stored."
            ),
            parameters=S(
                type="OBJECT",
                properties={
                    "summary": S(
                        type="STRING",
                        description="One-sentence summary of what was found",
                    ),
                },
                required=["summary"],
            ),
        ),
    ])


# ── Tool implementations ───────────────────────────────────────────────────────

async def _tool_web_search(args: dict) -> list[dict]:
    from app.services.tools.search import web_search
    query       = args.get("query", "")
    num_results = min(int(args.get("num_results", 8)), 10)
    results     = await web_search(query, num_results=num_results)
    logger.info("tool web_search %r → %d results", query, len(results))
    return results


async def _ensure_fetched(url: str, sem: asyncio.Semaphore, page_cache: dict, pub, keyword: str = "") -> dict:
    if url in page_cache:
        return page_cache[url]

    async def _progress(msg):
        await pub({"type": "status", "message": msg})

    res = await site_fetcher.smart_fetch(url, keyword=keyword, sem=sem, progress_cb=_progress)
    
    # Store result in cache
    page_cache[url] = {
        "text":     res.text,
        "strategy": res.strategy,
        "records":  res.records,
        "raw":      res.raw
    }
    return page_cache[url]


async def _tool_fetch_html(
    args: dict,
    sem: asyncio.Semaphore,
    page_cache: dict,
    pub,
) -> str:
    url     = args.get("url", "")
    keyword = args.get("keyword", "")
    data    = await _ensure_fetched(url, sem, page_cache, pub, keyword=keyword)
    logger.info("tool fetch_html %s (keyword=%r, strategy=%s) → %d chars",
                _domain_of(url), keyword, data.get("strategy", "?"), len(data.get("text", "")))
    return data["text"]


async def _tool_fetch_content(
    args: dict,
    sem: asyncio.Semaphore,
    page_cache: dict,
    pub,
) -> str:
    """Read a specific article/page directly — no API or feed probing."""
    url = args.get("url", "")
    if url in page_cache:
        logger.info("tool fetch_content %s (cached) → %d chars", _domain_of(url), len(page_cache[url]["text"]))
        return page_cache[url]["text"]

    res = await site_fetcher.smart_fetch(url, sem=sem, try_api=False, try_feed=False)
    page_cache[url] = {
        "text":     res.text,
        "strategy": res.strategy,
        "records":  [],   # fetch_content is for reading, not structured extraction
        "raw":      res.raw,
    }
    logger.info("tool fetch_content %s (strategy=%s) → %d chars",
                _domain_of(url), res.strategy, len(res.text))
    return res.text


async def _tool_scrape_listing(
    args: dict,
    pub,
    final_records: list,
    trace: list,
) -> str:
    """Paginated extraction from a listing/category page — wraps the job_runner pipeline."""
    from app.services.job_runner import _run_paginated_extraction

    url       = args.get("url", "")
    goal      = args.get("goal", "")
    max_pages = min(int(args.get("max_pages", 5)), 20)

    if not url:
        return "No URL provided."

    async def _progress(msg: str):
        await pub({"type": "progress", "message": msg})

    records, pages = await _run_paginated_extraction(url, goal, max_pages, _progress)
    added = _merge_records(final_records, records)
    trace.append({"stage": "scrape_listing", "url": url, "records": added, "pages": pages})
    await pub({"type": "progress", "message": f"→ Extracted {added} records from {pages} page(s) ({url})"})
    return f"Scraped {added} records across {pages} page(s) from {url}."


async def _tool_fetch_structured(
    args: dict,
    sem: asyncio.Semaphore,
    page_cache: dict,
    pub,
) -> dict:
    url = args.get("url", "")
    page = await _ensure_fetched(url, sem, page_cache, pub)
    if "error" in page:
        return {"error": page["error"]}
    
    if page["records"] is None:
        try:
            page["records"] = await extract_structured(page["raw"], url, sem)
        except Exception as exc:
            logger.warning("extract_structured failed for %s: %s", url, exc)
            page["records"] = []

    logger.info("tool fetch_structured %s → %d records", _domain_of(url), len(page["records"]))
    return {"records": page["records"]}


async def _tool_get_links(args: dict) -> list[dict]:
    from app.services.tools.links import get_links
    url     = args.get("url", "")
    results = await get_links(url)
    logger.info("tool get_links %s → %d links", url, len(results))
    return results


async def _tool_read_sitemap(args: dict) -> list[str]:
    from app.services.tools.sitemap import read_sitemap
    url     = args.get("url", "")
    results = await read_sitemap(url)
    logger.info("tool read_sitemap %s → %d urls", url, len(results))
    return results


async def _tool_read_feed(args: dict) -> list[dict]:
    from app.services.tools.feed import read_feed
    url     = args.get("url", "")
    results = await read_feed(url)
    logger.info("tool read_feed %s → %d entries", url, len(results))
    return results


async def _dispatch_tool(
    name: str,
    args: dict,
    sem: asyncio.Semaphore,
    page_cache: dict,
    pub,
    final_records: list | None = None,
    trace: list | None = None,
) -> object:
    try:
        if name == "web_search":
            return await _tool_web_search(args)
        if name == "fetch_html":
            return await _tool_fetch_html(args, sem, page_cache, pub)
        if name == "fetch_content":
            return await _tool_fetch_content(args, sem, page_cache, pub)
        if name == "scrape_listing":
            return await _tool_scrape_listing(args, pub, final_records if final_records is not None else [], trace if trace is not None else [])
        if name == "fetch_structured":
            return await _tool_fetch_structured(args, sem, page_cache, pub)
        if name == "get_links":
            return await _tool_get_links(args)
        if name == "read_sitemap":
            return await _tool_read_sitemap(args)
        if name == "read_feed":
            return await _tool_read_feed(args)
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.error("tool %s raised: %s", name, exc, exc_info=True)
        return {"error": str(exc)}


def _summarize_args(args: dict) -> str:
    """Short human-readable summary of tool args for SSE progress messages."""
    if not args:
        return ""
    first_val = next(iter(args.values()), "")
    s = str(first_val)
    return s[:80] + ("…" if len(s) > 80 else "")


def _prune_contents(
    contents: list,
    page_cache: dict,
    final_records: list,
) -> list:
    """
    Sliding context window: keep system message + last _MAX_CONTENTS_TURNS turn-pairs.
    Prepend a progress header so the model knows what was already searched and saved.
    """
    # Each turn-pair = one model Content + one tool-result user Content
    # contents[0] is the system/goal message; pairs start at index 1
    max_len = _MAX_CONTENTS_TURNS * 2 + 1
    if len(contents) <= max_len:
        return contents

    searched = list(page_cache.keys())[:20]
    progress = (
        f"[RESEARCH PROGRESS — {len(final_records)} records saved so far via add_records(). "
        f"Sources already searched (do not repeat): {searched}. "
        f"Continue finding new sources.]"
    )
    pruned = [
        contents[0],
        types.Content(role="user", parts=[types.Part(text=progress)]),
        *contents[-(  _MAX_CONTENTS_TURNS * 2):],
    ]
    logger.info(
        "context pruned: %d → %d turns (%d records saved)",
        len(contents), len(pruned), len(final_records),
    )
    return pruned


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_agent(run_id: str) -> None:
    cancel_event = cancellation.register(run_id)
    async with AsyncSessionLocal() as db:
        try:
            await _execute(db, run_id, cancel_event)
        except Exception as exc:
            logger.exception("Agent %s crashed unexpectedly", run_id)
            await _update(db, run_id, status=AgentStatus.FAILED,
                          error=str(exc), completed_at=_now())
            await sse_manager.publish(run_id, {"type": "error", "detail": str(exc)})
        finally:
            cancellation.cleanup(run_id)


async def _execute(db: AsyncSession, run_id: str, cancel_event) -> None:
    t_start = time.monotonic()

    res = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        logger.error("_execute: run_id %s not found", run_id)
        return

    await _update(db, run_id, status=AgentStatus.RUNNING)
    goal    = run.goal
    context = run.context  # prior conversation history (may be None)
    trace: list[dict] = []

    async def pub(event: dict) -> None:
        await sse_manager.publish(run_id, event)

    def cancelled() -> bool:
        return cancel_event.is_set()

    logger.info("[%s] Agent START — goal: %r", run_id[:8], goal)

    # ── Phase 1: Plan ─────────────────────────────────────────────────────────
    await pub({"type": "status", "message": "Planning research strategy…"})
    plan   = await _plan(goal)
    schema = plan["extraction_schema"]
    await pub({
        "type":    "status",
        "message": (
            f"Plan: {plan['plan_summary']} — "
            f"{len(plan['search_queries'])} queries, "
            f"tools: {plan.get('recommended_tools', [])}, "
            f"schema: {list(schema.keys())}"
        ),
    })
    trace.append({"stage": "plan", "queries": plan["search_queries"], "schema": schema})

    if cancelled():
        return await _do_cancel(db, run_id, trace)

    # ── Phase 2: Agentic research loop ────────────────────────────────────────
    final_records: list[dict] = []
    final_summary: str        = ""
    done_called               = False

    await pub({"type": "status", "message": "Starting agentic research loop…"})

    sem:        asyncio.Semaphore   = asyncio.Semaphore(FETCH_CONCURRENCY)
    page_cache: dict                = {}
    tools                           = _build_tools()
    iterations                      = 0
    _nudge_sent                     = False

    system_msg = f"""You are an expert web researcher and data extractor. Collect data to answer:
"{goal}"

Extraction schema — one record = one item matching the goal:
{json.dumps(schema, indent=2)}

Suggested starting queries: {json.dumps(plan["search_queries"])}

Tool guide — use the right tool for each situation:
• web_search      → discover URLs and sources; use when you don't know the URL
• fetch_html      → for LISTING / SEARCH / ROOT pages where you want structured records extracted.
                    Cascade: API endpoint → RSS feed → static HTML → stealth → JS render.
                    ALWAYS pass keyword= so API discovery builds the correct query.
                    Examples: product listings, job boards, site homepages, search pages.
• fetch_content   → for READING a specific page you already have the URL for: articles, news
                    stories, blog posts, reports, documentation. No API/feed probing.
• scrape_listing  → systematically extract ALL items from a listing/category/search result page,
                    paginating automatically. Use when you have a listing URL and need everything.
                    Pass goal= to describe what to extract. Records are auto-saved.
• fetch_structured → extract hidden metadata (JSON-LD, RSS) from a URL. Use as fallback only.
• get_links       → extract all hyperlinks from a page; use for pagination or finding detail pages
• read_sitemap    → discover all page URLs on a structured site
• read_feed       → get RSS/Atom headline entries (title/url/date only — NOT full content).
                    Use to discover article URLs, then fetch each with fetch_content.

Research strategy:
0. **For goals requesting a list, ranking, or "top N" items** (e.g. jobs, products, companies):
   use web_search to find the best listing URL, then call scrape_listing on it with goal= describing
   what to extract. scrape_listing auto-paginates and saves all records — prefer it over fetch_html
   for any goal that needs multiple items from a listing or category page.
   - If the goal asks for ≤ 20 items ("top 5", "top 10"), set max_pages=1 to avoid over-fetching.
1. **If the goal names a specific website** (e.g. "from RemoteOK", "on GitHub", "from Hacker News"),
   call scrape_listing (or fetch_html) on that site's URL IMMEDIATELY with the correct keyword= parameter.
   Do NOT call web_search first — you already know the URL.
2. For news/article goals: use web_search or read_feed to discover URLs, then call fetch_content
   on each article URL to get full content. Feed results are headlines only — always follow up.
3. Use web_search to discover unknown URLs, then:
   - scrape_listing → listing/search/category pages where you need multiple records (auto-paginates)
   - fetch_html     → listing pages when scrape_listing is not suitable
   - fetch_content  → specific article/page URLs
4. On listing pages: extract ALL visible items in one pass — do NOT fetch individual detail pages
   one-by-one unless the listing only has headlines/summaries (articles, news).
5. After EVERY tool call that yields useful data, call add_records() with ALL records found.
   Note: fetch_html and scrape_listing auto-save records from feed/api strategies — do NOT call add_records() again.
6. Keep fetching until you have 50+ records or have exhausted all good sources.
7. Call done() when finished — pass only a one-sentence summary.

Schema discipline: populate every field you can find; omit fields you cannot determine."""

    # ── Prepend prior conversation context if this is a follow-up ─────────────
    if context:
        system_msg = (
            "CONVERSATION HISTORY (prior turns in this session):\n"
            f"{context}\n\n"
            "---\n\n"
            "You are continuing the above conversation. Use the prior context to understand "
            "what the user already knows and build on it naturally.\n\n"
        ) + system_msg

    if plan.get("response_format") == "prose":
        system_msg += """

IMPORTANT — This goal requires a synthesized prose answer, not a list of records.
Use fetch_content (not fetch_html) to read article/page content directly.
Gather information from multiple sources, then call done() with a brief summary when ready.
Calling add_records() is optional — only if you encounter clearly structured items worth saving.
Zero records is perfectly fine for informational, analytical, or explanatory goals."""

    contents: list = [
        types.Content(role="user", parts=[types.Part(text=system_msg)])
    ]

    while not done_called and iterations < MAX_AGENT_ITERATIONS and not cancelled():
        iterations += 1
        contents = _prune_contents(contents, page_cache, final_records)
        logger.info("[%s] iteration %d/%d", run_id[:8], iterations, MAX_AGENT_ITERATIONS)

        try:
            response = await _generate_with_retry(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[tools],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode=types.FunctionCallingConfigMode.ANY,
                        )
                    ),
                    temperature=0.2,
                    max_output_tokens=8192,
                ),
            )
        except Exception as exc:
            logger.error("[%s] LLM call failed at iteration %d: %s", run_id[:8], iterations, exc)
            await pub({"type": "error", "detail": f"LLM error: {exc}"})
            break

        # Append model turn to conversation
        if response.candidates and response.candidates[0].content:
            contents.append(response.candidates[0].content)

        if not response.function_calls:
            # With ANY mode this should not happen — only on safety blocks or API errors
            logger.warning("[%s] no function calls returned at iteration %d", run_id[:8], iterations)
            # One recovery attempt: inject a hard nudge so the model calls done()
            if not _nudge_sent and trace:
                _nudge_sent = True
                logger.info("[%s] injecting done() nudge after empty response", run_id[:8])
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        "You MUST act now. First call add_records() with every article/profile/item "
                        "you found in the tool results above. Then call done() with a summary. "
                        "Do NOT generate plain text — you must call tools."
                    ))],
                ))
                continue
            break

        # ── Execute each tool call in this turn ───────────────────────────────
        tool_response_parts: list = []

        for fc in response.function_calls:
            args = dict(fc.args) if fc.args else {}
            await pub({"type": "progress",
                       "message": f"→ {fc.name}({_summarize_args(args)})"})

            if fc.name == "add_records":
                records_raw = args.get("records_json", "[]")
                try:
                    parsed   = _parse_json(records_raw) if isinstance(records_raw, str) else records_raw
                    new_recs = parsed if isinstance(parsed, list) else []
                except Exception as e:
                    logger.warning("Failed to parse add_records json: %s", e)
                    new_recs = []
                added = _merge_records(final_records, new_recs)
                trace.append({"stage": "add_records", "new": added, "total": len(final_records)})
                await pub({"type": "progress",
                           "message": f"→ Saved {added} records (total: {len(final_records)})"})
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name="add_records",
                        response={"saved": added, "total": len(final_records)},
                    )
                )
                continue  # keep processing other tool calls in this turn

            if fc.name == "done":
                final_summary = args.get("summary", "")
                done_called = True
                trace.append({"stage": "done", "records": len(final_records)})
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name="done", response={"result": "Research complete"}
                    )
                )
                break   # stop processing further tool calls in this turn

            result = await _dispatch_tool(fc.name, args, sem, page_cache, pub, final_records, trace)

            # When fetch_html resolved via feed/api, pre-parsed records are available.
            # For API/static strategies: auto-save immediately.
            # For feed strategy: do NOT auto-save headlines — return article URLs for the agent to fetch.
            if fc.name == "fetch_html":
                url = args.get("url", "")
                pre_records = (page_cache.get(url) or {}).get("records") or []
                strategy    = (page_cache.get(url) or {}).get("strategy", "")
                if pre_records:
                    if strategy == "feed":
                        # Feed entries are RSS headlines only (title/url/summary/published).
                        # Don't save them as records — give the agent the article URLs to fetch.
                        article_urls = [
                            r.get("url") or r.get("link", "")
                            for r in pre_records
                            if r.get("url") or r.get("link")
                        ]
                        article_urls = [u for u in article_urls if u][:15]
                        await pub({"type": "progress",
                                   "message": f"→ Feed: {len(pre_records)} headlines found — fetching articles next"})
                        result = (
                            f"Found {len(pre_records)} RSS/Atom feed entries (headlines only — title/url/date, NO detailed content). "
                            f"Do NOT save these as records and do NOT call done(). "
                            f"You MUST fetch the individual article URLs to get real content. "
                            f"Fetch these URLs now using fetch_html:\n"
                            + "\n".join(f"- {u}" for u in article_urls)
                        )
                    else:
                        added = _merge_records(final_records, pre_records)
                        if added:
                            trace.append({"stage": "auto_add_records", "new": added, "total": len(final_records)})
                            await pub({"type": "progress",
                                       "message": f"→ Auto-saved {added} records from {strategy} (total: {len(final_records)})"})
                            result = (
                                f"Fetched via '{strategy}' strategy. "
                                f"Auto-saved {added} structured records to buffer (total: {len(final_records)}). "
                                f"Record fields: {list(pre_records[0].keys())}. "
                                f"Do NOT call add_records() for these — they are already saved. "
                                f"Call done() if you have enough records, or search for more sources."
                            )

            trace.append({
                "tool":        fc.name,
                "args":        args,
                "result_size": len(str(result)),
            })
            tool_response_parts.append(
                types.Part.from_function_response(name=fc.name, response={"result": result})
            )

        if tool_response_parts:
            contents.append(types.Content(role="user", parts=tool_response_parts))

        if done_called:
            break

    # ── Finalise ──────────────────────────────────────────────────────────────
    if cancelled():
        return await _do_cancel(db, run_id, trace)

    if not final_records and not done_called:
        await _update(db, run_id,
                      status=AgentStatus.FAILED,
                      error="Agent completed without collecting any records.",
                      trace=json.dumps(trace),
                      completed_at=_now())
        return await pub({"type": "error", "detail": "No records collected."})

    total_time = time.monotonic() - t_start
    logger.info(
        "[%s] DONE — %d records | %d pages cached | %d iterations | %.1fs",
        run_id[:8], len(final_records), len(page_cache), iterations, total_time,
    )

    await pub({"type": "status", "message": "Formatting response…"})
    # source_url = first page fetched; used to make relative URLs absolute
    source_url = next(iter(page_cache), "")
    formatted = await _format_response(
        goal, final_records, final_summary, list(page_cache.keys()),
        source_url=source_url,
        response_format=plan.get("response_format", "tabular"),
    )

    await _update(db, run_id,
                  status=AgentStatus.COMPLETED,
                  result=json.dumps(final_records, ensure_ascii=False),
                  summary=final_summary,
                  formatted_response=formatted,
                  trace=json.dumps(trace),
                  iterations=iterations,
                  completed_at=_now())

    await pub({
        "type":    "done",
        "rows":    len(final_records),
        "summary": final_summary,
        "message": (
            f"Done — {len(final_records)} records from "
            f"{len(page_cache)} pages in {total_time:.0f}s."
        ),
    })


# ── Response formatter ────────────────────────────────────────────────────────

_FORMAT_SYSTEM_TABULAR = """\
You are a research assistant. Answer the user's goal using ONLY the data provided.

Rules:
- Only include the information the user explicitly asked for. Ignore all other fields in the records.
- Write 2–5 short paragraphs of plain prose. No markdown tables, no bullet lists, no headers.
- Highlight the most relevant findings. Do not list every record verbatim.
- Do not output raw field names, column headers, tab-separated data, or JSON blobs.
- If a requested field (e.g. salary) is missing or unclear for a record, say so briefly rather than showing a raw or empty value.
- Do not include any URLs unless the user specifically asked for them.\
"""

_FORMAT_SYSTEM_PROSE = """\
You are a research assistant. Write a thorough, well-structured response that directly answers
the user's goal based on the information collected.

Use markdown freely: headings (##/###), bullet lists, numbered lists, bold, comparison tables,
code blocks — whatever best presents the answer. Be direct and informative.

Guidelines:
- Answer the question fully. Don't just summarise — give the actual information.
- Use a table only if it genuinely helps compare or organise data.
- Keep it focused: no filler, no "I found that..." preamble.
- Include relevant URLs as markdown links [text](url) where they add value.\
"""


_SLIM_KEEP_KEYS = {
    "title", "position", "name", "company", "location", "published", "date",
    "tags", "summary", "description", "salary", "salaryRange", "salary_range",
    "requirements", "techStack", "tech_stack", "url", "profile_url",
    "employmentType", "locationType",
}


def _flatten_value(val):
    """Convert nested dicts/lists to a readable string."""
    if isinstance(val, dict):
        if "min" in val or "max" in val or "from" in val or "to" in val:
            lo = val.get("min") or val.get("from") or ""
            hi = val.get("max") or val.get("to") or ""
            if lo and hi:
                return f"{lo}–{hi}"
            return str(lo or hi or "")
        return ", ".join(f"{k}: {v}" for k, v in val.items() if v is not None)
    if isinstance(val, list):
        return ", ".join(str(x) for x in val[:8])
    return val


def _slim_record(r: dict) -> dict:
    """Keep only informative keys and flatten nested values."""
    slimmed = {k: _flatten_value(v) for k, v in r.items() if k in _SLIM_KEEP_KEYS}
    return slimmed


def _is_tabular(records: list[dict]) -> bool:
    """True if records look like a homogeneous list (jobs, people, articles)."""
    if len(records) < 2:
        return False
    keys0 = set(records[0].keys())
    # At least 2/3 of records share the same key set
    matches = sum(1 for r in records[1:10] if set(r.keys()) == keys0)
    return matches >= min(2, len(records) - 1)


def _make_url_absolute(url: str, source_url: str) -> str:
    """Convert a relative URL to absolute using the source page's origin."""
    if not url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    try:
        from urllib.parse import urlparse, urljoin
        return urljoin(source_url, url)
    except Exception:
        return url


def _build_table(records: list[dict], source_url: str = "") -> str:
    """
    Build a Markdown table from records with correct absolute URLs.
    URL/profile_url columns are made absolute and shown as clickable links.
    """
    if not records:
        return ""

    # Determine which fields to show (skip long/html fields, prefer key fields first)
    priority = ["title", "position", "name", "company", "location", "published", "date",
                "tags", "summary", "description"]
    url_fields = {"url", "profile_url", "link"}

    all_keys = list(records[0].keys())
    # Show priority fields first, then remaining non-url fields, url fields last
    ordered = [k for k in priority if k in all_keys]
    ordered += [k for k in all_keys if k not in ordered and k not in url_fields]
    url_col  = next((k for k in url_fields if k in all_keys), None)
    if url_col:
        ordered.append(url_col)

    # Truncate long text columns for readability
    def _cell(val, key: str) -> str:
        flat = _flatten_value(val)
        s = str(flat).strip() if flat is not None else ""
        if key in ("summary", "description") and len(s) > 120:
            s = s[:120] + "…"
        if key == url_col and s:
            abs_url = _make_url_absolute(s, source_url)
            return f"[{abs_url}]({abs_url})"
        return s

    header = " | ".join(k.replace("_", " ").title() for k in ordered)
    sep    = " | ".join("---" for _ in ordered)
    rows   = []
    for r in records:
        row = " | ".join(_cell(r.get(k), k) for k in ordered)
        rows.append(row)

    return "| " + header + " |\n| " + sep + " |\n" + "\n".join("| " + row + " |" for row in rows)


async def _format_response(
    goal: str,
    records: list[dict],
    summary: str,
    sources: list[str],
    source_url: str = "",
    response_format: str = "tabular",
) -> str:
    """
    Build the formatted response.
    - tabular: prose narrative summarising collected records (no markdown structure).
    - prose: full markdown response — headings, lists, tables — for informational/analytical goals.
    """
    # Collect verified source URLs (from records + pages visited)
    seen_src: set[str] = set()
    deduped_sources: list[str] = []
    for r in records:
        for field in ("url", "profile_url"):
            u = _make_url_absolute(r.get(field, "") or "", source_url)
            if u and u not in seen_src:
                seen_src.add(u)
                deduped_sources.append(u)
    for u in sources:
        u = _make_url_absolute(u or "", source_url)
        if u and u not in seen_src:
            seen_src.add(u)
            deduped_sources.append(u)
    deduped_sources = deduped_sources[:20]

    # Normalise record URLs to absolute before passing to LLM and table builder
    normalised_records = []
    for r in records:
        nr = dict(r)
        for field in ("url", "profile_url"):
            if nr.get(field):
                nr[field] = _make_url_absolute(nr[field], source_url)
        normalised_records.append(nr)

    # Ask LLM for narrative prose only (no table, no URLs)
    # Slim records: drop localised/irrelevant keys, flatten nested objects
    slimmed_records = [_slim_record(r) for r in normalised_records[:20]]
    records_preview = json.dumps(slimmed_records, ensure_ascii=False, indent=2)
    user_msg = (
        f"Goal: {goal}\n\n"
        f"Summary: {summary}\n\n"
        f"Total records collected: {len(records)}\n\n"
        f"Sample records (first 20):\n{records_preview}"
    )

    system_prompt = _FORMAT_SYSTEM_PROSE if response_format == "prose" else _FORMAT_SYSTEM_TABULAR
    max_tokens    = 2048 if response_format == "prose" else 1024

    body = summary  # fallback
    try:
        resp = await _generate_with_retry(
            model=settings.GEMINI_MODEL,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                max_output_tokens=max_tokens,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        body = resp.text.strip()
    except Exception as exc:
        logger.warning("_format_response LLM call failed: %s — using summary", exc)

    return body


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _do_cancel(db: AsyncSession, run_id: str, trace: list) -> None:
    logger.info("[%s] Agent cancelled", run_id[:8])
    await _update(db, run_id, status=AgentStatus.CANCELLED,
                  trace=json.dumps(trace), completed_at=_now())
    await sse_manager.publish(run_id, {"type": "status", "message": "Cancelled."})


async def _update(db: AsyncSession, run_id: str, **kwargs) -> None:
    res = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = res.scalar_one_or_none()
    if run:
        for k, v in kwargs.items():
            setattr(run, k, v)
        await db.commit()
    else:
        logger.error("_update: run_id %s not found", run_id)
