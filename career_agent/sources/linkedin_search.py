"""Live LinkedIn keyword search connector boundary.

This module is the future home for the working Apify integration currently in:

- `linkedin_email/src/apify_scraper.py`
- `linkedin_email/config/search_keywords.yaml`

The legacy source uses query dictionaries shaped as:

`keyword, location, region, category`
"""

from __future__ import annotations

from dataclasses import dataclass

from career_agent.core import Opportunity
from career_agent.sources.opportunities import LinkedInSearchQuery


@dataclass(frozen=True)
class LinkedInSearchSourceConfig:
    """Configuration for Apify-backed LinkedIn keyword search."""

    queries: tuple[LinkedInSearchQuery, ...]
    actor_id: str = "curious_coder~linkedin-jobs-scraper"
    max_results_per_query: int = 10
    actor_timeout_seconds: int = 30
    max_total_jobs: int = 300
    api_token: str | None = None


class LinkedInSearchSource:
    """Live source for LinkedIn keyword/location search."""

    source_name = "linkedin_search"

    def __init__(self, config: LinkedInSearchSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch opportunities from LinkedIn search via Apify.

        Porting target:
        1. Build LinkedIn search URLs from `LinkedInSearchQuery`.
        2. Run the configured Apify actor.
        3. Cap per-query and total result counts.
        4. Normalize each result into `Opportunity(source="linkedin_search")`.
        """
        raise NotImplementedError("Live LinkedIn search will be ported after v0.1 fixtures")
