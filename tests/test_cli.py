from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from career_agent import __version__
from career_agent.cli.main import (
    format_job_scan_summary,
    format_news_scan_summary,
    linkedin_email_config_from_args,
    linkedin_search_config_from_args,
    load_env_file,
    main,
    mock_score_response,
)
from career_agent.core import Opportunity


def test_version_command():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["version"])

    assert exit_code == 0
    assert __version__ in output.getvalue()


def test_demo_command():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["demo"])

    text = output.getvalue()
    assert exit_code == 0
    assert "Impact Career Agent demo digest" in text
    assert "not an external LLM" in text


def test_scan_linkedin_email_command_uses_safe_summary(monkeypatch):
    def fake_scan(args):
        assert args.live is True
        assert args.limit == 3
        return "LinkedIn email scan\nMessages: 1\nOpportunities: 2"

    monkeypatch.setattr("career_agent.cli.main.run_linkedin_email_scan", fake_scan)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["scan-linkedin-email", "--live", "--limit", "3"])

    assert exit_code == 0
    assert "LinkedIn email scan" in output.getvalue()
    assert "Opportunities: 2" in output.getvalue()


def test_linkedin_email_config_from_args_prefers_cli_over_env(monkeypatch):
    monkeypatch.setenv("LINKEDIN_ALERT_HOURS_BACK", "26")
    monkeypatch.setenv("LINKEDIN_ALERT_MAX_RESULTS", "20")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/old/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/old/token.json")

    config = linkedin_email_config_from_args(
        SimpleNamespace(
            hours_back=12,
            max_results=5,
            credentials_path="~/new/credentials.json",
            token_path="~/new/token.json",
        )
    )

    assert config.hours_back == 12
    assert config.max_results == 5
    assert config.credentials_path == "~/new/credentials.json"
    assert config.token_path == "~/new/token.json"


def test_scan_linkedin_search_dry_run_uses_weekday_rotation():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-linkedin-search",
                "--searches",
                "examples/sample_data/linkedin_searches.yaml",
                "--weekday",
                "0",
                "--limit",
                "2",
                "--query-limit",
                "3",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "Mode: dry-run" in text
    assert "Queries: 3" in text
    assert "impact investing analyst" in text
    assert "https://www.linkedin.com/jobs/search/" in text
    assert "more queries" in text


def test_scan_linkedin_search_command_uses_safe_live_summary(monkeypatch):
    def fake_scan(args):
        assert args.live is True
        assert args.region == ["united_states"]
        assert args.query_limit == 1
        return "LinkedIn search scan\nMode: live\nOpportunities: 1"

    monkeypatch.setattr("career_agent.cli.main.run_linkedin_search_scan", fake_scan)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-linkedin-search",
                "--live",
                "--region",
                "united_states",
                "--query-limit",
                "1",
            ]
        )

    assert exit_code == 0
    assert "Mode: live" in output.getvalue()


def test_load_env_file_keeps_existing_env_value(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("APIFY_API_TOKEN=file-token\nAPIFY_MAX_RESULTS_PER_QUERY=9\n")
    monkeypatch.setenv("APIFY_API_TOKEN", "existing-token")

    load_env_file(env_path)

    import os

    assert os.environ["APIFY_API_TOKEN"] == "existing-token"
    assert os.environ["APIFY_MAX_RESULTS_PER_QUERY"] == "9"


def test_linkedin_search_config_from_args_prefers_cli_max_results(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "local-token")
    monkeypatch.setenv("APIFY_MAX_RESULTS_PER_QUERY", "10")
    args = SimpleNamespace(max_results_per_query=3)
    query = SimpleNamespace(
        keyword="impact investing analyst",
        location="United States",
        region="united_states",
        category="finance",
    )

    config = linkedin_search_config_from_args(args, [query])

    assert config.api_token == "local-token"
    assert config.max_results_per_query == 3


def test_scan_jobs_default_uses_fixture_sources():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["scan-jobs", "--config", "examples/demo_config.yaml"])

    text = output.getvalue()
    assert exit_code == 0
    assert "Job scan summary" in text
    assert "career_page: 1" in text
    assert "linkedin_email: 1" in text
    assert "linkedin_search: 1" in text
    assert "deduped_total: 3" in text
    assert "Details hidden" in text


def test_scan_news_default_is_safe_source_pack_dry_run():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["scan-news"])

    text = output.getvalue()
    assert exit_code == 0
    assert "News signal scan" in text
    assert "Source pack: impact_capital_signals" in text
    assert "No live sources selected" in text


def test_format_news_scan_summary_hides_titles_by_default():
    from career_agent.core import Signal

    signal = Signal(
        source="ImpactAlpha",
        title="Private newsletter title",
        signal_subtype="fund_close",
        suggested_action="rescan_org_jobs",
    )

    summary = format_news_scan_summary(
        source_pack_name="demo",
        source_summary={"impactalpha_eml": 1, "deduped_total": 1},
        signals=[signal],
        show_details=False,
        limit=10,
    )

    assert "Private newsletter title" not in summary
    assert "Details hidden" in summary


def test_scan_jobs_can_score_with_mock_provider():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--score",
                "--show-details",
                "--limit",
                "2",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "score_apply_now:" in text
    assert "score_skip:" in text
    assert "| apply_now" in text or "| skip" in text


def test_scan_jobs_live_command_uses_safe_summary(monkeypatch):
    monkeypatch.setattr(
        "career_agent.cli.main.fetch_linkedin_email_opportunities_for_job_scan",
        lambda args: [
            Opportunity(
                source="linkedin_email",
                company="Example Capital",
                job_title="Analyst",
                location="Chicago",
            )
        ],
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["scan-jobs", "--linkedin-email-live", "--show-details"])

    text = output.getvalue()
    assert exit_code == 0
    assert "linkedin_email: 1" in text
    assert "deduped_total: 1" in text
    assert "Example Capital | Analyst | Chicago" in text


def test_scan_jobs_send_email_uses_sender(monkeypatch):
    sent = {}

    class FakeSender:
        def __init__(self, config):
            self.config = config

        def send_digest(self, *, opportunities, source_summary, subject=None):
            sent["to_email"] = self.config.to_email
            sent["count"] = len(opportunities)
            sent["subject"] = subject
            return {"success": True, "message_id": "message-1"}

    monkeypatch.setenv("GMAIL_ADDRESS", "user@example.com")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/token.json")
    monkeypatch.setattr("career_agent.cli.main.GmailEmailSender", FakeSender)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--send-email",
                "--email-subject",
                "Test Digest",
            ]
        )

    assert exit_code == 0
    assert sent == {"to_email": "user@example.com", "count": 3, "subject": "Test Digest"}
    assert "Email sent: yes (message-1)" in output.getvalue()


def test_format_job_scan_summary_hides_details_by_default():
    opportunity = Opportunity(
        source="career_page",
        company="Private Org",
        job_title="Analyst",
        location="Remote",
    )

    summary = format_job_scan_summary(
        source_summary={"career_page": 1, "deduped_total": 1},
        opportunities=[opportunity],
        show_details=False,
        limit=10,
    )

    assert "Private Org" not in summary
    assert "Details hidden" in summary


def test_mock_score_response_matches_opportunity_count():
    opportunities = [
        Opportunity(
            source="career_page",
            company="Example Impact Fund",
            job_title="Impact Analyst",
            location="Chicago",
        ),
        Opportunity(
            source="linkedin_search",
            company="Example Bank",
            job_title="Operations Analyst",
            location="New York",
        ),
    ]

    payload = mock_score_response(opportunities)

    assert payload.count("recommended_action") == 2
