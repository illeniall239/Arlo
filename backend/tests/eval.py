"""
Evaluation suite for the universal scraper pipeline.

Unit tests  — pure logic, no network, run instantly.
Integration — real HTTP + Gemini, marked @pytest.mark.integration.

Run all:          pytest backend/tests/eval.py -v
Run unit only:    pytest backend/tests/eval.py -v -m "not integration"
Run integration:  pytest backend/tests/eval.py -v -m integration
"""

import json
import asyncio
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(coro):
    """Run a coroutine in a test."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests — no network, no LLM
# ══════════════════════════════════════════════════════════════════════════════

class TestBlockDetection:
    """_is_blocked should catch bot-wall pages and pass real content."""

    def setup_method(self):
        from app.services.agent_runner import _is_blocked
        self.check = _is_blocked

    def test_cloudflare_caught(self):
        assert self.check("Just a moment... Checking your browser before accessing")

    def test_captcha_caught(self):
        assert self.check("Please complete the CAPTCHA to verify you are human")

    def test_ray_id_caught(self):
        assert self.check("Error 1020 Ray ID: abc123 • Cloudflare")

    def test_access_denied_caught(self):
        assert self.check("403 Forbidden — Access Denied")

    def test_real_content_passes(self):
        assert not self.check("Senior Python Developer — Remote — $120k — Apply now at Acme Corp")

    def test_short_but_clean_passes(self):
        assert not self.check("Python jobs board. 50 listings found.")


class TestDomainDedup:
    """_discover should never return two URLs from the same domain."""

    def test_no_duplicate_domains(self):
        from app.services.agent_runner import _discover

        async def _run():
            urls = await _discover(["python remote jobs", "python developer remote"])
            domains = [u.split("/")[2] for u in urls if u.count("/") >= 2]
            return domains

        domains = run(_run())
        assert len(domains) == len(set(domains)), (
            f"Duplicate domains found: {[d for d in domains if domains.count(d) > 1]}"
        )


class TestRecordDedup:
    """_record_key should identify same records across different formats."""

    def setup_method(self):
        from app.services.agent_runner import _record_key
        self.key = _record_key

    def test_same_job_different_case(self):
        r1 = {"title": "Python Developer", "company": "Acme Corp", "location": "Remote"}
        r2 = {"title": "PYTHON DEVELOPER", "company": "acme corp", "location": "Remote"}
        assert self.key(r1) == self.key(r2)

    def test_different_jobs_differ(self):
        r1 = {"title": "Python Developer", "company": "Acme", "location": "Remote"}
        r2 = {"title": "React Developer",  "company": "Acme", "location": "Remote"}
        assert self.key(r1) != self.key(r2)

    def test_url_used_when_no_title(self):
        r = {"url": "https://example.com/job/123", "salary": "$100k"}
        assert self.key(r) == "https://example.com/job/123"

    def test_full_json_fallback(self):
        r1 = {"price": "$10", "sku": "ABC"}
        r2 = {"price": "$20", "sku": "DEF"}
        assert self.key(r1) != self.key(r2)


class TestJsonParsing:
    """_parse_json should handle all Gemini output quirks."""

    def setup_method(self):
        from app.services.ai_pipeline import _parse_json
        self.parse = _parse_json

    def test_clean_array(self):
        result = self.parse('[{"a": 1}, {"b": 2}]')
        assert result == [{"a": 1}, {"b": 2}]

    def test_markdown_fences_stripped(self):
        result = self.parse('```json\n[{"a": 1}]\n```')
        assert result == [{"a": 1}]

    def test_trailing_comma_repaired(self):
        result = self.parse('[{"a": 1,}]')
        assert result == [{"a": 1}]

    def test_truncated_array_salvaged(self):
        # Truncated mid-record — salvage should return the complete first record
        truncated = '[{"title": "Job 1", "company": "Acme"}, {"title": "Job 2", "com'
        result = self.parse(truncated)
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["title"] == "Job 1"

    def test_missing_comma_repaired(self):
        # json_repair should handle this
        broken = '[{"a": 1}\n{"b": 2}]'
        result = self.parse(broken)
        assert isinstance(result, list)
        assert len(result) == 2


class TestStealhFirstDomains:
    """Known protected domains should skip static fetcher."""

    def setup_method(self):
        from app.services.agent_runner import _stealth_first
        self.check = _stealth_first

    def test_linkedin_stealth(self):
        assert self.check("https://www.linkedin.com/jobs/remote-python")

    def test_indeed_stealth(self):
        assert self.check("https://www.indeed.com/jobs?q=python")

    def test_unknown_domain_static(self):
        assert not self.check("https://pyjobs.com/remote-python-jobs")

    def test_weworkremotely_static(self):
        assert not self.check("https://weworkremotely.com/remote-python-jobs")


class TestJsonLdExtraction:
    """extract_jsonld should parse Schema.org types from raw HTML."""

    def setup_method(self):
        from app.services.structured_data import extract_jsonld
        self.extract = extract_jsonld

    def _wrap(self, obj: dict) -> str:
        return (
            '<html><head>'
            f'<script type="application/ld+json">{json.dumps(obj)}</script>'
            '</head><body>Hello</body></html>'
        )

    def test_job_posting_extracted(self):
        html = self._wrap({
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Senior Python Developer",
            "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
            "jobLocation": {"@type": "Place", "address": {"addressLocality": "Remote"}},
            "datePosted": "2026-03-06",
            "baseSalary": {"@type": "MonetaryAmount", "currency": "USD",
                           "value": {"minValue": 120000, "maxValue": 150000}},
        })
        records = self.extract(html, "https://example.com/jobs/1")
        assert len(records) == 1
        r = records[0]
        assert r["title"] == "Senior Python Developer"
        assert r["company"] == "Acme Corp"
        assert "120000" in r.get("salary", "")
        assert r["_schema_type"] == "JobPosting"

    def test_product_extracted(self):
        html = self._wrap({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Python Cookbook",
            "offers": {"@type": "Offer", "price": "39.99", "priceCurrency": "USD"},
        })
        records = self.extract(html, "https://example.com/product/1")
        assert len(records) == 1
        assert records[0]["name"] == "Python Cookbook"
        assert "39.99" in records[0].get("price", "")

    def test_article_extracted(self):
        html = self._wrap({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Python 4.0 Released",
            "datePublished": "2026-03-06",
            "author": {"@type": "Person", "name": "Jane Doe"},
        })
        records = self.extract(html, "https://news.example.com/article/1")
        assert len(records) == 1
        assert records[0]["title"] == "Python 4.0 Released"
        assert records[0]["author"] == "Jane Doe"

    def test_graph_array_expanded(self):
        html = self._wrap({
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "JobPosting", "title": "Job A",
                 "hiringOrganization": {"name": "Co A"}},
                {"@type": "JobPosting", "title": "Job B",
                 "hiringOrganization": {"name": "Co B"}},
            ],
        })
        records = self.extract(html)
        assert len(records) == 2
        titles = {r["title"] for r in records}
        assert titles == {"Job A", "Job B"}

    def test_webpage_type_skipped(self):
        html = self._wrap({"@context": "https://schema.org", "@type": "WebPage",
                           "name": "Home"})
        records = self.extract(html)
        assert records == []

    def test_multiple_script_blocks(self):
        html = (
            '<html><head>'
            f'<script type="application/ld+json">'
            f'{json.dumps({"@type": "JobPosting", "title": "Job A", "hiringOrganization": {"name": "X"}})}'
            '</script>'
            f'<script type="application/ld+json">'
            f'{json.dumps({"@type": "JobPosting", "title": "Job B", "hiringOrganization": {"name": "Y"}})}'
            '</script>'
            '</head></html>'
        )
        records = self.extract(html)
        assert len(records) == 2

    def test_malformed_json_skipped(self):
        html = (
            '<html><head>'
            '<script type="application/ld+json">{bad json}</script>'
            '</head></html>'
        )
        records = self.extract(html)
        assert records == []


class TestFeedDiscovery:
    """_find_advertised_feeds should detect <link rel='alternate'> feed URLs."""

    def setup_method(self):
        from app.services.structured_data import _find_advertised_feeds
        self.find = _find_advertised_feeds

    def test_rss_link_detected(self):
        html = '<link rel="alternate" type="application/rss+xml" href="/jobs.rss">'
        urls = self.find(html, "https://example.com/jobs")
        assert any("jobs.rss" in u for u in urls)

    def test_atom_link_detected(self):
        html = '<link rel="alternate" type="application/atom+xml" href="/atom.xml">'
        urls = self.find(html, "https://example.com")
        assert any("atom.xml" in u for u in urls)

    def test_relative_url_resolved(self):
        html = '<link rel="alternate" type="application/rss+xml" href="/feed">'
        urls = self.find(html, "https://example.com/jobs/python")
        assert "https://example.com/feed" in urls

    def test_no_feed_returns_empty(self):
        html = "<html><head><title>No feed here</title></head></html>"
        urls = self.find(html, "https://example.com")
        assert urls == []


class TestLoadMoreSelectors:
    """_LOAD_MORE_SELECTORS list should cover all common button patterns."""

    def setup_method(self):
        from app.services.scraper import _LOAD_MORE_SELECTORS
        self.selectors = _LOAD_MORE_SELECTORS

    def test_list_is_nonempty(self):
        assert len(self.selectors) >= 5

    def test_covers_load_more_text(self):
        joined = " ".join(self.selectors)
        assert "Load more" in joined

    def test_covers_show_more_text(self):
        joined = " ".join(self.selectors)
        assert "Show more" in joined

    def test_covers_data_attributes(self):
        joined = " ".join(self.selectors)
        assert "data-" in joined

    def test_no_duplicate_selectors(self):
        assert len(self.selectors) == len(set(self.selectors))


@pytest.mark.integration
class TestScrollHandler:
    """Real browser scroll tests — verifies load-more / infinite scroll behaviour."""

    CASES = [
        # (url, min_chars, description)
        # remoteok uses infinite scroll — plain static fetch gets ~10k chars,
        # scroll handler should get significantly more
        (
            "https://remoteok.com/remote-python-jobs",
            15_000,
            "remoteok — infinite scroll",
        ),
        # remoterocketship is a JS SPA — scroll handler renders and returns content
        (
            "https://remoterocketship.com/jobs/python",
            10_000,
            "remoterocketship — JS SPA",
        ),
    ]

    @pytest.mark.parametrize("url,min_chars,desc", CASES)
    def test_scroll_fetch(self, url, min_chars, desc):
        from app.services.scraper import fetch_with_scroll
        from app.services.ai_pipeline import _html_to_text

        async def _run():
            html = await fetch_with_scroll(url, max_scrolls=3)
            return html

        html = run(_run())
        assert html, f"{desc}: fetch_with_scroll returned empty"
        text = _html_to_text(html)
        assert len(text) >= min_chars, (
            f"{desc}: got {len(text)} chars after scroll, expected >= {min_chars}"
        )


class TestExtractOneReturnShape:
    """_extract_one must return a 3-tuple (url, records, next_url)."""

    def test_return_is_three_tuple(self):
        from app.services.agent_runner import _extract_one
        import asyncio

        async def _run():
            sem = asyncio.Semaphore(1)
            result = await _extract_one(
                "https://example.com",
                "title: Python Dev company: Acme location: Remote",
                {"title": "job title", "company": "company name"},
                "python developer jobs",
                sem,
            )
            return result

        result = run(_run())
        assert isinstance(result, tuple) and len(result) == 3, (
            f"Expected 3-tuple, got {type(result)} of length {len(result) if isinstance(result, tuple) else 'N/A'}"
        )
        url, records, next_url = result
        assert isinstance(url, str)
        assert isinstance(records, list)
        assert next_url is None or isinstance(next_url, str)


class TestResolveNextUrl:
    """_resolve_next_url should normalise / reject bad next_page values."""

    def setup_method(self):
        from app.services.agent_runner import _resolve_next_url
        self.resolve = _resolve_next_url

    def test_empty_string_returns_none(self):
        assert self.resolve("", "https://example.com/jobs") is None

    def test_none_returns_none(self):
        assert self.resolve(None, "https://example.com/jobs") is None

    def test_string_null_returns_none(self):
        assert self.resolve("null", "https://example.com/jobs") is None

    def test_same_url_returns_none(self):
        assert self.resolve("https://example.com/jobs", "https://example.com/jobs") is None

    def test_relative_url_resolved(self):
        result = self.resolve("/jobs?page=2", "https://example.com/jobs")
        assert result == "https://example.com/jobs?page=2"

    def test_absolute_url_returned_as_is(self):
        result = self.resolve("https://example.com/jobs?page=2", "https://example.com/jobs")
        assert result == "https://example.com/jobs?page=2"


class TestDomainThrottle:
    """_domain_throttle should enforce a delay between calls to aggressive domains."""

    def test_aggressive_domain_delays(self):
        from app.services.agent_runner import _domain_throttle, _domain_last_access
        import time

        domain = "linkedin.com"
        # Prime the tracker so next call will need to wait
        _domain_last_access[domain] = time.monotonic()

        async def _run():
            t0 = time.monotonic()
            await _domain_throttle(domain)
            return time.monotonic() - t0

        elapsed = run(_run())
        # Should have waited close to _PAGINATION_DELAY_AGGRESSIVE (4s)
        # We allow a wide range since we primed it at "now"
        assert elapsed >= 3.5, f"Expected ~4s delay, got {elapsed:.1f}s"

    def test_unknown_domain_short_delay(self):
        from app.services.agent_runner import _domain_throttle, _domain_last_access
        import time

        domain = "pyjobs.com"
        _domain_last_access[domain] = time.monotonic()

        async def _run():
            t0 = time.monotonic()
            await _domain_throttle(domain)
            return time.monotonic() - t0

        elapsed = run(_run())
        # Should have waited close to _PAGINATION_DELAY_DEFAULT (1s)
        assert 0.8 <= elapsed <= 2.0, f"Expected ~1s delay, got {elapsed:.1f}s"


# ══════════════════════════════════════════════════════════════════════════════
# Integration tests — real network + Gemini (slow, run explicitly)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestFetchCascade:
    """Real fetches — verify cascade picks the right fetcher and gets content."""

    CASES = [
        # (url, min_chars, description)
        ("https://pyjobs.com/remote-python-jobs",        3_000,  "pyjobs — static should work"),
        ("https://weworkremotely.com/remote-python-jobs", 5_000, "weworkremotely — static should work"),
        ("https://www.linkedin.com/jobs/remote-python-developer-jobs", 10_000, "linkedin — needs stealth"),
    ]

    @pytest.mark.parametrize("url,min_chars,desc", CASES)
    def test_fetch(self, url, min_chars, desc):
        from app.services.agent_runner import _fetch_one
        import asyncio

        async def _run():
            sem = asyncio.Semaphore(1)
            _, text, _ = await _fetch_one(url, sem)
            return text

        text = run(_run())
        assert text is not None, f"{desc}: fetch returned None"
        assert len(text) >= min_chars, (
            f"{desc}: only got {len(text)} chars, expected >= {min_chars}"
        )


@pytest.mark.integration
class TestExtraction:
    """
    Real extraction — uses the planner to generate the schema for each URL,
    same as the actual pipeline does. Avoids hardcoded schema mismatch.
    """

    CASES = [
        # (url, goal, min_records, description)
        ("https://weworkremotely.com/remote-python-jobs", "remote python developer jobs", 5,  "weworkremotely"),
        ("https://pyjobs.com/remote-python-jobs",         "remote python developer jobs", 3,  "pyjobs"),
        ("https://remoterocketship.com/jobs/python",      "remote python developer jobs", 5,  "remoterocketship"),
    ]

    @pytest.mark.parametrize("url,goal,min_records,desc", CASES)
    def test_extract(self, url, goal, min_records, desc):
        from app.services.agent_runner import _fetch_one, _extract_one, _plan

        async def _run():
            sem = asyncio.Semaphore(1)
            # Use planner schema — same as real pipeline
            plan = await _plan(goal)
            schema = plan["extraction_schema"]
            _, text = await _fetch_one(url, sem)
            assert text, f"{desc}: fetch returned None"
            _, records, _ = await _extract_one(url, text, schema, goal, sem)
            return records, schema

        records, schema = run(_run())
        assert len(records) >= min_records, (
            f"{desc}: got {len(records)} records (expected >= {min_records})\n"
            f"Schema used: {list(schema.keys())}\n"
            f"Sample: {json.dumps(records[:3], indent=2)}"
        )


@pytest.mark.integration
class TestFullPipeline:
    """End-to-end pipeline tests — given a goal, get >= N final records."""

    CASES = [
        # (goal, min_records)
        ("remote python developer jobs", 20),
        ("top AI startups 2024",         5),
        ("freelance web design jobs",    10),
    ]

    @pytest.mark.parametrize("goal,min_records", CASES)
    def test_pipeline(self, goal, min_records):
        from app.services.agent_runner import (
            _plan, _discover, _fetch_all, _filter_relevant,
            _extract_all, _aggregate,
        )

        async def _noop(*_args, **_kwargs):
            pass

        async def _run():
            plan                  = await _plan(goal)
            urls                  = await _discover(plan["search_queries"])
            fetch_sem             = asyncio.Semaphore(3)
            lm_cache, pre_extr    = await _fetch_all(urls, _noop, fetch_sem)
            lm_cache              = await _filter_relevant(lm_cache, goal, _noop)
            lm_records            = await _extract_all(lm_cache, plan["extraction_schema"], goal, _noop, fetch_sem)
            pre_records           = [r for recs in pre_extr.values() for r in recs]
            final, _              = await _aggregate(pre_records + lm_records, goal)
            return final

        records = run(_run())
        assert len(records) >= min_records, (
            f"Goal '{goal}': got {len(records)} records, expected >= {min_records}"
        )


@pytest.mark.integration
class TestPagination:
    """Pagination — extraction should follow next_page_url and return > page-1 records."""

    CASES = [
        # (url, goal, min_records_page1, description)
        # weworkremotely shows ~25 jobs per page — with pagination we should get more
        (
            "https://weworkremotely.com/remote-python-jobs",
            "remote python developer jobs",
            20,
            "weworkremotely (paginated)",
        ),
    ]

    @pytest.mark.parametrize("url,goal,min_records,desc", CASES)
    def test_pagination(self, url, goal, min_records, desc):
        from app.services.agent_runner import _fetch_one, _extract_with_pagination, _plan

        async def _run():
            fetch_sem   = asyncio.Semaphore(2)
            extract_sem = asyncio.Semaphore(2)
            plan        = await _plan(goal)
            schema      = plan["extraction_schema"]
            _, text, _  = await _fetch_one(url, fetch_sem)
            assert text, f"{desc}: fetch returned None"
            _, records  = await _extract_with_pagination(
                url, text, schema, goal, fetch_sem, extract_sem, max_pages=3
            )
            return records

        records = run(_run())
        assert len(records) >= min_records, (
            f"{desc}: got {len(records)} records across pages (expected >= {min_records})\n"
            f"Sample: {json.dumps(records[:3], indent=2)}"
        )
