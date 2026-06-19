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
from career_agent.sources.career_extraction import extract_opportunities_from_snapshot
from career_agent.sources.career_pages import CareerPageSnapshot, CareerPageSource, CareerPageSourceConfig
from career_agent.sources.linkedin_email import LinkedInEmailSource, LinkedInEmailSourceConfig
from career_agent.sources.linkedin_search import LinkedInSearchSource, LinkedInSearchSourceConfig
from career_agent.sources.watchlist import (
    GoogleSheetsOrganizationSource,
    GoogleSheetsWatchlistConfig,
    organizations_from_sheet_values,
)

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
    "CareerPageSnapshot",
    "CareerPageSourceConfig",
    "extract_opportunities_from_snapshot",
    "LinkedInEmailSource",
    "LinkedInEmailSourceConfig",
    "LinkedInSearchSource",
    "LinkedInSearchSourceConfig",
    "GoogleSheetsOrganizationSource",
    "GoogleSheetsWatchlistConfig",
    "organizations_from_sheet_values",
]
