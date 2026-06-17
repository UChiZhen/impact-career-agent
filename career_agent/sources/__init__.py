"""Input source connectors."""

from career_agent.sources.opportunities import (
    LINKEDIN_ALERT_SENDER,
    CareerPageFixtureSource,
    LinkedInEmailFixtureSource,
    LinkedInSearchFixtureSource,
    LinkedInSearchQuery,
    LINKEDIN_SEARCH_ROTATION,
    OpportunitySourceProvider,
    Organization,
    dedupe_opportunities,
    fetch_all_opportunities,
    load_linkedin_search_queries,
    load_organizations,
    normalize_legacy_source,
    opportunity_from_dict,
)
from career_agent.sources.career_pages import CareerPageSource, CareerPageSourceConfig
from career_agent.sources.linkedin_email import LinkedInEmailSource, LinkedInEmailSourceConfig
from career_agent.sources.linkedin_search import LinkedInSearchSource, LinkedInSearchSourceConfig

__all__ = [
    "LINKEDIN_ALERT_SENDER",
    "CareerPageFixtureSource",
    "LinkedInEmailFixtureSource",
    "LinkedInSearchFixtureSource",
    "LinkedInSearchQuery",
    "LINKEDIN_SEARCH_ROTATION",
    "OpportunitySourceProvider",
    "Organization",
    "dedupe_opportunities",
    "fetch_all_opportunities",
    "load_linkedin_search_queries",
    "load_organizations",
    "normalize_legacy_source",
    "opportunity_from_dict",
    "CareerPageSource",
    "CareerPageSourceConfig",
    "LinkedInEmailSource",
    "LinkedInEmailSourceConfig",
    "LinkedInSearchSource",
    "LinkedInSearchSourceConfig",
]
