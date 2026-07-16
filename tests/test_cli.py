from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from career_agent import __version__
from career_agent.cli.main import (
    draft_application_packets_for_scan,
    format_job_scan_summary,
    format_news_scan_summary,
    linkedin_email_config_from_args,
    linkedin_search_config_from_args,
    load_env_file,
    main,
    mock_score_response,
)
from career_agent.core import ApplicationPacket, FitScore, Opportunity
from career_agent.sinks.google_sheets import TrackerPacketState
from career_agent.sources.job_descriptions import (
    JobDescriptionEnrichmentResult,
    JobDescriptionQuality,
)


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


def test_scan_linkedin_search_live_hides_opportunity_details_by_default(monkeypatch):
    private_opportunity = Opportunity(
        source="linkedin_search",
        company="Private Employer",
        job_title="Private Role",
        location="Private Location",
    )

    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "career_agent.cli.main.LinkedInSearchSource",
        lambda config: SimpleNamespace(fetch=lambda: [private_opportunity]),
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-linkedin-search",
                "--live",
                "--weekday",
                "0",
                "--query-limit",
                "1",
                "--max-results-per-query",
                "1",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "Opportunities: 1" in text
    assert "Details hidden" in text
    assert "Private Employer" not in text
    assert "Private Role" not in text
    assert "Private Location" not in text


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


def test_scan_news_reports_selected_scoring_provider(monkeypatch):
    from career_agent.core import Signal
    from career_agent.sources.news import RSSFetchResult, SourceHealthResult

    monkeypatch.setattr(
        "career_agent.cli.main.RSSNewsSource",
        lambda config: SimpleNamespace(
            fetch_with_health=lambda: RSSFetchResult(
                signals=(Signal(source="Public Feed", title="Fund closes new vehicle"),),
                health_results=(
                    SourceHealthResult(
                        name="Public Feed",
                        url="https://example.org/feed",
                        source_group="rss_feeds",
                        ok=True,
                    ),
                ),
            )
        ),
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-news",
                "--rss-live",
                "--score",
                "--score-provider",
                "mock",
                "--max-signals",
                "1",
                "--top-signals",
                "1",
            ]
        )

    assert exit_code == 0
    assert "signal_scoring_provider_mock: 1" in output.getvalue()


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

        def send_digest(
            self,
            *,
            opportunities,
            source_summary,
            signals=None,
            include_unscored=False,
            subject=None,
        ):
            sent["to_email"] = self.config.to_email
            sent["count"] = len(opportunities)
            sent["scored_count"] = sum(1 for opportunity in opportunities if opportunity.fit)
            sent["signals"] = len(signals or [])
            sent["include_unscored"] = include_unscored
            sent["fallback_count"] = source_summary.get("scoring_source_fallback")
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
        "scored_count": 3,
        "signals": 0,
        "include_unscored": False,
        "fallback_count": 3,
        "subject": "Test Digest",
    }
    assert "scoring_source_fallback: 3" in output.getvalue()
    assert "Email sent: yes (message-1)" in output.getvalue()


def test_scan_jobs_can_draft_top_application_packet_preview():
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--draft-applications",
                "1",
                "--show-details",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "application_packets_requested: 1" in text
    assert "application_packets_selected: 1" in text
    assert "Application packets" in text
    assert "Example Impact Fund | Impact Investment Analyst" in text
    assert "packet:" in text
    assert "scoring_source_llm: 1" in text
    assert "scoring_source_fallback: 2" in text


def test_scan_jobs_does_not_draft_when_full_jd_is_unavailable(monkeypatch):
    def incomplete_enrichment(opportunity):
        return JobDescriptionEnrichmentResult(
            opportunity=opportunity,
            status="needs_jd",
            quality=JobDescriptionQuality(
                accepted=False,
                char_count=120,
                word_count=20,
                reasons=("description_too_short",),
            ),
            error="blocked",
        )

    monkeypatch.setattr("career_agent.cli.main.enrich_job_description", incomplete_enrichment)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--draft-applications",
                "1",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "application_jd_attempted: 1" in text
    assert "application_needs_jd: 1" in text
    assert "application_packets_selected: 0" in text
    assert "Application packets" not in text


