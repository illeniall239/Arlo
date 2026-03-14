# Changelog — Arlo (AI Web Scraper)

All notable changes documented here. Newest first.
Format: `[DATE] TYPE: Description`
Types: FEAT, FIX, REFACTOR, BREAKING, CHORE

---

## [2026-03-14] FIX: Deterministic URL extraction — _validate_urls replaces title-matching

**Root cause chain:**
1. `re.sub(r'[*_`~]', '', md)` was stripping underscores inside `[LINK:url]` markers after
   link conversion → `a-light-in-the-attic_1000` became `a-light-in-the-attic1000`
2. Jina markdown uses `[text](url "Title")` — the regex was capturing the title as part of the URL
3. Title-matching in the old `_enrich_with_urls` caused false URL assignments on short nav links

**`backend/app/services/ai_pipeline.py`**
- `_markdown_to_text()`: Underscore stripping now uses `re.split(r'(\[LINK:[^\]]*\])', md)` to
  split on link markers first; markdown formatting is only stripped from non-link segments
- `_clean_url(url)`: Strips Markdown title attributes via `re.sub(r'\s+["'][^"']*["']', '', url)`
  Applied in both `_build_link_map` and wherever URLs are parsed from raw markdown
- `_build_link_map(md, base_url)`: Builds ground-truth `{anchor_text_lower → absolute_url}` dict
  from raw Jina markdown before any text conversion. Skips images and utility URLs
- `_validate_urls(records, valid_urls)`: Post-extraction validation. Removes `url` field from
  any record whose URL Gemini produced but does not exist in the ground-truth set. No guessing.
- Removed `_enrich_with_urls` and `_normalize_for_match` — title-matching entirely eliminated
- `extract()`: Builds `link_map` for markdown input; calls `_validate_urls(records, link_map.values())`
  after Gemini extraction. HTML input path unchanged.

---

## [2026-03-14] FIX: Navigation/category over-extraction (books.toscrape page 1: 71→20 records)

**Root cause:** Homepage had a 50-category grid absent on sub-pages. `_EXTRACT_SYSTEM` had no
rule distinguishing main-content items from navigation chrome.

**`backend/app/services/ai_pipeline.py`**
- Added to `_EXTRACT_SYSTEM`:
  `"- Ignore navigation menus, sidebars, breadcrumbs, headers, footers, and category/tag listings
  unless the goal explicitly asks for them. Only extract items from the main content area."`

---

## [2026-03-14] FEAT: All jobs listing page at /jobs

**`frontend/app/jobs/page.tsx`** — new file
- Paginated listing of all past jobs (page_size=20)
- Reads `data.data` array and `data.meta.total` from `/jobs/` endpoint (correct API shape)
- Columns: domain (hostname), goal (prompt truncated), status badge, date, open-in-new link
- Pagination: Previous / Next buttons, "Page N of M" label

**`frontend/app/history/page.tsx`** — replaced
- Now simply `redirect("/jobs")` — old "Search runs" / agent-history page removed

**`frontend/components/layout/Sidebar.tsx`**
- Fixed API field: `data.items` → `data.data` (jobs were silently not appearing)
- Added "All jobs" nav link (IconSearch icon, active when pathname === "/jobs")
- "New research" button: active state (`var(--sidebar-active)` background) only when
  `pathname === "/dashboard"`, not always-on
- Removed "Your trial ends in 7 days" upgrade card
- Removed footer links: Help Center, Settings, Sign out
- Removed grid icon button from logo row

**`frontend/components/jobs/NewJobForm.tsx`**
- Fires `window.dispatchEvent(new Event("arlo:new-run"))` immediately after job creation,
  before `router.push()` — sidebar recent list updates instantly

---

## [2026-03-14] FIX: Terminal jobs show static completion message (no "Waiting for job to start…")

**Root cause:** `useJobSSE` always opened an SSE connection; SSE messages are ephemeral (real-time
only, not stored). Revisiting a completed job → empty message list → "Waiting for job to start…"

**`frontend/components/stream/LiveStatusFeed.tsx`**
- Added `jobStatus` prop
- `const isTerminal = TERMINAL.has(jobStatus ?? "")` — skips SSE connection for completed/failed/cancelled
- `useJobSSE(jobId, !isTerminal)` — `autoConnect=false` for terminal jobs
- Static fallback for empty message list:
  - completed → "✓ Job completed" (lime)
  - failed    → "✗ Job failed" (red)
  - cancelled → "— Job was cancelled" (grey)

**`frontend/app/jobs/[id]/page.tsx`**
- Passes `jobStatus={job.status}` to `<LiveStatusFeed />`
- Back button now routes to `/jobs` (was `/history`)

---

## [2026-03-14] FIX: Submit button uses lime theme color (was orange)

**`frontend/app/dashboard/page.tsx`**
- Submit button: `background: "var(--lime)"`, `color: "#111"` (was hardcoded orange)
- Disabled state: `background: "var(--border-strong)"` (unchanged)

