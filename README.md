# Arlo

AI-powered universal web scraper. Paste a URL, describe what you want — Arlo handles the rest.

![Status](https://img.shields.io/badge/status-live-brightgreen)
![Backend](https://img.shields.io/badge/backend-FastAPI-009688)
![Frontend](https://img.shields.io/badge/frontend-Next.js-black)
![DB](https://img.shields.io/badge/database-Neon%20Postgres-3ECF8E)
![Deploy](https://img.shields.io/badge/deploy-Cloud%20Run-4285F4)

---

## What it does

Arlo extracts structured data from any website using a three-tier pipeline:

1. **Tier 0 — Site APIs** — Direct JSON for known sites (Indeed, LinkedIn, Glassdoor)
2. **Tier 1 — curl_cffi + embedded extractors** — Chrome TLS fingerprinting to bypass bot detection; pulls pre-rendered JSON from `<script>` tags (Next.js, Nuxt, JSON-LD, Apollo)
3. **Tier 2 — Jina Reader + Gemini** — Universal fallback. Jina converts any URL to clean markdown (handles JS, Cloudflare). Gemini reads plain text and returns structured records.

No CSS selectors. No XPath. No browser infrastructure required.

---

## Features

- Natural language extraction — describe what you want, not how to find it
- Scrape mode (single page) and Crawl mode (multi-page with pagination)
- Live activity feed via SSE while jobs run
- Export results as JSON or CSV
- Scheduled scrapes with diff tracking (added / changed / removed records)
- Universal record normalizer — nested JSON flattened to readable table cells

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Uvicorn |
| AI | Gemini 2.5 Flash (`google-genai`) |
| Fetching | curl_cffi (Chrome TLS), Jina Reader |
| Database | Neon (serverless Postgres) via asyncpg |
| Real-time | Server-Sent Events (SSE) |
| Frontend | Next.js 16, App Router, inline styles |
| Deploy | Google Cloud Run, Artifact Registry |
| CI/CD | GitHub Actions + Workload Identity Federation |

---

## Running locally

### Prerequisites
- Python 3.11+
- Node.js 20+
- A [Gemini API key](https://aistudio.google.com/app/apikey)
- A [Neon](https://neon.tech) database (or any Postgres instance)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Create `.env` in the project root:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname?ssl=require
JINA_API_KEY=your_key_here        # optional — raises rate limits
ALLOWED_ORIGINS=http://localhost:3000
```

```bash
uvicorn main:app --reload --workers 1
# http://localhost:8000
# http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

```bash
npm run dev
# http://localhost:3000
```

---

## Deployment

Deployed on **Google Cloud Run** (backend + frontend) with **Neon** as the database.

Every push to `main` triggers the GitHub Actions workflow which:
1. Builds and pushes Docker images to Artifact Registry
2. Deploys the backend Cloud Run service
3. Deploys the frontend Cloud Run service

Authentication uses Workload Identity Federation — no long-lived service account keys.

---

## Project structure

```
├── backend/
│   ├── main.py                      # FastAPI app entry point
│   ├── app/
│   │   ├── core/                    # Config, DB engine, rate limiter
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── routers/                 # API routes (jobs, results, schedules)
│   │   ├── services/
│   │   │   ├── job_runner.py        # 3-tier pipeline orchestrator
│   │   │   ├── ai_pipeline.py       # Jina markdown → Gemini → records
│   │   │   ├── scraper.py           # fetch_raw / fetch_jina / fetch_plain
│   │   │   ├── embedded.py          # Script tag extractors (no LLM)
│   │   │   └── site_apis.py         # Tier 0 direct API handlers
│   │   └── utils/
│   │       ├── normalizer.py        # Flatten nested records to scalars
│   │       └── sse_manager.py       # SSE pub/sub
└── frontend/
    ├── app/
    │   ├── dashboard/page.tsx       # Job submission
    │   ├── jobs/page.tsx            # All jobs listing
    │   └── jobs/[id]/page.tsx       # Live job detail + results
    └── components/
        ├── layout/Sidebar.tsx
        └── stream/LiveStatusFeed.tsx
```