def test_scan_jobs_rescores_full_jd_before_drafting(monkeypatch):
    def complete_enrichment(opportunity):
        return JobDescriptionEnrichmentResult(
            opportunity=opportunity,
            status="existing",
            source="source_description",
            quality=JobDescriptionQuality(
                accepted=True,
                char_count=len(opportunity.description),
                word_count=150,
            ),
        )

    def review_after_full_jd(opportunities, candidate, provider, *, description_limit=1200):
        assert description_limit == 6000
        return [
            opportunity.model_copy(
                update={
                    "fit": FitScore(
                        total=72,
                        recommended_action="review",
                        match_summary="Full JD reveals a weaker fit.",
                    )
                }
            )
            for opportunity in opportunities
        ]

    monkeypatch.setattr("career_agent.cli.main.enrich_job_description", complete_enrichment)
    monkeypatch.setattr(
        "career_agent.cli.main.score_opportunities_with_fallback",
        review_after_full_jd,
    )

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--draft-applications",
                "1",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert "application_jd_ready: 1" in text
    assert "application_not_apply_after_jd: 1" in text
    assert "application_packets_selected: 0" in text


def test_application_batch_tries_next_candidate_after_missing_jd(monkeypatch):
    first = Opportunity(
        source="linkedin_email",
        company="Missing JD Org",
        job_title="Impact Analyst",
        job_url="https://www.linkedin.com/jobs/view/111111",
        fit=FitScore(total=92, recommended_action="apply_now"),
    )
    second = Opportunity(
        source="linkedin_search",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        job_url="https://www.linkedin.com/jobs/view/222222",
        description="Impact finance responsibilities and qualifications. " * 30,
        fit=FitScore(total=88, recommended_action="apply_now"),
    )

    def staged_enrichment(opportunity):
        if opportunity.company == "Missing JD Org":
            return JobDescriptionEnrichmentResult(
                opportunity=opportunity,
                status="needs_jd",
                quality=JobDescriptionQuality(False, 0, 0, ("missing_description",)),
            )
        return JobDescriptionEnrichmentResult(
            opportunity=opportunity,
            status="existing",
            source="source_description",
            quality=JobDescriptionQuality(True, len(opportunity.description), 150),
        )

    monkeypatch.setattr("career_agent.cli.main.enrich_job_description", staged_enrichment)
    args = SimpleNamespace(
        candidate_profile="examples/sample_data/candidate_profile.yaml",
        master_resume="examples/sample_data/master_resume.yaml",
        draft_applications=1,
        max_jd_enrichment_attempts=2,
        score_provider="mock",
        application_provider="mock",
        application_output="preview",
        application_output_dir="application_packets",
        render_pdf=False,
        debug_output=False,
    )

    batch = draft_application_packets_for_scan(args, [first, second])

    assert len(batch.results) == 1
    assert batch.summary["application_jd_attempted"] == 2
    assert batch.summary["application_needs_jd"] == 1
    assert batch.summary["application_jd_ready"] == 1
    assert batch.opportunities[0].metadata["application_status"] == "needs_jd"
    assert batch.opportunities[1].metadata["application_status"] == "preview_ready"


