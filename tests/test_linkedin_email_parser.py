from pathlib import Path

from career_agent.sources.linkedin_email import (
    LINKEDIN_ALERT_SENDER,
    clean_linkedin_url,
    parse_gmail_saved_linkedin_threads,
    parse_job_alert_subject,
    parse_linkedin_alert_email_html,
)


def test_parse_job_alert_subject():
    parsed = parse_job_alert_subject(
        "“( development finance OR DFI )”: Example Capital - Analyst posted on 6/10/26"
    )

    assert parsed == {
        "company": "Example Capital",
        "job_title": "Analyst",
        "posted_date": "6/10/26",
    }


def test_clean_linkedin_url_strips_tracking_params():
    url = clean_linkedin_url("https://www.linkedin.com/jobs/view/123456?trackingId=abc")

    assert url == "https://www.linkedin.com/jobs/view/123456"


def test_parse_raw_linkedin_alert_email_html():
    html = """
    <html>
      <body>
        <p>View jobs in United Kingdom</p>
        <a href="https://www.linkedin.com/jobs/view/123456?trackingId=abc">
          Analyst
        </a>
      </body>
    </html>
    """

    opportunities = parse_linkedin_alert_email_html(
        html,
        subject="“( development finance OR DFI )”: Example Capital - Analyst posted on 6/10/26",
        date="Wed, 10 Jun 2026 06:00:00 -0500",
    )

    assert len(opportunities) == 1
    assert opportunities[0].source == "linkedin_email"
    assert opportunities[0].job_title == "Analyst"
    assert opportunities[0].company == "Example Capital"
    assert opportunities[0].location == "United Kingdom"
    assert opportunities[0].job_url == "https://www.linkedin.com/jobs/view/123456"


def test_parse_gmail_saved_page_thread_metadata_fixture():
    html = f"""
    <script>
    var data = "\\u201c( \\\\\\"development finance\\\\\\" OR DFI OR\\u2026\\u201d:
    Example Capital - Analyst posted on 6/10/26",
    "View jobs in United Kingdom", "{LINKEDIN_ALERT_SENDER}";
    </script>
    """

    opportunities = parse_gmail_saved_linkedin_threads(html)

    assert len(opportunities) == 1
    assert opportunities[0].source_detail == "gmail_saved_page"
    assert opportunities[0].company == "Example Capital"
    assert opportunities[0].job_title == "Analyst"
    assert opportunities[0].location == "United Kingdom"


def test_local_user_download_smoke_if_present():
    """Optional local smoke test for the maintainer's exported Gmail page.

    This does not ship private HTML in the repository and quietly skips when the
    local file is absent.
    """
    path = Path(
        "/Users/zz/Downloads/“( _development finance_ OR DFI OR…”_ "
        "LCM Partners - Analyst posted on 6_10_26 - "
        "zhenzeng37@gmail.com - Gmail.html"
    )
    if not path.exists():
        return

    opportunities = parse_gmail_saved_linkedin_threads(path.read_text(encoding="utf-8"))

    assert any(
        opportunity.company == "LCM Partners" and opportunity.job_title == "Analyst"
        for opportunity in opportunities
    )
