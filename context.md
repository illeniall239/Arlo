# Project Context — Arlo (AI Web Scraper)

## What This Is
Arlo is an AI-powered universal web scraper. The user describes what they want to extract in
plain English, points it at any URL, and the system handles everything: fetching the page,
bypassing anti-bot protection, extracting structured data, handling pagination, and returning
a clean downloadable table.

The app runs as a local web application: FastAPI backend + Next.js frontend.

## Core Philosophy
- **Natural language first** — no CSS selectors or XPath from the user ever
- **Text-based AI extraction** — Gemini reads plain text (not raw HTML) from Jina Reader;
  no selector generation, no brittle DOM-walking
- **Embedded data first** — many modern sites pre-render their full dataset in `<script>` tags;
  we extract it directly (zero LLM cost, highest fidelity)
- **Tiered resilience** — three fetch tiers tried in order; Jina is the universal fallback
- **Universal normalization** — nested JSON in extracted records is flattened to readable
  scalars before storage; no band-aids per site
- **Cloud-deployable** — no Playwright, no Chromium, no browser infrastructure required;
  Docker image ~200MB

## Extraction Pipeline (Three Tiers)

```
URL submitted
    │
    ├─ Tier 0: Site-specific API (Indeed, LinkedIn, Glassdoor)
    │           Direct structured JSON — no HTML, no AI
    │
    ├─ Tier 1: curl_cffi raw HTML (Chrome TLS fingerprint)
    │           → embedded extractors (window.mosaic, apolloState, JSON-LD, Next.js, Nuxt)
    │           → Jina Reader + Gemini on failure
    │
    └─ Tier 2 (was Tier 3): Jina Reader + Gemini
                Jina converts any URL to clean markdown (handles JS, Cloudflare)
                Gemini reads plain text → structured JSON records
```

Note: Playwright/browser rendering was removed. Jina handles JS and Cloudflare transparently
on its servers. This keeps the stack cloud-deployable with no Chromium dependency.

## Architecture Decision Log

### ADR-001: Backend — FastAPI
**Reason:** Async-native, Pydantic v2 built-in, BackgroundTasks for job execution, minimal
boilerplate. No Django overhead for what is essentially a job queue + API.

### ADR-002: AI Layer — Gemini via `google-genai` SDK
**Model:** `gemini-2.5-flash` (configurable via `GEMINI_MODEL`)
**Reason:** 1M token context window, `response_mime_type="application/json"` guarantees
valid JSON output, strong at reading and structuring prose/markdown content.
**Usage:** Single extraction stage — receives Jina markdown (or raw HTML stripped to text),
returns `{records: [...], has_next_page: bool, next_button_selector: str|null}`.
No "planning" stage — Gemini reads visible text directly.

### ADR-003: Fetching — curl_cffi as Tier 1, Jina as Tier 2
**curl_cffi:** Chrome TLS fingerprint impersonation — bypasses JA3/JA4 detection at the
handshake level. Used for raw HTML to attempt embedded data extraction first.
**Jina Reader (r.jina.ai):** Universal fallback for everything. Jina handles JS rendering
and Cloudflare internally and returns clean markdown. No browser needed on our side.
**Playwright removed:** Was Tier 2. Removed to enable cloud deployment — Docker image went
from ~1.2GB to ~200MB. Jina covers the JS-rendering use case transparently.

### ADR-004: Embedded Data Extraction Before AI
**Reason:** Many high-value sites (Indeed, Glassdoor, Next.js apps, Nuxt apps) pre-render
their full dataset in `<script>` tags. Extracting it directly is faster, cheaper, and more
accurate than sending the page to Gemini. Extractors: `window.mosaic` (Indeed),
`apolloState` (Glassdoor), `application/ld+json` (schema.org), `__NEXT_DATA__` (Next.js),
`__NUXT__` / `__NUXT_DATA__` (Nuxt.js).

### ADR-005: Universal Record Normalizer
**Reason:** Embedded extractors (especially Next.js/JSON-LD) return nested objects like
`{base_salary: {minValue: 90000, maxValue: 130000, unitText: "YEAR"}}`. Storing these as-is
breaks the UI table. `flatten_record()` in `normalizer.py` converts every nested value to a
readable scalar before storage — no per-site special cases.

### ADR-006: Database — SQLite + SQLAlchemy (async)
**Reason:** Single-user local app. Zero infrastructure. `aiosqlite` driver makes it compatible
with FastAPI's async model. Swap to PostgreSQL by changing one connection string.

### ADR-007: Real-time — SSE over WebSockets
**Reason:** Job updates are server → client only. SSE is simpler, HTTP/1.1 compatible, and
has native browser `EventSource` support with auto-reconnect.

### ADR-008: Job execution — FastAPI BackgroundTasks
**Reason:** MVP scope. No Redis broker or separate worker process needed. CancellationRegistry
provides cooperative cancellation between stages.

### ADR-009: Frontend — Next.js App Router, inline styles (no Tailwind)
**Reason:** App Router colocates layouts cleanly. Inline styles are used throughout for
complete style isolation and no build-time CSS dependency.

### ADR-010: Deterministic URL extraction from Jina markdown
**Reason:** Gemini was hallucinating item URLs (wrong slugs, missing underscores). Fix: build
a `link_map {anchor_text → url}` from raw Jina markdown BEFORE text conversion, then call
`_validate_urls()` post-extraction to remove any URL Gemini fabricated that doesn't exist on
the page. URLs are always sourced from actual page content, never from Gemini's language model.