def test_application_batch_skips_existing_packet_and_tries_next_candidate(monkeypatch):
    first = Opportunity(
        source="linkedin_search",
        company="Already Generated Fund",
        job_title="Impact Analyst",
        job_url="https://example.org/jobs/existing",
        description="Responsibilities and qualifications for impact investing. " * 30,
        metadata={"jd_content_hash": "jd-existing"},
        fit=FitScore(total=92, recommended_action="apply_now"),
    )
    second = Opportunity(
        source="linkedin_search",
        company="New Opportunity Fund",
        job_title="Investment Analyst",
        job_url="https://example.org/jobs/new",
        description="Responsibilities and qualifications for mission investing. " * 30,
        metadata={"jd_content_hash": "jd-new"},
        fit=FitScore(total=88, recommended_action="apply_now"),
    )
    existing_packet_id = ApplicationPacket(
        opportunity=first,
        candidate_name="Jane Doe",
    ).packet_id
    generated = []

    class FakeTracker:
        def __init__(self, config):
            self.config = config

        def list_packets(self):
            return {
                existing_packet_id: TrackerPacketState(
                    packet_id=existing_packet_id,
                    row_number=2,
                    jd_content_hash="jd-existing",
                    drive_folder_url="https://drive.google.com/drive/folders/existing",
                )
            }

    def complete_enrichment(opportunity):
        return JobDescriptionEnrichmentResult(
            opportunity=opportunity,
            status="existing",
            source="source_description",
            content_hash=opportunity.metadata["jd_content_hash"],
            quality=JobDescriptionQuality(True, len(opportunity.description), 150),
        )

    def generate_packet(opportunity, candidate, provider):
        generated.append(opportunity.company)
        return ApplicationPacket(opportunity=opportunity, candidate_name=candidate.name)

    monkeypatch.setattr("career_agent.cli.main.GoogleSheetsApplicationTracker", FakeTracker)
    monkeypatch.setattr("career_agent.cli.main.enrich_job_description", complete_enrichment)
    monkeypatch.setattr(
        "career_agent.cli.main.score_opportunities_with_fallback",
        lambda opportunities, candidate, provider, description_limit: opportunities,
    )
    monkeypatch.setattr("career_agent.cli.main.generate_application_packet", generate_packet)
    monkeypatch.setattr(
        "career_agent.cli.main.persist_application_packet",
        lambda *args, **kwargs: (None, None, None),
    )
    args = SimpleNamespace(
        candidate_profile="examples/sample_data/candidate_profile.yaml",
        master_resume="examples/sample_data/master_resume.yaml",
        draft_applications=1,
        max_jd_enrichment_attempts=2,
        score_provider="mock",
        application_provider="mock",
        application_output="local",
        application_output_dir="application_packets",
        render_pdf=False,
        debug_output=False,
        tracker_sheet_id="sheet-123",
        tracker_sheet_name="Application Tracker",
        credentials_path=None,
        token_path=None,
        force_regenerate=False,
    )

    batch = draft_application_packets_for_scan(args, [first, second])

    assert generated == ["New Opportunity Fund"]
    assert len(batch.results) == 1
    assert batch.summary["application_already_generated"] == 1
    assert batch.summary["application_jd_attempted"] == 2
    assert batch.opportunities[0].metadata["application_status"] == "already_generated"
    assert batch.opportunities[0].metadata["application_drive_url"].endswith("/existing")
    assert batch.opportunities[1].metadata["application_status"] == "materials_ready"


