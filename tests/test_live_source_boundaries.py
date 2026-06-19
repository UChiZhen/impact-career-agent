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
from career_agent.sources.linkedin_search import (
    build_linkedin_search_url,
    call_apify_actor,
    default_dataset_id_from_run,
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


def test_linkedin_search_source_config_reads_apify_env(monkeypatch):
    query = LinkedInSearchQuery(
        keyword="impact investing analyst",
        location="United States",
        region="united_states",
        category="finance",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "local-token")
    monkeypatch.setenv("APIFY_MAX_RESULTS_PER_QUERY", "7")
    monkeypatch.setenv("APIFY_ACTOR_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("APIFY_MAX_TOTAL_JOBS", "50")
    monkeypatch.setenv("APIFY_INTER_QUERY_DELAY_SECONDS", "0")

    config = LinkedInSearchSourceConfig.from_env(queries=(query,))

    assert config.api_token == "local-token"
    assert config.max_results_per_query == 7
    assert config.actor_timeout_seconds == 25
    assert config.max_total_jobs == 50
    assert config.inter_query_delay_seconds == 0


def test_build_linkedin_search_url_matches_legacy_shape():
    url = build_linkedin_search_url("impact investing analyst", "United States")

    assert url == (
        "https://www.linkedin.com/jobs/search/"
        "?keywords=impact%20investing%20analyst"
        "&location=United%20States"
        "&f_TPR=r86400"
    )


def test_linkedin_search_source_fetches_from_apify_client_boundary():
    queries = (
        LinkedInSearchQuery(
            keyword="impact investing analyst",
            location="United States",
            region="united_states",
            category="finance",
        ),
        LinkedInSearchQuery(
            keyword="climate finance analyst",
            location="United States",
            region="united_states",
            category="finance",
        ),
    )
    client = FakeApifyClient(
        datasets={
            "dataset-1": [
                {
                    "jobUrl": "https://www.linkedin.com/jobs/view/123456/?trackingId=abc",
                    "title": "Impact Investment Analyst",
                    "companyName": "Example Capital",
                    "location": "Chicago, IL",
                    "postedAt": "2026-06-17",
                    "description": "Impact investing role",
                },
                {
                    "jobUrl": "https://www.linkedin.com/jobs/view/123456/?trackingId=duplicate",
                    "title": "Impact Investment Analyst",
                    "companyName": "Example Capital",
                    "location": "Chicago, IL",
                },
            ],
            "dataset-2": [
                {
                    "link": "https://www.linkedin.com/jobs/view/987654/?trk=public_jobs",
                    "jobTitle": "Climate Finance Analyst",
                    "company": "Example Green Bank",
                    "jobLocation": "New York, NY",
                    "applicantsCount": "12",
                }
            ],
        }
    )
    source = LinkedInSearchSource(
        LinkedInSearchSourceConfig(
            queries=queries,
            max_results_per_query=10,
            inter_query_delay_seconds=0,
        )
    )

    opportunities = source.fetch_from_client(client)

    assert len(opportunities) == 2
    assert client.actor_calls[0]["actor_id"] == "curious_coder~linkedin-jobs-scraper"
    assert client.actor_calls[0]["timeout_secs"] == 30
    assert client.actor_calls[0]["run_input"]["maxItems"] == 10
    assert client.actor_calls[0]["run_input"]["scrapeJobDetails"] is False
    assert opportunities[0].source == "linkedin_search"
    assert opportunities[0].source_detail == "apify_keyword"
    assert opportunities[0].company == "Example Capital"
    assert opportunities[0].job_url == "https://www.linkedin.com/jobs/view/123456/"
    assert opportunities[0].search_keyword == "impact investing analyst"
    assert opportunities[0].search_region == "united_states"
    assert opportunities[1].company == "Example Green Bank"


def test_call_apify_actor_supports_new_run_timeout_signature():
    actor = FakeApifyActorV3()

    run = call_apify_actor(actor, run_input={"hello": "world"}, timeout_seconds=30)

    assert default_dataset_id_from_run(run) == "dataset-v3"
    assert actor.run_input == {"hello": "world"}
    assert actor.run_timeout.total_seconds() == 30
    assert actor.logger is None


def test_default_dataset_id_from_run_supports_legacy_dict():
    assert default_dataset_id_from_run({"defaultDatasetId": "dataset-legacy"}) == "dataset-legacy"


@pytest.mark.parametrize(
    "source",
    [
        CareerPageSource(CareerPageSourceConfig(organizations=())),
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


class FakeApifyActor:
    def __init__(self, client, actor_id):
        self.client = client
        self.actor_id = actor_id

    def call(self, *, run_input, timeout_secs):
        dataset_id = f"dataset-{len(self.client.actor_calls) + 1}"
        self.client.actor_calls.append(
            {
                "actor_id": self.actor_id,
                "run_input": run_input,
                "timeout_secs": timeout_secs,
                "dataset_id": dataset_id,
            }
        )
        return {"defaultDatasetId": dataset_id}


class FakeApifyDataset:
    def __init__(self, items):
        self.items = items

    def iterate_items(self):
        return iter(self.items)


class FakeApifyClient:
    def __init__(self, *, datasets):
        self.datasets = datasets
        self.actor_calls = []

    def actor(self, actor_id):
        return FakeApifyActor(self, actor_id)

    def dataset(self, dataset_id):
        return FakeApifyDataset(self.datasets[dataset_id])


class FakeApifyActorV3:
    def __init__(self):
        self.run_input = None
        self.run_timeout = None
        self.logger = "default"

    def call(self, *, run_input, run_timeout, logger="default"):
        self.run_input = run_input
        self.run_timeout = run_timeout
        self.logger = logger
        return FakeRun(default_dataset_id="dataset-v3")


class FakeRun:
    def __init__(self, *, default_dataset_id):
        self.default_dataset_id = default_dataset_id
