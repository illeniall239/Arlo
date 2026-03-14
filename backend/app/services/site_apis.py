"""
site_apis.py — Site-specific API clients for job boards that block standard scrapers.

Bypasses HTML scraping by hitting internal/unofficial APIs directly:
  - Indeed:    apis.indeed.com/graphql        — mobile app GraphQL, iPhone UA, API key
  - LinkedIn:  jobs-guest REST API             — semi-public, no auth, returns HTML cards
  - Glassdoor: glassdoor.com/graph             — Apollo GraphQL + CSRF token

Technique sourced from: https://github.com/speedyapply/JobSpy

Returns list[dict] records — no Jina, no Gemini, no curl_cffi.
"""

import json
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)


# ── Indeed ─────────────────────────────────────────────────────────────────────

_INDEED_URL = "https://apis.indeed.com/graphql"

_INDEED_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8",
    "accept": "application/json",
    "indeed-locale": "en-US",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

# Double-braces {{ }} become literal { } after .format()
_INDEED_QUERY = """
query GetJobData {{
    jobSearch(
        {what}
        {location}
        limit: 100
        {cursor}
        sort: RELEVANCE
    ) {{
        pageInfo {{
            nextCursor
        }}
        results {{
            job {{
                key
                title
                datePublished
                description {{ html }}
                location {{
                    countryCode
                    admin1Code
                    city
                    formatted {{ short long }}
                }}
                compensation {{
                    estimated {{
                        currencyCode
                        baseSalary {{
                            unitOfWork
                            range {{ ... on Range {{ min max }} }}
                        }}
                    }}
                    baseSalary {{
                        unitOfWork
                        range {{ ... on Range {{ min max }} }}
                    }}
                    currencyCode
                }}
                attributes {{ key label }}
                employer {{
                    relativeCompanyPageUrl
                    name
                }}
                recruit {{ viewJobUrl }}
            }}
        }}
    }}
}}
"""


# ── LinkedIn ───────────────────────────────────────────────────────────────────

_LINKEDIN_BASE = "https://www.linkedin.com"
_LINKEDIN_API  = f"{_LINKEDIN_BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"

