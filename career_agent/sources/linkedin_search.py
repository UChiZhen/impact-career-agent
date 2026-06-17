"""Live LinkedIn keyword search connector boundary.

This module is the future home for the working Apify integration currently in:

- `linkedin_email/src/apify_scraper.py`
- `linkedin_email/config/search_keywords.yaml`

The legacy source uses query dictionaries shaped as:

`keyword, location, region, category`
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import time
from typing import Any
from urllib.parse import quote

from career_agent.core import Opportunity
from career_agent.sources.opportunities import (
    LinkedInSearchQuery,
    dedupe_opportunities,
    opportunity_from_dict,
)


@dataclass(frozen=True)
class LinkedInSearchSourceConfig:
    """Configuration for Apify-backed LinkedIn keyword search."""

    queries: tuple[LinkedInSearchQuery, ...]
    actor_id: str = "curious_coder~linkedin-jobs-scraper"
    max_results_per_query: int = 10
    actor_timeout_seconds: int = 30
    max_total_jobs: int = 300
    inter_query_delay_seconds: float = 2.0
    api_token: str | None = None

    @classmethod
    def from_env(
        cls,
        *,
        queries: tuple[LinkedInSearchQuery, ...],
    ) -> "LinkedInSearchSourceConfig":
        """Build config from the original `linkedin_email` Apify environment."""
        return cls(
            queries=queries,
            actor_id=os.getenv("APIFY_ACTOR_ID", "curious_coder~linkedin-jobs-scraper"),
            max_results_per_query=int(os.getenv("APIFY_MAX_RESULTS_PER_QUERY", "10")),
            actor_timeout_seconds=int(os.getenv("APIFY_ACTOR_TIMEOUT_SECONDS", "30")),
            max_total_jobs=int(os.getenv("APIFY_MAX_TOTAL_JOBS", "300")),
            inter_query_delay_seconds=float(os.getenv("APIFY_INTER_QUERY_DELAY_SECONDS", "2")),
            api_token=os.getenv("APIFY_API_TOKEN"),
        )


class LinkedInSearchSource:
    """Live source for LinkedIn keyword/location search."""

    source_name = "linkedin_search"

    def __init__(self, config: LinkedInSearchSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch opportunities from LinkedIn search via Apify."""
        client = self.build_apify_client()
        return self.fetch_from_client(client)

    def build_apify_client(self):
        """Build an Apify client lazily so demo/test users do not need the package."""
        if not self.config.api_token:
            raise RuntimeError("Apify live source requires APIFY_API_TOKEN.")

        try:
            from apify_client import ApifyClient
        except ImportError as exc:
            raise RuntimeError(
                "Apify live source requires optional dependencies. "
                "Install with `pip install 'impact-career-agent[apify]'`."
            ) from exc

        return ApifyClient(self.config.api_token)

    def fetch_from_client(self, client: Any) -> list[Opportunity]:
        """Run configured Apify searches and normalize results."""
        opportunities: list[Opportunity] = []
        seen_urls: set[str] = set()

        for index, query in enumerate(self.config.queries):
            items = self.run_single_search(client, query)
            for item in items:
                normalized = normalize_apify_item(item, query)
                if not normalized:
                    continue

                job_url = normalized.get("job_url", "")
                if job_url and job_url in seen_urls:
                    continue
                if job_url:
                    seen_urls.add(job_url)

                opportunities.append(opportunity_from_dict(normalized))
                if len(opportunities) >= self.config.max_total_jobs:
                    return dedupe_opportunities(opportunities[: self.config.max_total_jobs])

            if index < len(self.config.queries) - 1 and self.config.inter_query_delay_seconds > 0:
                time.sleep(self.config.inter_query_delay_seconds)

        return dedupe_opportunities(opportunities)

    def run_single_search(self, client: Any, query: LinkedInSearchQuery) -> list[dict]:
        """Run one Apify actor search and return raw dataset items."""
        run_input = {
            "urls": [build_linkedin_search_url(query.keyword, query.location)],
            "maxItems": self.config.max_results_per_query,
            "scrapeJobDetails": False,
            "proxy": {"useApifyProxy": True},
        }
        run = client.actor(self.config.actor_id).call(
            run_input=run_input,
            timeout_secs=self.config.actor_timeout_seconds,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        return items[: self.config.max_results_per_query]


def build_linkedin_search_url(keyword: str, location: str) -> str:
    """Build the LinkedIn search URL used by the original Apify scraper."""
    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote(keyword)}"
        f"&location={quote(location)}"
        "&f_TPR=r86400"
    )


def normalize_apify_item(item: dict, query: LinkedInSearchQuery) -> dict:
    """Normalize one Apify LinkedIn item into the shared opportunity shape."""
    raw_url = item.get("jobUrl") or item.get("link") or item.get("url", "")
    match = re.search(r"(https?://(?:www\.)?linkedin\.com/jobs/view/[^?&\s]+)", raw_url)
    job_url = match.group(1) if match else raw_url
    title = item.get("title") or item.get("jobTitle", "")
    if not title:
        return {}

    return {
        "source": "linkedin_search",
        "source_detail": "apify_keyword",
        "job_title": title.strip(),
        "company": (item.get("companyName") or item.get("company", "")).strip(),
        "location": (item.get("location") or item.get("jobLocation", "")).strip(),
        "job_url": job_url.strip(),
        "posted_date": item.get("postedAt", ""),
        "description_snippet": (item.get("description") or "")[:500],
        "applicant_count": item.get("applicantsCount", ""),
        "search_keyword": query.keyword,
        "search_location": query.location,
        "search_region": query.region,
        "search_category": query.category,
    }