---

## [2026-03-11] FEAT: Sidebar — recent scrape jobs replace agent history

**`frontend/components/layout/Sidebar.tsx`**
- Removed "Search runs" nav link (was pointing to `/history` agent runs page)
- Recent section now fetches from `/jobs/?page_size=5` instead of `/agents/?limit=3`
- Each recent item shows: status dot (lime=completed, amber=running, red=failed, grey=pending),
  domain name extracted from `job.url` (e.g. `remoteok.com`), links to `/jobs/{id}`
- `RecentRun` interface replaced with `RecentJob {id, url, prompt, status}`
- `"arlo:new-run"` window event still refreshes the list after a new job starts

---

## [2026-03-11] FIX: Universal record normalizer prevents blank table cells

**`backend/app/utils/normalizer.py`** — new file
- `flatten_value(val)` — recursively flattens nested dicts and lists to readable scalars:
  - Range dicts `{minValue, maxValue, unitText}` → `"90,000–130,000/YEAR"`
  - Named entities `{name: "Acme Corp"}` → `"Acme Corp"`
  - Generic dicts → `"key: value, key: value"` pairs
  - Lists → comma-joined strings
  - Strips HTML tags from string values
- `flatten_record(record)` — applies `flatten_value` to every field, drops empty keys
- `normalize_records(records)` — batch flatten + dedup by content hash

**`backend/app/services/embedded.py`**
- `_extract_next_data` and `_extract_nuxt` now call `flatten_record()` on each extracted dict
- Added `_CONTENT_FIELDS` set and `_looks_like_content(records)` quality gate:
  rejects records where <50% have content-indicating fields (description, salary, location, etc.)
  — prevents site-level schema.org metadata (Organization blocks) from being returned as results
- `extract_embedded` now gates all results through `_looks_like_content`
- Removed `Organization` from `_USEFUL_TYPES` (always site-level metadata, never content)
- JSON-LD min_records_to_trust raised to 3 (1-2 records is usually site metadata)

**`backend/app/services/ai_pipeline.py`**
- Added rule to `_EXTRACT_SYSTEM` prompt: all field values must be plain scalars; nested objects
  or arrays must be joined with `, `

**`backend/app/services/job_runner.py`**
- `_execute_pipeline`: applies `flatten_record` to all records before DB save (safety net)
- Schema computed from ALL records (union of keys), not just the first record

---

## [2026-03-11] FIX: JS-heavy / infinite-scroll sites now scrape correctly

**Root cause:** For JS-heavy sites (e.g. remoteok.com):
1. curl_cffi returns placeholder HTML (28KB, mostly nav/header)
2. `_is_js_heavy()` fires → browser render called → embedded succeeds
3. But pagination loop continued trying URL-based page navigation (none exist on infinite-scroll sites)
4. Result: only first render's records, pagination silently broke

**`backend/app/services/scraper.py`**
- `_run_browser_scroll_sync(url, max_scrolls, target_count)` — Playwright-based scroll loop:
  scrolls to bottom, waits 1.5s, checks page height growth; stops at plateau or target count
  Runs in dedicated thread with `asyncio.ProactorEventLoop()` (Windows SelectorEventLoop cannot
  spawn subprocesses required by Playwright/Camoufox)
- `fetch_with_scroll(url, max_scrolls=15, target_count=150)` — async wrapper using ThreadPoolExecutor
- `fetch_browser(url)` — now delegates to `fetch_with_scroll(url, max_scrolls=0)` (single render, no scroll)

**`backend/app/services/job_runner.py`**
- Added `_is_js_heavy(html)` heuristic:
  - Visible text ratio < 4% of total HTML length, OR
  - ≥ 3 placeholder/skeleton elements (`class="placeholder"`, `class="skeleton"`, etc.), OR
  - Empty SPA mount point (`<div id="app"></div>`, `<div id="root"></div>` with no children)
- JS-heavy path in `_run_paginated_extraction`:
  - Calls `fetch_with_scroll(url, max_scrolls=15, target_count=150)` — one render covers all content
  - Tries embedded extractors on rendered HTML
  - Falls back to Jina+Gemini if embedded fails
  - **Breaks out of page loop immediately** — infinite-scroll sites have no URL-based pages

---

## [2026-03-11] FIX: Removed 10-minute duplicate job check

**`backend/app/routers/jobs.py`**
- Removed deduplication check that rejected jobs identical to one submitted in the last 10 minutes
- Removed unused `timedelta` import
- Users can now resubmit the same URL+prompt immediately

---

## [2026-03-11] FEAT: Max Pages parameter in Crawl mode

**`frontend/app/dashboard/page.tsx`**
- Added `maxPages` state (default 10), number input (range 1–100) shown only when `mode === "crawl"`
- Label corrected to "Max Pages" (capital P)
- `createJob()` now passes `max_pages: maxPages` instead of hardcoded 10

---