_LINKEDIN_HEADERS = {
    "authority": "www.linkedin.com",
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# ── Glassdoor ──────────────────────────────────────────────────────────────────

_GLASSDOOR_BASE          = "https://www.glassdoor.com"
_GLASSDOOR_URL           = f"{_GLASSDOOR_BASE}/graph"
_GLASSDOOR_FALLBACK_TOKEN = (
    "Ft6oHEWlRZrxDww95Cpazw:0pGUrkb2y3TyOpAIqF2vbPmUXoXVkD3oEGDVkvfeCerceQ5-"
    "n8mBg3BovySUIjmCPHCaW0H2nQVdqzbtsYqf4Q:wcqRqeegRUa9MVLJGyujVXB7vWFPjdaS1CtrrzJq-ok"
)

_GLASSDOOR_HEADERS = {
    "authority": "www.glassdoor.com",
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "apollographql-client-name": "job-search-next",
    "apollographql-client-version": "4.65.5",
    "content-type": "application/json",
    "origin": "https://www.glassdoor.com",
    "referer": "https://www.glassdoor.com/",
    "sec-ch-ua": '"Chromium";v="118", "Google Chrome";v="118", "Not=A?Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "gd-csrf-token": _GLASSDOOR_FALLBACK_TOKEN,
}

_GLASSDOOR_QUERY = """
    query JobSearchResultsQuery(
        $excludeJobListingIds: [Long!],
        $keyword: String,
        $locationId: Int,
        $locationType: LocationTypeEnum,
        $numJobsToShow: Int!,
        $pageCursor: String,
        $pageNumber: Int,
        $filterParams: [FilterParams],
        $originalPageUrl: String,
        $seoFriendlyUrlInput: String,
        $parameterUrlInput: String,
        $seoUrl: Boolean
    ) {
        jobListings(
            contextHolder: {
                searchParams: {
                    excludeJobListingIds: $excludeJobListingIds,
                    keyword: $keyword,
                    locationId: $locationId,
                    locationType: $locationType,
                    numPerPage: $numJobsToShow,
                    pageCursor: $pageCursor,
                    pageNumber: $pageNumber,
                    filterParams: $filterParams,
                    originalPageUrl: $originalPageUrl,
                    seoFriendlyUrlInput: $seoFriendlyUrlInput,
                    parameterUrlInput: $parameterUrlInput,
                    seoUrl: $seoUrl,
                    searchType: SR
                }
            }
        ) {
            jobListings {
                ...JobView
                __typename
            }
            paginationCursors {
                cursor
                pageNumber
                __typename
            }
            totalJobsCount
            __typename
        }
    }

    fragment JobView on JobListingSearchResult {
        jobview {
            header {
                adOrderSponsorshipLevel
                ageInDays
                employer { id name shortName __typename }
                employerNameFromSearch
                jobTitleText
                locationName
                locationType
                payPeriod
                payPeriodAdjustedPay { p10 p50 p90 __typename }
                payCurrency
                salarySource
                __typename
            }
            job {
                description
                jobTitleText
                listingId
                __typename
            }
            overview {
                shortName
                squareLogoUrl
                __typename
            }
            __typename
        }
        __typename
    }
"""


# ── URL parameter extraction ───────────────────────────────────────────────────

def _indeed_params(url: str) -> tuple[str, str, str]:
    """Return (search_term, location, country_code) from an Indeed URL.

    Handles both query-string format (?q=python+developer&l=Remote)
    and path-based format (/q-python-developer-l-Remote-jobs.html).
    """
    import re as _re
    parsed = urlparse(url)
    qs     = parse_qs(parsed.query)
    term   = qs.get("q", [""])[0]
    loc    = qs.get("l", [""])[0]

    # Handle path-based format: /q-python-developer-l-Remote-jobs.html
    if not term:
        path = parsed.path
        # With location: /q-{query}-l-{location}-jobs[.html]
        m = _re.search(r"/q-(.+?)-l-(.+?)-jobs(?:\.html)?(?:\?|$)", path)
        if m:
            term = m.group(1).replace("-", " ")
            loc  = m.group(2).replace("-", " ")
        else:
            # Without location: /q-{query}-jobs[.html]
            m = _re.search(r"/q-(.+?)-jobs(?:\.html)?(?:\?|$)", path)
            if m:
                term = m.group(1).replace("-", " ")

    netloc = parsed.netloc.lower()
    if netloc.startswith("uk."):
        country = "GB"
    elif netloc.startswith("ca."):
        country = "CA"
    elif netloc.startswith("au."):
        country = "AU"
    elif netloc.startswith("in."):
        country = "IN"
    else:
        country = "US"

    return term, loc, country


def _linkedin_params(url: str) -> tuple[str, str]:
    """Return (keywords, location) from a LinkedIn jobs URL."""
    parsed   = urlparse(url)
    qs       = parse_qs(parsed.query)
    keywords = qs.get("keywords", [""])[0]
    location = qs.get("location", [""])[0]

    if not keywords:
        # /jobs/search/software-engineer-jobs → "software engineer"
        m = re.search(r"/jobs/(?:search/)?([^/?]+?)(?:-jobs)?/?$", parsed.path, re.I)
        if m:
            keywords = m.group(1).replace("-", " ").strip()

    return keywords, location


def _glassdoor_params(url: str) -> str:
    """Extract search keyword from a Glassdoor URL."""
    parsed = urlparse(url)
    qs     = parse_qs(parsed.query)

    keyword = qs.get("keyword", qs.get("q", [""]))[0]
    if keyword:
        return keyword

    # /Job/software-engineer-jobs-SRCH_KO0,17.htm
    # /Job/us-software-engineer-jobs-SRCH_IL.0,2_IN1_KO3,20.htm
    m = re.search(
        r"/(?:Job|Jobs)/(?:[a-z]{2}-)?(.+?)-jobs-SRCH",
        parsed.path,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).replace("-", " ").strip()

    return ""


# ── Record mappers ─────────────────────────────────────────────────────────────

def _indeed_salary(comp: dict) -> str:
    """Extract a human-readable salary string from an Indeed compensation dict."""
    for section in ("baseSalary", "estimated"):
        node = comp.get(section) or {}
        if section == "estimated":
            node = node.get("baseSalary") or {}
        r = node.get("range") or {}
        lo, hi = r.get("min"), r.get("max")
        if lo and hi:
            unit     = node.get("unitOfWork", "")
            currency = (
                comp.get("currencyCode")
                or (comp.get("estimated") or {}).get("currencyCode", "USD")
            )
            return f"{currency} {lo:,.0f}–{hi:,.0f}/{unit}" if unit else f"{currency} {lo:,.0f}–{hi:,.0f}"
    return ""


def _indeed_record(job: dict, base_url: str = "https://www.indeed.com") -> dict | None:
    key   = job.get("key", "")
    title = job.get("title", "")
    if not title:
        return None

    employer = job.get("employer") or {}
    company  = employer.get("name", "")

    loc_obj  = job.get("location") or {}
    location = (
        (loc_obj.get("formatted") or {}).get("short")
        or ", ".join(filter(None, [loc_obj.get("city"), loc_obj.get("admin1Code")]))
    )

    salary = _indeed_salary(job.get("compensation") or {})

    indeed_url  = f"{base_url}/viewjob?jk={key}" if key else ""
    apply_url   = (job.get("recruit") or {}).get("viewJobUrl", "")
    # Use Indeed listing URL as canonical; include direct employer URL separately
    url         = indeed_url or apply_url

    desc_html = (job.get("description") or {}).get("html", "")
    desc      = re.sub(r"<[^>]+>", " ", desc_html).strip()[:800] if desc_html else ""

    return {k: v for k, v in {
        "title":       title,
        "company":     company,
        "location":    location,
        "salary":      salary,
        "description": desc,
        "url":         url,
        "apply_url":   apply_url if apply_url != indeed_url else "",
    }.items() if v}


def _linkedin_cards(html: str) -> list[dict]:
    """Parse LinkedIn job cards HTML into list[dict]. Requires beautifulsoup4."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 not installed — run: pip install beautifulsoup4")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_=lambda c: c and "base-search-card" in c)
    jobs  = []

    for card in cards:
        link = card.find("a", class_=lambda c: c and "base-card__full-link" in c)
        href = link.get("href", "").split("?")[0] if link else ""
        job_id = href.rstrip("/").split("-")[-1] if href else ""

        title_tag   = card.find("span", class_="sr-only")
        company_tag = card.find("h4", class_=lambda c: c and "base-search-card__subtitle" in c)
        loc_tag     = card.find("span", class_=lambda c: c and "job-search-card__location" in c)
        time_tag    = card.find("time")
        salary_tag  = card.find("span", class_=lambda c: c and "job-search-card__salary-info" in c)

        title   = title_tag.get_text(strip=True)   if title_tag   else ""
        company = company_tag.get_text(strip=True)  if company_tag else ""
        loc     = loc_tag.get_text(strip=True)      if loc_tag     else ""
        date    = time_tag.get("datetime", "")      if time_tag    else ""
        salary  = salary_tag.get_text(strip=True)   if salary_tag  else ""

        if not title:
            continue

        jobs.append({
            "_id":         job_id,
            "title":       title,
            "company":     company,
            "location":    loc,
            "salary":      salary,
            "date_posted": date,
            "url":         href,
        })

    return jobs


def _glassdoor_record(listing: dict, base_url: str) -> dict | None:
    jv      = listing.get("jobview") or {}
    header  = jv.get("header") or {}
    job     = jv.get("job") or {}
    overview = jv.get("overview") or {}

    title   = header.get("jobTitleText") or job.get("jobTitleText", "")
    if not title:
        return None

    company  = header.get("employerNameFromSearch") or (header.get("employer") or {}).get("name", "")
    location = header.get("locationName", "")
    loc_type = header.get("locationType", "")
    is_remote = loc_type == "S"
    if is_remote:
        location = "Remote"

    listing_id = job.get("listingId", "")
    url = f"{base_url}/job-listing/j?jl={listing_id}" if listing_id else ""

    # Salary from payPeriodAdjustedPay (p10/p50/p90 range)
    salary = ""
    pay = header.get("payPeriodAdjustedPay") or {}
    p10, p90 = pay.get("p10"), pay.get("p90")
    currency = header.get("payCurrency", "USD")
    period   = header.get("payPeriod", "")
    if p10 and p90:
        salary = f"{currency} {p10:,.0f}–{p90:,.0f}/{period}" if period else f"{currency} {p10:,.0f}–{p90:,.0f}"

    desc_html = job.get("description", "")
    desc      = re.sub(r"<[^>]+>", " ", desc_html).strip()[:800] if desc_html else ""

    logo = overview.get("squareLogoUrl", "")

    return {k: v for k, v in {
        "title":       title,
        "company":     company,
        "location":    location,
        "salary":      salary,
        "description": desc,
        "url":         url,
        "logo":        logo,
    }.items() if v}


def _glassdoor_cursor(cursors: list, page_num: int) -> str | None:
    """Find the pagination cursor for the given page number."""
    for item in cursors or []:
        if item.get("pageNumber") == page_num:
            return item.get("cursor")
    return None


# ── Glassdoor helpers ──────────────────────────────────────────────────────────

async def _glassdoor_csrf(client: httpx.AsyncClient) -> str:
    """Fetch a live CSRF token from Glassdoor. Falls back to hardcoded token."""
    try:
        resp = await client.get(
            f"{_GLASSDOOR_BASE}/Job/computer-science-jobs.htm",
            timeout=10,
        )
        if resp.status_code == 200:
            tokens = re.findall(r'"token"\s*:\s*"([^"]+)"', resp.text)
            if tokens:
                logger.debug("Glassdoor: fresh CSRF token acquired")
                return tokens[0]
    except Exception as exc:
        logger.debug("Glassdoor CSRF fetch failed: %s", exc)
    logger.debug("Glassdoor: using fallback CSRF token")
    return _GLASSDOOR_FALLBACK_TOKEN


async def _glassdoor_location(
    client: httpx.AsyncClient, hint: str
) -> tuple[int, str]:
    """
    Resolve a location string to (locationId, locationType).
    Falls back to (1, "COUNTRY") = US nationwide.
    """
    if not hint:
        return 1, "COUNTRY"
    try:
        resp = await client.get(
            f"{_GLASSDOOR_BASE}/findPopularLocationAjax.htm",
            params={"maxLocationsToReturn": 5, "term": hint},
            timeout=10,
        )
        if resp.status_code == 200:
            items = resp.json()
            if items:
                _type_map = {"C": "CITY", "S": "STATE", "N": "COUNTRY"}
                lt = _type_map.get(items[0].get("locationType", "N"), "COUNTRY")
                return int(items[0]["locationId"]), lt
    except Exception as exc:
        logger.debug("Glassdoor location lookup failed: %s", exc)
    return 1, "COUNTRY"


# ── Fetchers ───────────────────────────────────────────────────────────────────

async def fetch_indeed(url: str, max_results: int = 100) -> list[dict]:
    """
    Fetch jobs from Indeed's internal mobile app GraphQL API.
    Bypasses all web-level bot detection — iPhone app UA + private API key.
    Returns up to max_results records.
    """
    term, location, country = _indeed_params(url)
    if not term:
        logger.warning("Indeed: no search term found in URL %s", url)

    base_url = f"https://{'www' if country == 'US' else country.lower()}.indeed.com"
    headers  = {**_INDEED_HEADERS, "indeed-co": country}

    records: list[dict] = []
    cursor: str | None  = None

    async with httpx.AsyncClient(timeout=20, verify=False) as client:
        while len(records) < max_results:
            what = f'what: "{term}"' if term else ""
            loc  = (
                f'location: {{where: "{location}", radius: 25, radiusUnit: MILES}}'
                if location else ""
            )
            cur  = f'cursor: "{cursor}"' if cursor else ""

            query = _INDEED_QUERY.format(what=what, location=loc, cursor=cur)

            try:
                resp = await client.post(
                    _INDEED_URL, headers=headers, json={"query": query}
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("Indeed API page failed: %s", exc)
                break

            search  = (data.get("data") or {}).get("jobSearch") or {}
            results = search.get("results") or []
            cursor  = (search.get("pageInfo") or {}).get("nextCursor")

            for r in results:
                rec = _indeed_record(r.get("job") or {}, base_url)
                if rec:
                    records.append(rec)

            logger.info("Indeed: page fetched — %d total records", len(records))

            if not results or not cursor or len(records) >= max_results:
                break

    logger.info("Indeed: %d records from %s", len(records), url)
    return records[:max_results]


async def fetch_linkedin(url: str, max_results: int = 100) -> list[dict]:
    """
    Fetch jobs from LinkedIn's semi-public jobs-guest REST API.
    No authentication required. Rate-limits around page 10 without proxies (~250 jobs).
    Returns up to max_results records.
    """
    keywords, location = _linkedin_params(url)

    records:  list[dict] = []
    seen_ids: set[str]   = set()
    start = 0

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers=_LINKEDIN_HEADERS,
    ) as client:
        while len(records) < max_results and start < 1000:
            params = {k: v for k, v in {
                "keywords": keywords,
                "location": location,
                "start":    start,
            }.items() if v is not None}

            try:
                resp = await client.get(_LINKEDIN_API, params=params)
            except Exception as exc:
                logger.warning("LinkedIn API error: %s", exc)
                break

            if resp.status_code == 429:
                logger.warning("LinkedIn: rate-limited at start=%d — stopping", start)
                break
            if resp.status_code not in range(200, 400):
                logger.warning("LinkedIn: status %d — stopping", resp.status_code)
                break

            cards = _linkedin_cards(resp.text)
            if not cards:
                break

            added = 0
            for card in cards:
                jid = card.get("_id")
                if jid and jid in seen_ids:
                    continue
                if jid:
                    seen_ids.add(jid)
                records.append({k: v for k, v in card.items() if k != "_id" and v})
                added += 1

            logger.info("LinkedIn: start=%d → +%d cards (%d total)", start, added, len(records))
            start += len(cards)

    logger.info("LinkedIn: %d records from %s", len(records), url)
    return records[:max_results]


async def fetch_glassdoor(url: str, max_results: int = 90) -> list[dict]:
    """
    Fetch jobs from Glassdoor's Apollo GraphQL API.
    Acquires a fresh CSRF token first; falls back to a hardcoded token.
    Returns up to max_results records (30 per page).
    """
    keyword = _glassdoor_params(url)

    records:  list[dict] = []
    seen_ids: set[str]   = set()

    headers = dict(_GLASSDOOR_HEADERS)

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers=headers,
    ) as client:
        # Step 1: CSRF token
        token = await _glassdoor_csrf(client)
        client.headers.update({"gd-csrf-token": token})

        # Step 2: Location resolution
        location_id, location_type = await _glassdoor_location(client, "")

        # Step 3: Paginated GraphQL
        cursor:   str | None = None
        page_num: int        = 1
        max_pages = max(1, (max_results + 29) // 30)

        while len(records) < max_results and page_num <= max_pages:
            param_url_input = f"IL.0,0_I{location_type}{location_id}"
            payload = [{
                "operationName": "JobSearchResultsQuery",
                "variables": {
                    "excludeJobListingIds": [],
                    "filterParams":        [],
                    "keyword":             keyword,
                    "numJobsToShow":       30,
                    "locationType":        location_type,
                    "locationId":          location_id,
                    "parameterUrlInput":   param_url_input,
                    "pageNumber":          page_num,
                    "pageCursor":          cursor,
                    "sort":                "date",
                },
                "query": _GLASSDOOR_QUERY,
            }]

            try:
                resp = await client.post(
                    _GLASSDOOR_URL,
                    content=json.dumps(payload),
                )
                resp.raise_for_status()
                res_json = resp.json()[0]
                if "errors" in res_json:
                    logger.warning("Glassdoor GraphQL errors: %s", res_json["errors"])
                    break
            except Exception as exc:
                logger.warning("Glassdoor API page %d failed: %s", page_num, exc)
                break

            listings_data = (
                (res_json.get("data") or {})
                .get("jobListings") or {}
            )
            listings  = listings_data.get("jobListings") or []
            cursors   = listings_data.get("paginationCursors") or []
            cursor    = _glassdoor_cursor(cursors, page_num + 1)

            for item in listings:
                rec = _glassdoor_record(item, _GLASSDOOR_BASE)
                if not rec:
                    continue
                lid = rec.get("url", "")
                if lid in seen_ids:
                    continue
                seen_ids.add(lid)
                records.append(rec)

            logger.info("Glassdoor: page %d → +%d listings (%d total)", page_num, len(listings), len(records))

            if not listings or not cursor:
                break

            page_num += 1

    logger.info("Glassdoor: %d records from %s", len(records), url)
    return records[:max_results]


# ── Public API ─────────────────────────────────────────────────────────────────

_SITE_MATCHERS: list[tuple[re.Pattern, object]] = [
    (re.compile(r"indeed\.com",    re.I), fetch_indeed),
    (re.compile(r"linkedin\.com",  re.I), fetch_linkedin),
    (re.compile(r"glassdoor\.com", re.I), fetch_glassdoor),
]


def is_supported_site(url: str) -> bool:
    """Return True if the URL is handled by a site-specific API client."""
    return any(pat.search(url) for pat, _ in _SITE_MATCHERS)


async def fetch_site_api(url: str, max_results: int = 100) -> list[dict]:
    """
    Route URL to the appropriate site-specific API client.
    Returns [] if no site matches or if the API call fails.
    """
    for pattern, fetcher in _SITE_MATCHERS:
        if pattern.search(url):
            try:
                return await fetcher(url, max_results)  # type: ignore[operator]
            except Exception as exc:
                logger.warning("Site API [%s] failed: %s", fetcher.__name__, exc)
            return []
    return []
