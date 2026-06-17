import pytest

from career_agent.sources import (
    LINKEDIN_ALERT_SENDER,
    CareerPageSource,
    CareerPageSourceConfig,
    LinkedInEmailSource,
    LinkedInEmailSourceConfig,
    LinkedInSearchQuery,
    LinkedInSearchSource,
    LinkedInSearchSourceConfig,
    Organization,
)


def test_career_page_source_config_uses_watchlist_schema():
    org = Organization(
        name="Example Impact Fund",
        career_url="https://example.org/careers",
        location="United States",
        industry="impact investing",
        priority=1,
        tags=("impact fund",),
    )
    config = CareerPageSourceConfig(organizations=(org,))

    assert config.organizations[0].name == "Example Impact Fund"
    assert config.use_content_cache is True


def test_linkedin_email_source_config_uses_real_sender_default():
    config = LinkedInEmailSourceConfig()

    assert config.sender == LINKEDIN_ALERT_SENDER
    assert config.gmail_query("2026/06/16") == (
        "from:jobalerts-noreply@linkedin.com after:2026/06/16"
    )


def test_linkedin_search_source_config_matches_apify_shape():
    query = LinkedInSearchQuery(
        keyword="impact investing analyst",
        location="United States",
        region="united_states",
        category="finance",
    )
    config = LinkedInSearchSourceConfig(queries=(query,))

    assert config.actor_id == "curious_coder~linkedin-jobs-scraper"
    assert config.max_results_per_query == 10
    assert config.queries[0].keyword == "impact investing analyst"


@pytest.mark.parametrize(
    "source",
    [
        CareerPageSource(CareerPageSourceConfig(organizations=())),
        LinkedInEmailSource(LinkedInEmailSourceConfig()),
        LinkedInSearchSource(LinkedInSearchSourceConfig(queries=())),
    ],
)
def test_live_sources_are_explicitly_not_implemented_yet(source):
    with pytest.raises(NotImplementedError):
        source.fetch()
