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


def test_draft_application_command_uses_mock_provider():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["draft-application"])

    text = output.getvalue()
    assert exit_code == 0
    assert "Application packet draft" in text
    assert "Impact Investment Analyst @ Example Impact Fund" in text
    assert "resume: json" in text
    assert "cover_letter: json" in text
    assert "Mock resume draft" in text


def test_draft_application_command_can_show_json():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["draft-application", "--show-json"])

    text = output.getvalue()
    assert exit_code == 0
    assert "Generated documents" in text
    assert '"summary_text"' in text
    assert '"paragraphs"' in text


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


def test_scan_news_loads_env_file_for_live_news_settings(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("IMPACTALPHA_NEWSLETTER_SENDER=newsletter@example.com\n")

    class FakeSource:
        def __init__(self, config):
            assert config.sender == "newsletter@example.com"

        def fetch(self):
            return []

    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/token.json")
    monkeypatch.setattr("career_agent.cli.main.ImpactAlphaNewsletterSource", FakeSource)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-news",
                "--env-file",
                str(env_path),
                "--impactalpha-email-live",
            ]
        )

    assert exit_code == 0
    assert "impactalpha_email: 0" in output.getvalue()


def test_scan_news_cli_query_override_for_impactalpha(monkeypatch):
    captured = {}

    class FakeSource:
        def __init__(self, config):
            captured["query"] = config.gmail_query("2026/06/18")

        def fetch(self):
            return []

    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/token.json")
    monkeypatch.setattr("career_agent.cli.main.ImpactAlphaNewsletterSource", FakeSource)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-news",
                "--impactalpha-email-live",
                "--impactalpha-sender",
                "newsletter@example.com",
                "--impactalpha-query",
                "from:{sender} after:{after_date}",
            ]
        )

    assert exit_code == 0
    assert captured["query"] == "from:newsletter@example.com after:2026/06/18"


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
        health_results=[],
        show_details=False,
        limit=10,
    )

    assert "Private newsletter title" not in summary
    assert "Details hidden" in summary


def test_scan_news_health_check_uses_source_pack_health(monkeypatch):
    from career_agent.sources.news import SourceHealthResult

    captured = {}

    def fake_health(source_pack, *, user_agent):
        captured["user_agent"] = user_agent
        return [
            SourceHealthResult(
                name="ImpactAlpha",
                url="https://impactalpha.com/feed/",
                source_group="rss_feeds",
                ok=True,
                status_code=200,
                item_count=10,
            )
        ]

    monkeypatch.setenv("IMPACT_CAREER_USER_AGENT", "ImpactCareerAgent test@example.com")
    monkeypatch.setattr("career_agent.cli.main.check_source_pack_health", fake_health)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["scan-news", "--health-check"])

    text = output.getvalue()
    assert exit_code == 0
    assert "health_ok: 1" in text
    assert "Source health" in text
    assert "ImpactAlpha" in text
    assert captured["user_agent"] == "ImpactCareerAgent test@example.com"


def test_scan_news_scores_signals_with_mock_provider(monkeypatch):
    from career_agent.core import Signal

    monkeypatch.setattr(
        "career_agent.cli.main.parse_impactalpha_newsletter_eml",
        lambda raw: [
            Signal(
                source="ImpactAlpha",
                title=f"Fund closes vehicle {index}",
                signal_subtype="fund_close",
            )
            for index in range(7)
        ],
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-news",
                "--impactalpha-eml",
                "examples/sample_data/job_posting.md",
                "--score",
                "--max-signals",
                "6",
                "--show-details",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "top_signals: 5" in text
    assert "signals_selected: 6" in text
    assert "deduped_total: 5" in text
    assert text.count("Fund closes vehicle") == 5


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

        def send_digest(self, *, opportunities, source_summary, signals=None, subject=None):
            sent["to_email"] = self.config.to_email
            sent["count"] = len(opportunities)
            sent["signals"] = len(signals or [])
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
    assert sent == {
        "to_email": "user@example.com",
        "count": 3,
        "signals": 0,
        "subject": "Test Digest",
    }
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


def test_scan_jobs_can_include_scored_news_signals(monkeypatch):
    from career_agent.core import Signal

    monkeypatch.setattr(
        "career_agent.cli.main.RSSNewsSource",
        lambda config: SimpleNamespace(
            fetch=lambda: [
                Signal(
                    source="ImpactAlpha",
                    title=f"Capital signal {index}",
                    signal_subtype="fund_close",
                )
                for index in range(7)
            ]
        ),
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--include-news",
                "--news-rss-live",
                "--show-details",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "news_rss: 7" in text
    assert "top_signals: 5" in text
    assert "Top capital signals" in text
    assert text.count("Capital signal") == 5


def test_scan_jobs_send_email_includes_news_signals(monkeypatch):
    from career_agent.core import Signal

    sent = {}

    class FakeSender:
        def __init__(self, config):
            self.config = config

        def send_digest(self, *, opportunities, source_summary, signals=None, subject=None):
            sent["opportunities"] = len(opportunities)
            sent["signals"] = len(signals or [])
            sent["top_signals"] = source_summary.get("top_signals")
            return {"success": True, "message_id": "message-1"}

    monkeypatch.setenv("GMAIL_ADDRESS", "user@example.com")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/token.json")
    monkeypatch.setattr("career_agent.cli.main.GmailEmailSender", FakeSender)
    monkeypatch.setattr(
        "career_agent.cli.main.RSSNewsSource",
        lambda config: SimpleNamespace(
            fetch=lambda: [
                Signal(
                    source="ImpactAlpha",
                    title="Fund closes new vehicle",
                    signal_subtype="fund_close",
                )
            ]
        ),
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--include-news",
                "--news-rss-live",
                "--send-email",
            ]
        )

    assert exit_code == 0
    assert sent == {"opportunities": 3, "signals": 1, "top_signals": 1}


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
