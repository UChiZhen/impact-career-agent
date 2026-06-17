"""Input source connectors."""

from career_agent.sources.opportunities import (
    LINKEDIN_ALERT_SENDER,
    CareerPageFixtureSource,
    LinkedInEmailFixtureSource,
    LinkedInSearchFixtureSource,
    LinkedInSearchQuery,
    OpportunitySourceProvider,
    Organization,
    dedupe_opportunities,
    fetch_all_opportunities,
    load_organizations,
    normalize_legacy_source,
    opportunity_from_dict,
)

__all__ = [
    "LINKEDIN_ALERT_SENDER",
    "CareerPageFixtureSource",
    "LinkedInEmailFixtureSource",
    "LinkedInSearchFixtureSource",
    "LinkedInSearchQuery",
    "OpportunitySourceProvider",
    "Organization",
    "dedupe_opportunities",
    "fetch_all_opportunities",
    "load_organizations",
    "normalize_legacy_source",
    "opportunity_from_dict",
]
