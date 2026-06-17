"""Opportunity source contracts and fixture implementations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import yaml

from career_agent.core import Opportunity


LINKEDIN_ALERT_SENDER = "jobalerts-noreply@linkedin.com"


class OpportunitySourceProvider(Protocol):
    """Source adapter that returns normalized opportunities."""

    source_name: str

    def fetch(self) -> list[Opportunity]:
        """Fetch and normalize opportunities."""


@dataclass(frozen=True)
class Organization:
    """Organization watchlist entry.

    Matches the working Job Radar sheet semantics:
    Organizations, Website, Locations, Relevant Industry.
    """

    name: str
    career_url: str
    location: str = ""
    industry: str = ""
    priority: int = 3
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkedInSearchQuery:
    """LinkedIn keyword/location query used by the Apify search source."""

    keyword: str
    location: str
    region: str
    category: str


def normalize_legacy_source(value: str) -> str:
    """Map legacy source labels into v0.1 source labels."""
    mapping = {
        "apify_search": "linkedin_search",
        "linkedin_apify": "linkedin_search",
        "career_site": "career_page",
        "job_radar": "career_page",
    }
    return mapping.get(value, value)


def opportunity_from_dict(item: dict) -> Opportunity:
    """Normalize a legacy/current job dict into an `Opportunity`."""
    source = normalize_legacy_source(item.get("source", "manual"))
    description = item.get("description") or item.get("description_snippet") or item.get("raw_text") or ""
    job_url = item.get("job_url") or item.get("url")

    return Opportunity(
        source=source,
        source_detail=item.get("source_detail"),
        job_title=item.get("job_title") or item.get("title") or "Untitled role",
        company=item.get("company") or item.get("org_name") or item.get("organization") or "",
        location=item.get("location", ""),
        job_url=job_url,
        origin_url=item.get("origin_url") or item.get("career_url"),
        description=description,
        post_date=item.get("post_date") or item.get("posted_date") or item.get("postedAt"),
        search_keyword=item.get("search_keyword"),
        search_location=item.get("search_location"),
        search_region=item.get("search_region"),
        search_category=item.get("search_category"),
        metadata=_string_metadata(
            item,
            exclude={
                "source",
                "source_detail",
                "job_title",
                "title",
                "company",
                "org_name",
                "organization",
                "location",
                "job_url",
                "url",
                "origin_url",
                "career_url",
                "description",
                "description_snippet",
                "raw_text",
                "post_date",
                "posted_date",
                "postedAt",
                "search_keyword",
                "search_location",
                "search_region",
                "search_category",
            },
        ),
    )


def dedupe_opportunities(opportunities: list[Opportunity]) -> list[Opportunity]:
    """Deduplicate opportunities by stable `Opportunity.dedup_key`."""
    seen: set[str] = set()
    unique: list[Opportunity] = []
    for opportunity in opportunities:
        key = opportunity.dedup_key
        if key in seen:
            continue
        seen.add(key)
        unique.append(opportunity)
    return unique


def fetch_all_opportunities(sources: list[OpportunitySourceProvider]) -> list[Opportunity]:
    """Fetch opportunities from multiple sources and deduplicate them."""
    opportunities: list[Opportunity] = []
    for source in sources:
        opportunities.extend(source.fetch())
    return dedupe_opportunities(opportunities)


class CareerPageFixtureSource:
    """Credential-free fixture for target-organization career pages."""

    source_name = "career_page"

    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> list[Opportunity]:
        data = _load_json_or_yaml(self.path)
        jobs = _jobs_from_data(data)
        normalized = []
        for item in jobs:
            item = {**item, "source": "career_page", "source_detail": "organization_watchlist"}
            normalized.append(opportunity_from_dict(item))
        return normalized


class LinkedInEmailFixtureSource:
    """Credential-free fixture for LinkedIn alert emails.

    The real legacy source queries Gmail as:
    `from:jobalerts-noreply@linkedin.com after:YYYY/MM/DD`.
    """

    source_name = "linkedin_email"

    def __init__(
        self,
        path: Path,
        *,
        sender: str = LINKEDIN_ALERT_SENDER,
        hours_back: int = 26,
        now: datetime | None = None,
    ):
        self.path = path
        self.sender = sender
        self.hours_back = hours_back
        self.now = now

    @property
    def gmail_query(self) -> str:
        now = self.now or datetime.now()
        after_date = (now - timedelta(hours=self.hours_back)).strftime("%Y/%m/%d")
        return f"from:{self.sender} after:{after_date}"

    def fetch(self) -> list[Opportunity]:
        data = _load_json_or_yaml(self.path)
        jobs = _jobs_from_data(data)
        normalized = []
        for item in jobs:
            item = {
                **item,
                "source": "linkedin_email",
                "source_detail": "gmail_alert",
                "gmail_query": self.gmail_query,
            }
            normalized.append(opportunity_from_dict(item))
        return normalized


class LinkedInSearchFixtureSource:
    """Credential-free fixture for Apify-backed LinkedIn keyword search."""

    source_name = "linkedin_search"

    ROTATION = {
        0: ["united_states"],
        1: ["united_kingdom", "uae"],
        2: ["netherlands", "canada"],
        3: ["singapore", "hong_kong"],
        4: ["africa"],
        5: [],
        6: [],
    }

    def __init__(
        self,
        jobs_path: Path,
        searches_path: Path,
        *,
        weekday: int | None = None,
    ):
        self.jobs_path = jobs_path
        self.searches_path = searches_path
        self.weekday = weekday

    def queries_for_today(self) -> list[LinkedInSearchQuery]:
        weekday = self.weekday if self.weekday is not None else datetime.now().weekday()
        return self.queries_for_regions(self.ROTATION.get(weekday, []))

    def all_queries(self) -> list[LinkedInSearchQuery]:
        config = _load_json_or_yaml(self.searches_path)
        return self.queries_for_regions(list(config.get("searches", {}).keys()))

    def queries_for_regions(self, regions: list[str]) -> list[LinkedInSearchQuery]:
        config = _load_json_or_yaml(self.searches_path)
        queries: list[LinkedInSearchQuery] = []
        for region_key, region_data in config.get("searches", {}).items():
            if region_key not in regions:
                continue
            location = region_data.get("location", "")
            for category in ("finance", "measurement", "fellowship"):
                for keyword in region_data.get(category, []):
                    queries.append(
                        LinkedInSearchQuery(
                            keyword=keyword,
                            location=location,
                            region=region_key,
                            category=category,
                        )
                    )
        return queries

    def fetch(self) -> list[Opportunity]:
        data = _load_json_or_yaml(self.jobs_path)
        jobs = _jobs_from_data(data)
        normalized = []
        for item in jobs:
            item = {**item, "source": "linkedin_search", "source_detail": "apify_keyword"}
            normalized.append(opportunity_from_dict(item))
        return normalized


def load_organizations(path: Path) -> list[Organization]:
    """Load watchlist organizations from a YAML fixture/config file."""
    data = _load_json_or_yaml(path)
    rows = data.get("organizations", data if isinstance(data, list) else [])
    return [
        Organization(
            name=row["name"],
            career_url=row["career_url"],
            location=row.get("location", ""),
            industry=row.get("industry", ""),
            priority=int(row.get("priority", 3)),
            tags=tuple(row.get("tags", [])),
        )
        for row in rows
        if row.get("name") and row.get("career_url")
    ]


def _load_json_or_yaml(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            return json.load(handle)
        return yaml.safe_load(handle)


def _jobs_from_data(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("jobs", [])
    return []


def _string_metadata(item: dict, *, exclude: set[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, value in item.items():
        if key in exclude or value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = str(value)
    return metadata