def test_application_batch_force_regenerates_existing_packet(monkeypatch):
    opportunity = Opportunity(
        source="linkedin_search",
        company="Changed Fund",
        job_title="Impact Analyst",
        job_url="https://example.org/jobs/force",
        description="Responsibilities and qualifications for impact investing. " * 30,
        metadata={"jd_content_hash": "jd-v1"},
        fit=FitScore(total=90, recommended_action="apply_now"),
    )
    packet_id = ApplicationPacket(
        opportunity=opportunity,
        candidate_name="Jane Doe",
    ).packet_id
    generated = []

    class FakeTracker:
        def __init__(self, config):
            self.config = config

        def list_packets(self):
            return {
                packet_id: TrackerPacketState(
                    packet_id=packet_id,
                    row_number=2,
                    jd_content_hash="jd-v1",
                )
            }

    monkeypatch.setattr("career_agent.cli.main.GoogleSheetsApplicationTracker", FakeTracker)
    monkeypatch.setattr(
        "career_agent.cli.main.enrich_job_description",
        lambda item: JobDescriptionEnrichmentResult(
            opportunity=item,
            status="existing",
            source="source_description",
            content_hash="jd-v1",
            quality=JobDescriptionQuality(True, len(item.description), 150),
        ),
    )
    monkeypatch.setattr(
        "career_agent.cli.main.score_opportunities_with_fallback",
        lambda opportunities, candidate, provider, description_limit: opportunities,
    )

    def generate_packet(item, candidate, provider):
        generated.append(item.company)
        return ApplicationPacket(opportunity=item, candidate_name=candidate.name)

    monkeypatch.setattr("career_agent.cli.main.generate_application_packet", generate_packet)
    monkeypatch.setattr(
        "career_agent.cli.main.persist_application_packet",
        lambda *args, **kwargs: (None, None, None),
    )
    args = SimpleNamespace(
        candidate_profile="examples/sample_data/candidate_profile.yaml",
        master_resume="examples/sample_data/master_resume.yaml",
        draft_applications=1,
        max_jd_enrichment_attempts=1,
        score_provider="mock",
        application_provider="mock",
        application_output="local",
        tracker_sheet_id="sheet-123",
        tracker_sheet_name="Application Tracker",
        credentials_path=None,
        token_path=None,
        force_regenerate=True,
    )

    batch = draft_application_packets_for_scan(args, [opportunity])

    assert generated == ["Changed Fund"]
    assert len(batch.results) == 1
    assert batch.summary["application_already_generated"] == 0