## [2026-03-06] REFACTOR: Replaced two-stage Gemini + Scrapling CSS pipeline with text-based extraction

**Breaking change — entire scraping pipeline redesigned.**

### Old pipeline
1. Fetch page preview (Scrapling Fetcher)
2. Gemini Stage 1: analyze HTML → generate CSS selectors + fetcher choice
3. Scrapling Stage 2: execute selectors with chosen fetcher
4. Gemini Stage 3: normalize raw records

### New pipeline
1. curl_cffi raw fetch (Chrome TLS fingerprint) → embedded extractor attempt
2. JS-heavy check → browser render with scroll if needed
3. Jina Reader fetch → Gemini reads plain markdown → records + pagination info

### Why
- CSS selectors break on redesigns; Gemini reading plain text is more robust
- Jina handles anti-bot and JS rendering transparently — no Playwright dependency for most sites
- Embedded extraction (window.mosaic, apolloState, __NEXT_DATA__) is faster and more accurate
  than any LLM when data is pre-rendered in `<script>` tags

**`backend/app/services/ai_pipeline.py`** — full rewrite
- Single `extract(url, goal, html)` function
- Auto-detects Jina markdown vs raw HTML input, strips to plain text accordingly
- `_html_to_text()`: preserves `[LINK:url]` markers from anchor hrefs, strips scripts/styles
- `_markdown_to_text()`: converts `[text](url)` → `text [LINK:url]`, strips markdown syntax
- `_strip_tracking_params()`: cleans URLs with >150-char query strings
- Returns `(records, has_next_page, next_button_selector)`
- Retry wrapper for Gemini 503/500/UNAVAILABLE with exponential backoff

**`backend/app/services/scraper.py`** — full rewrite
- `fetch_jina(url)` — Jina Reader via `r.jina.ai/{url}`, returns markdown
- `fetch_raw(url)` — curl_cffi Chrome120 impersonation, returns raw HTML
- `fetch_browser(url)` — Scrapling StealthyFetcher → DynamicFetcher fallback, in ProactorEventLoop thread
- `fetch_plain(url)` — plain httpx GET for JSON APIs / RSS feeds
- `fetch_with_scroll(url, max_scrolls, target_count)` — Playwright with scroll loop

**`backend/app/services/embedded.py`** — new file
- In-page script extractors for common SPA patterns (no LLM needed)
- `_extract_indeed()`: `window.mosaic.providerData["mosaic-provider-jobcards"]`
- `_extract_glassdoor()`: Apollo GraphQL cache (`apolloState`) with `__ref` resolution
- `_extract_json_ld()`: `<script type="application/ld+json">` schema.org blocks
- `_extract_next_data()`: `<script id="__NEXT_DATA__">` Next.js hydration payload
- `_extract_nuxt()`: `window.__NUXT__` / `<script id="__NUXT_DATA__">` Nuxt.js state

**`backend/app/services/site_apis.py`** — new file
- Tier 0 handlers that bypass HTML scraping entirely
- `fetch_indeed(url)`: Indeed Jobs API (`https://apis.indeed.com/graphql`)
- `fetch_linkedin(url)`: LinkedIn Jobs API
- `fetch_glassdoor(url)`: Glassdoor Jobs API
- `_SITE_MATCHERS`: regex → handler dispatch table

**`backend/app/services/job_runner.py`** — major rewrite
- `_run_paginated_extraction()`: main loop, calls tiers in order, handles pagination
- `_scan_next_page_url()`: finds next-page URLs in page content (regex + heuristics)
- Publishes SSE events at each tier transition

---

## [2026-03-05] FEAT: Full project scaffold

### Backend
- `main.py` — FastAPI + CORS + SlowAPI rate limiting + lifespan DB init
- `app/core/` — config (pydantic-settings), async SQLAlchemy, rate limiter
- `app/models/` — ScrapeJob, ScrapeResult ORM models
- `app/schemas/` — Pydantic request/response schemas
- `app/routers/` — jobs (CRUD + stream + export), settings
- `app/utils/sse_manager.py` — in-process asyncio.Queue SSE pub/sub
- `app/utils/cancellation.py` — cooperative cancellation registry
- `app/services/export.py` — JSON + CSV export

### Frontend
- Next.js 14 App Router + TypeScript, inline styles (not Tailwind)
- Pages: /dashboard, /jobs/[id], /history, /settings
- Components: NewJobForm, ResultsTable, ExportButtons, Sidebar
- `lib/api.ts` — typed fetch wrappers for all backend endpoints

---

## [2026-03-05] CHORE: Project initialized

- Created project structure in CareerAI/
- Defined tech stack: FastAPI + Gemini + curl_cffi + Jina Reader + SQLite + Next.js
- Created context.md, changes.md, system_design.txt
- Chose Gemini for AI layer (JSON mode, 1M context)
- Chose SSE over WebSockets for real-time job updates
- Chose FastAPI BackgroundTasks over Celery for MVP simplicity

---
<!-- Add new entries above this line, newest first -->