## Project Structure
```
CareerAI/
├── context.md              ← this file
├── changes.md              ← living changelog
├── system_design.txt       ← system design deep-dive
├── backend/
│   ├── main.py             ← FastAPI app, CORS, lifespan DB init
│   ├── requirements.txt
│   ├── app/
│   │   ├── core/           ← config (pydantic-settings), DB engine, rate limiter
│   │   ├── models/         ← ScrapeJob, ScrapeResult ORM models
│   │   ├── schemas/        ← Pydantic request/response schemas
│   │   ├── routers/        ← jobs (CRUD + stream + export), settings
│   │   ├── services/
│   │   │   ├── job_runner.py    ← orchestrates the 3-tier pipeline + pagination
│   │   │   ├── ai_pipeline.py   ← Jina markdown → Gemini → structured records
│   │   │   ├── scraper.py       ← fetch_raw, fetch_jina, fetch_plain
│   │   │   ├── embedded.py      ← in-page script tag extractors (no LLM)
│   │   │   ├── site_apis.py     ← Tier 0 site-specific API handlers
│   │   │   └── export.py        ← JSON / CSV export
│   │   └── utils/
│   │       ├── normalizer.py    ← flatten_record / flatten_value / normalize_records
│   │       ├── sse_manager.py   ← in-process asyncio.Queue SSE pub/sub
│   │       └── cancellation.py  ← cooperative cancellation registry
└── frontend/
    ├── app/
    │   ├── dashboard/page.tsx    ← job submission form (Scrape / Crawl modes)
    │   ├── jobs/page.tsx         ← all past jobs listing
    │   ├── jobs/[id]/page.tsx    ← live job status + results table
    │   ├── history/page.tsx      ← redirects to /jobs
    │   └── settings/page.tsx     ← app settings
    ├── components/
    │   ├── layout/Sidebar.tsx    ← nav + recent jobs + "All jobs" link
    │   ├── jobs/NewJobForm.tsx   ← fires arlo:new-run event on job creation
    │   └── stream/LiveStatusFeed.tsx  ← SSE log; static summary for terminal jobs
    └── hooks/
        └── useJobSSE.ts          ← SSE hook; autoConnect=false for terminal jobs
```

## Key Files
| File | Purpose |
|---|---|
| `backend/app/services/job_runner.py` | 3-tier pipeline orchestrator, pagination loop, `_scan_next_page_url` |
| `backend/app/services/ai_pipeline.py` | Jina markdown → plain text → Gemini → records; URL validation |
| `backend/app/services/scraper.py` | fetch_raw (curl_cffi) / fetch_jina / fetch_plain |
| `backend/app/services/embedded.py` | In-page script extractors (Indeed, Glassdoor, JSON-LD, Next.js, Nuxt) |
| `backend/app/services/site_apis.py` | Tier 0 handlers (Indeed, LinkedIn, Glassdoor direct APIs) |
| `backend/app/utils/normalizer.py` | Universal record normalization (flatten nested dicts/lists) |
| `frontend/components/layout/Sidebar.tsx` | Sidebar with recent jobs, "All jobs" nav link |
| `frontend/app/jobs/page.tsx` | Paginated listing of all past jobs |

## Running the App
```bash
# Backend
cd backend
venv/Scripts/activate
uvicorn main:app --reload --workers 1

# Frontend (separate terminal)
cd frontend
npm run dev
```
Backend: http://localhost:8000
Frontend: http://localhost:3000
API Docs: http://localhost:8000/docs

## Environment Variables
```
# backend/.env
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash
JINA_API_KEY=jina_...           # optional — raises Jina rate limits
UPSTASH_REDIS_URL=rediss://...  # optional — enables multi-worker SSE
DB_PATH=./scraper.db
ALLOWED_ORIGINS=http://localhost:3000

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Current Status
- [x] Backend scaffolded (FastAPI, SQLAlchemy, SSE, cancellation)
- [x] 3-tier extraction pipeline (Tier 0: site APIs, Tier 1: curl_cffi + embedded, Tier 2: Jina + Gemini)
- [x] Playwright/Scrapling removed — cloud-deployable, ~200MB Docker image
- [x] Embedded data extractors (Indeed, Glassdoor, JSON-LD, Next.js, Nuxt.js)
- [x] Universal record normalizer (flatten nested objects to readable scalars)
- [x] Jina + Gemini text-based extraction pipeline
- [x] Universal pagination: rel=next, "Next" text, query-param math, path-number increment
- [x] Deterministic URL extraction: link_map from Jina markdown + _validate_urls post-extraction
- [x] URL fixes: underscore protection in [LINK:...] markers, Markdown title attribute stripping
- [x] Extraction prompt: ignores navigation/sidebar/category items (main content only)
- [x] Frontend: dashboard (Scrape/Crawl), job detail, all-jobs listing, settings
- [x] Sidebar: recent jobs, "All jobs" nav, fires arlo:new-run on job creation
- [x] Job detail: terminal jobs show static completion message (no "Waiting..." for old jobs)
- [x] Theme: lime (#c9f135) accent throughout, no orange, no trial/upgrade card