def test_scan_jobs_application_packets_can_use_drive_and_tracker(monkeypatch):
    calls = {}

    class FakeLocalSink:
        def __init__(self, root_dir, render_pdf=False, debug_output=False):
            calls["local"] = {
                "root_dir": Path(root_dir),
                "render_pdf": render_pdf,
                "debug_output": debug_output,
            }

        def save(self, packet, candidate):
            folder = calls["local"]["root_dir"] / "packet-folder"
            return SimpleNamespace(
                folder=folder,
                files=[
                    folder / "resume.docx",
                    folder / "cover_letter.docx",
                    folder / "manifest.json",
                ],
                warnings=[],
            )

    class FakeDriveSink:
        def __init__(self, config):
            calls["drive_config"] = config

        def upload_packet_folder(self, folder, files):
            calls["drive_upload"] = {
                "folder": folder,
                "files": [path.name for path in files],
            }
            return SimpleNamespace(
                folder_url="https://drive.google.com/drive/folders/folder-1",
                files=[
                    {"name": "resume.docx", "action": "updated"},
                    {"name": "cover_letter.docx", "action": "updated"},
                ],
            )

    class FakeTracker:
        def __init__(self, config):
            calls["tracker_config"] = config

        def list_packets(self):
            return {}

        def write_packet(
            self,
            packet,
            *,
            output_result=None,
            drive_result=None,
            force=False,
        ):
            calls["tracker_packet"] = packet.packet_id
            calls["tracker_drive_url"] = drive_result.folder_url
            calls["tracker_force"] = force
            return SimpleNamespace(sheet_name="Application Tracker", rows_written=1)

    monkeypatch.setattr("career_agent.cli.main.LocalApplicationPacketSink", FakeLocalSink)
    monkeypatch.setattr("career_agent.cli.main.GoogleDrivePacketSink", FakeDriveSink)
    monkeypatch.setattr("career_agent.cli.main.GoogleSheetsApplicationTracker", FakeTracker)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "scan-jobs",
                "--config",
                "examples/demo_config.yaml",
                "--draft-applications",
                "1",
                "--application-output",
                "drive",
                "--credentials-path",
                "~/credentials.json",
                "--token-path",
                "~/token.json",
                "--replace-existing",
                "--tracker-sheet-id",
                "sheet-123",
            ]
        )

    text = output.getvalue()
    assert exit_code == 0
    assert calls["local"]["root_dir"].name.startswith("career_agent_packet_")
    assert calls["local"]["render_pdf"] is False
    assert calls["local"]["debug_output"] is False
    assert calls["drive_config"].replace_existing is True
    assert calls["drive_config"].credentials_path == "~/credentials.json"
    assert calls["tracker_config"].spreadsheet_id == "sheet-123"
    assert calls["tracker_drive_url"] == "https://drive.google.com/drive/folders/folder-1"
    assert "drive: https://drive.google.com/drive/folders/folder-1" in text
    assert "tracker: Application Tracker (1 row)" in text


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
    from career_agent.sources.news import RSSFetchResult, SourceHealthResult

    signals = [
        Signal(
            source="Impact Entrepreneur",
            title=f"Capital signal {index}",
            signal_subtype="fund_close",
        )
        for index in range(7)
    ]

    monkeypatch.setattr(
        "career_agent.cli.main.RSSNewsSource",
        lambda config: SimpleNamespace(
            fetch_with_health=lambda: RSSFetchResult(
                signals=tuple(signals),
                health_results=(
                    SourceHealthResult(
                        name="Impact Entrepreneur",
                        url="https://example.org/feed",
                        source_group="rss_feeds",
                        ok=True,
                    ),
                ),
            )
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
    from career_agent.sources.news import RSSFetchResult, SourceHealthResult

    sent = {}

    class FakeSender:
        def __init__(self, config):
            self.config = config

        def send_digest(
            self,
            *,
            opportunities,
            source_summary,
            signals=None,
            include_unscored=False,
            subject=None,
        ):
            sent["opportunities"] = len(opportunities)
            sent["signals"] = len(signals or [])
            sent["include_unscored"] = include_unscored
            sent["top_signals"] = source_summary.get("top_signals")
            return {"success": True, "message_id": "message-1"}

    monkeypatch.setenv("GMAIL_ADDRESS", "user@example.com")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "~/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "~/token.json")
    monkeypatch.setattr("career_agent.cli.main.GmailEmailSender", FakeSender)
    monkeypatch.setattr(
        "career_agent.cli.main.RSSNewsSource",
        lambda config: SimpleNamespace(
            fetch_with_health=lambda: RSSFetchResult(
                signals=(
                    Signal(
                        source="Impact Entrepreneur",
                        title="Fund closes new vehicle",
                        signal_subtype="fund_close",
                    ),
                ),
                health_results=(
                    SourceHealthResult(
                        name="Impact Entrepreneur",
                        url="https://example.org/feed",
                        source_group="rss_feeds",
                        ok=True,
                    ),
                ),
            )
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
    assert sent == {
        "opportunities": 3,
        "signals": 1,
        "include_unscored": False,
        "top_signals": 1,
    }


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


def test_draft_application_drive_output_uses_drive_sink(monkeypatch):
    calls = {}

    class FakeLocalSink:
        def __init__(self, root_dir, render_pdf=False, debug_output=False):
            calls["local"] = {
                "root_dir": Path(root_dir),
                "render_pdf": render_pdf,
                "debug_output": debug_output,
            }

        def save(self, packet, candidate):
            folder = calls["local"]["root_dir"] / "packet-folder"
            return SimpleNamespace(
                folder=folder,
                files=[
                    folder / "resume.docx",
                    folder / "cover_letter.docx",
                    folder / "manifest.json",
                ],
                warnings=[],
            )

    class FakeDriveSink:
        def __init__(self, config):
            calls["drive_config"] = config

        def upload_packet_folder(self, folder, files):
            calls["drive_upload"] = {
                "folder": folder,
                "files": [path.name for path in files],
            }
            return SimpleNamespace(
                folder_url="https://drive.google.com/drive/folders/folder-1",
                files=[
                    {"name": "resume.docx"},
                    {"name": "cover_letter.docx"},
                ],
            )

    monkeypatch.setattr("career_agent.cli.main.LocalApplicationPacketSink", FakeLocalSink)
    monkeypatch.setattr("career_agent.cli.main.GoogleDrivePacketSink", FakeDriveSink)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "draft-application",
                "--output",
                "drive",
                "--credentials-path",
                "~/credentials.json",
                "--token-path",
                "~/token.json",
                "--replace-existing",
            ]
        )

    assert exit_code == 0
    assert calls["local"]["render_pdf"] is False
    assert calls["local"]["debug_output"] is False
    assert calls["drive_config"].root_folder_name == "Impact Career Agent"
    assert calls["drive_config"].applications_folder_name == "Applications"
    assert calls["drive_config"].replace_existing is True
    assert calls["drive_upload"]["files"] == [
        "resume.docx",
        "cover_letter.docx",
        "manifest.json",
    ]
    assert "Drive folder: https://drive.google.com/drive/folders/folder-1" in output.getvalue()


def test_draft_application_tracker_sheet_writeback(monkeypatch):
    calls = {}

    class FakeLocalSink:
        def __init__(self, root_dir, render_pdf=False, debug_output=False):
            self.root_dir = Path(root_dir)

        def save(self, packet, candidate):
            folder = self.root_dir / "packet-folder"
            return SimpleNamespace(
                folder=folder,
                files=[
                    folder / "resume.docx",
                    folder / "cover_letter.docx",
                    folder / "manifest.json",
                ],
                warnings=[],
            )

    class FakeDriveSink:
        def __init__(self, config):
            self.config = config

        def upload_packet_folder(self, folder, files):
            return SimpleNamespace(
                folder_url="https://drive.google.com/drive/folders/folder-1",
                files=[
                    {"name": "resume.docx"},
                    {"name": "cover_letter.docx"},
                ],
            )

    class FakeTracker:
        def __init__(self, config):
            calls["tracker_config"] = config

        def write_packet(
            self,
            packet,
            *,
            output_result=None,
            drive_result=None,
            force=False,
        ):
            calls["tracker_packet"] = packet.packet_id
            calls["tracker_drive_url"] = drive_result.folder_url
            return SimpleNamespace(sheet_name="Application Tracker", rows_written=1)

    monkeypatch.setattr("career_agent.cli.main.LocalApplicationPacketSink", FakeLocalSink)
    monkeypatch.setattr("career_agent.cli.main.GoogleDrivePacketSink", FakeDriveSink)
    monkeypatch.setattr("career_agent.cli.main.GoogleSheetsApplicationTracker", FakeTracker)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(
            [
                "draft-application",
                "--output",
                "drive",
                "--credentials-path",
                "~/credentials.json",
                "--token-path",
                "~/token.json",
                "--tracker-sheet-id",
                "sheet-123",
            ]
        )

    assert exit_code == 0
    assert calls["tracker_config"].spreadsheet_id == "sheet-123"
    assert calls["tracker_config"].sheet_name == "Application Tracker"
    assert calls["tracker_config"].credentials_path == "~/credentials.json"
    assert calls["tracker_config"].token_path == "~/token.json"
    assert calls["tracker_drive_url"] == "https://drive.google.com/drive/folders/folder-1"
    assert "Tracker row: Application Tracker (1 row)" in output.getvalue()


def test_draft_application_preview_skips_tracker_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_TRACKER_SHEET_ID", "sheet-from-env")

    class UnexpectedTracker:
        def __init__(self, config):
            raise AssertionError("preview mode should not initialize the Sheets tracker")

    monkeypatch.setattr("career_agent.cli.main.GoogleSheetsApplicationTracker", UnexpectedTracker)

    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(["draft-application"])

    assert exit_code == 0
    assert "Application packet draft" in output.getvalue()
    assert "Tracker row" not in output.getvalue()
