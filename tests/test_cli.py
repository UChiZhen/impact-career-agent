from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from career_agent import __version__
from career_agent.cli.main import linkedin_email_config_from_args, main


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
