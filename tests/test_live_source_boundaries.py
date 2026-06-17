import base64
from datetime import datetime

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


def test_linkedin_email_source_config_reads_migration_env(monkeypatch):
    monkeypatch.setenv("LINKEDIN_ALERT_HOURS_BACK", "12")
    monkeypatch.setenv("LINKEDIN_ALERT_MAX_RESULTS", "7")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/jobsearch/job-radar/config/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/jobsearch/job-radar/config/token.json")

    config = LinkedInEmailSourceConfig.from_env()

    assert config.sender == LINKEDIN_ALERT_SENDER
    assert config.hours_back == 12
    assert config.max_results == 7
    assert config.credentials_path == "~/jobsearch/job-radar/config/credentials.json"
    assert config.token_path == "~/jobsearch/job-radar/config/token.json"


def test_linkedin_email_source_fetches_from_gmail_service_boundary():
    body = """
    Analyst
    Example Capital
    London
    View job: https://www.linkedin.com/comm/jobs/view/123456/?trackingId=abc
    """
    encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8").rstrip("=")
    message = {
        "id": "message-1",
        "threadId": "thread-1",
        "payload": {
            "headers": [
                {
                    "name": "Subject",
                    "value": "“( impact investing )”: Example Capital - Analyst posted on 6/10/26",
                },
                {"name": "Date", "value": "Wed, 10 Jun 2026 06:00:00 -0500"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded_body},
                }
            ],
        },
    }
    service = FakeGmailService(messages={"message-1": message})
    source = LinkedInEmailSource(LinkedInEmailSourceConfig(hours_back=26, max_results=10))

    opportunities = source.fetch_from_service(
        service,
        now=datetime(2026, 6, 17, 12, 0, 0),
    )

    assert service.list_query == "from:jobalerts-noreply@linkedin.com after:2026/06/16"
    assert len(opportunities) == 1
    assert opportunities[0].source == "linkedin_email"
    assert opportunities[0].company == "Example Capital"
    assert opportunities[0].metadata["gmail_message_id"] == "message-1"
    assert opportunities[0].metadata["gmail_thread_id"] == "thread-1"
    assert opportunities[0].metadata["gmail_query"] == service.list_query


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
        LinkedInSearchSource(LinkedInSearchSourceConfig(queries=())),
    ],
)
def test_remaining_live_sources_are_explicitly_not_implemented_yet(source):
    with pytest.raises(NotImplementedError):
        source.fetch()


class FakeExecutable:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeMessagesResource:
    def __init__(self, service):
        self.service = service

    def list(self, *, userId, q, maxResults):
        self.service.list_user_id = userId
        self.service.list_query = q
        self.service.list_max_results = maxResults
        return FakeExecutable({"messages": [{"id": message_id} for message_id in self.service.messages]})

    def get(self, *, userId, id, format):
        self.service.get_calls.append({"userId": userId, "id": id, "format": format})
        return FakeExecutable(self.service.messages[id])


class FakeUsersResource:
    def __init__(self, service):
        self.service = service

    def messages(self):
        return FakeMessagesResource(self.service)


class FakeGmailService:
    def __init__(self, *, messages):
        self.messages = messages
        self.list_user_id = None
        self.list_query = None
        self.list_max_results = None
        self.get_calls = []

    def users(self):
        return FakeUsersResource(self)
