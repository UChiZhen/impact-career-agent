"""Extract structured opportunities from career-page snapshots."""

from __future__ import annotations

import json
from typing import Any

from career_agent.core import Opportunity
from career_agent.llm import LLMProvider, LLMProviderError
from career_agent.sources.career_pages import CareerPageSnapshot


CAREER_PAGE_EXTRACTION_SYSTEM_PROMPT = """You extract job postings from organization career pages.

Return valid JSON only. Be conservative: include only roles visible in the
provided page text. Do not invent jobs, locations, or URLs.
"""


def build_career_page_extraction_prompt(snapshot: CareerPageSnapshot) -> str:
    """Build a provider-agnostic extraction prompt for one career page snapshot."""
    organization = snapshot.organization
    payload = {
        "organization": {
            "name": organization.name,
            "career_url": organization.career_url,
            "location": organization.location,
            "industry": organization.industry,
            "tags": list(organization.tags),
        },
        "page": {
            "url": snapshot.url,
            "content_hash": snapshot.content_hash,
            "text": snapshot.raw_text,
        },
    }

    return f"""Extract job postings from this career page.

Input:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return this JSON shape:
{{
  "jobs": [
    {{
      "job_title": "exact visible role title",
      "company": "organization name",
      "location": "visible location or organization default location",
      "job_url": "direct job URL if visible, otherwise career page URL",
      "post_date": "visible posting date or null",
      "description": "short visible summary, no more than 500 characters"
    }}
  ],
  "page_summary": "one sentence summary of the page"
}}
"""


def extract_opportunities_from_snapshot(
    snapshot: CareerPageSnapshot,
    provider: LLMProvider,
) -> list[Opportunity]:
    """Extract opportunities from one fetched career-page snapshot."""
    if not snapshot.success or not snapshot.raw_text:
        return []

    response = provider.generate(
        build_career_page_extraction_prompt(snapshot),
        system=CAREER_PAGE_EXTRACTION_SYSTEM_PROMPT,
    )
    payload = response.json_object()
    return opportunities_from_extraction_payload(snapshot, payload)


def opportunities_from_extraction_payload(
    snapshot: CareerPageSnapshot,
    payload: dict[str, Any],
) -> list[Opportunity]:
    """Normalize an extraction JSON object into `Opportunity` records."""
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        raise LLMProviderError("Career-page extraction payload must contain a jobs array")

    opportunities = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        opportunity = opportunity_from_extracted_job(snapshot, item)
        if opportunity:
            opportunities.append(opportunity)
    return opportunities


def opportunity_from_extracted_job(
    snapshot: CareerPageSnapshot,
    item: dict[str, Any],
) -> Opportunity | None:
    """Normalize one extracted job object."""
    title = clean_string(item.get("job_title") or item.get("title"))
    if not title:
        return None

    organization = snapshot.organization
    company = clean_string(item.get("company")) or organization.name
    location = clean_string(item.get("location")) or organization.location
    job_url = clean_string(item.get("job_url") or item.get("url")) or snapshot.url
    post_date = clean_string(item.get("post_date") or item.get("posted_date")) or None
    description = clean_string(item.get("description") or item.get("summary"))

    return Opportunity(
        source="career_page",
        source_detail="organization_watchlist",
        job_title=title,
        company=company,
        location=location,
        job_url=job_url,
        origin_url=organization.career_url,
        description=description[:500],
        post_date=post_date,
        metadata={
            "organization_industry": organization.industry,
            "career_page_hash": snapshot.content_hash,
            "career_page_fetched_at": snapshot.fetched_at,
        },
    )


def clean_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(clean_string(item) for item in value if clean_string(item))
    return str(value).strip()
