"""Live career-page source connector boundary.

This module is the future home for the working Job Radar scraper currently in:

- `jobsearch/job-radar/src/scraper.py`
- `jobsearch/job-radar/src/cache.py`
- `jobsearch/job-radar/src/job_extractor.py`

v0.1 defines the connector boundary without making network calls. The fixture
source in `career_agent.sources.opportunities` remains the credential-free demo
path until the live scraper is ported.
"""

from __future__ import annotations

from dataclasses import dataclass

from career_agent.core import Opportunity
from career_agent.sources.opportunities import Organization


@dataclass(frozen=True)
class CareerPageSourceConfig:
    """Configuration for target-organization career-page scanning."""

    organizations: tuple[Organization, ...]
    timeout_seconds: int = 30
    max_retries: int = 3
    use_content_cache: bool = True


class CareerPageSource:
    """Live source for organization watchlist career pages."""

    source_name = "career_page"

    def __init__(self, config: CareerPageSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch opportunities from configured career pages.

        Porting target:
        1. Fetch each `Organization.career_url`.
        2. Use content hashing to avoid unnecessary LLM extraction.
        3. Extract visible jobs.
        4. Normalize each result into `Opportunity(source="career_page")`.
        """
        raise NotImplementedError("Live career-page scraping will be ported after v0.1 fixtures")
