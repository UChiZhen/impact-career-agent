from datetime import datetime
from pathlib import Path

from career_agent.sources import (
    LINKEDIN_ALERT_SENDER,
    CareerPageFixtureSource,
    LinkedInEmailFixtureSource,
    LinkedInSearchFixtureSource,
    dedupe_opportunities,
    fetch_all_opportunities,
    load_linkedin_search_queries,
    load_organizations,
    normalize_legacy_source,
    opportunity_from_dict,
)


def test_normalize_legacy_source_values():
    assert normalize_legacy_source("apify_search") == "linkedin_search"
    assert normalize_legacy_source("career_site") == "career_page"
    assert normalize_legacy_source("linkedin_email") == "linkedin_email"


def test_opportunity_from_legacy_apify_dict_preserves_search_metadata():
    opportunity = opportunity_from_dict(
        {
            "source": "apify_search",
            "job_title": "Climate Finance Analyst",
            "company": "Example Green Bank",
            "location": "New York, NY",
            "job_url": "https://www.linkedin.com/jobs/view/789012",
            "description_snippet": "Analyze climate finance portfolios.",
            "search_keyword": "climate finance analyst",
            "search_location": "United States",
            "search_region": "united_states",
            "search_category": "finance",
        }
    )

    assert opportunity.source == "linkedin_search"
    assert opportunity.search_keyword == "climate finance analyst"
    assert opportunity.description == "Analyze climate finance portfolios."


def test_load_organizations_fixture():
    orgs = load_organizations(Path("examples/sample_data/organizations.yaml"))

    assert len(orgs) == 2
    assert orgs[0].name == "Example Impact Fund"
    assert orgs[0].career_url == "https://example.org/careers"


def test_linkedin_email_fixture_uses_real_sender_query():
    source = LinkedInEmailFixtureSource(
        Path("examples/sample_data/linkedin_email_jobs.json"),
        now=datetime(2026, 6, 17, 7, 0, 0),
    )

    opportunities = source.fetch()

    assert source.sender == LINKEDIN_ALERT_SENDER
    assert source.gmail_query == "from:jobalerts-noreply@linkedin.com after:2026/06/16"
    assert opportunities[0].source == "linkedin_email"
    assert opportunities[0].source_detail == "gmail_alert"
    assert opportunities[0].metadata["gmail_query"] == source.gmail_query


def test_linkedin_search_fixture_queries_match_rotation_shape():
    source = LinkedInSearchFixtureSource(
        Path("examples/sample_data/linkedin_search_jobs.json"),
        Path("examples/sample_data/linkedin_searches.yaml"),
        weekday=0,
    )

    queries = source.queries_for_today()
    opportunities = source.fetch()

    assert [query.keyword for query in queries] == [
        "impact investing analyst",
        "climate finance analyst",
        "impact analyst SQL",
        "impact fellowship analyst",
    ]
    assert opportunities[0].source == "linkedin_search"
    assert opportunities[0].source_detail == "apify_keyword"


def test_load_linkedin_search_queries_supports_regions_and_all_regions():
    path = Path("examples/sample_data/linkedin_searches.yaml")

    region_queries = load_linkedin_search_queries(path, regions=["united_states"])
    all_queries = load_linkedin_search_queries(path, all_regions=True)

    assert len(region_queries) == 4
    assert {query.region for query in region_queries} == {"united_states"}
    assert len(all_queries) > len(region_queries)


def test_fetch_all_opportunities_dedupes_across_sources():
    career = CareerPageFixtureSource(Path("examples/sample_data/career_page_jobs.json"))
    email = LinkedInEmailFixtureSource(Path("examples/sample_data/linkedin_email_jobs.json"))
    search = LinkedInSearchFixtureSource(
        Path("examples/sample_data/linkedin_search_jobs.json"),
        Path("examples/sample_data/linkedin_searches.yaml"),
    )

    opportunities = fetch_all_opportunities([career, email, search])
    duplicated = dedupe_opportunities(opportunities + [opportunities[0]])

    assert len(opportunities) == 3
    assert len(duplicated) == 3
