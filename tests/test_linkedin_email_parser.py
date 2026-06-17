import base64
from email.message import EmailMessage
import os
from pathlib import Path

from career_agent.sources.linkedin_email import (
    LINKEDIN_ALERT_SENDER,
    clean_linkedin_url,
    parse_gmail_saved_linkedin_threads,
    parse_gmail_message_payload,
    parse_job_alert_subject,
    parse_linkedin_alert_email_text,
    parse_linkedin_alert_eml,
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


def test_parse_raw_linkedin_alert_email_html_ignores_alert_management_links():
    html = """
    <html>
      <body>
        <a href="https://www.linkedin.com/comm/jobs/search-results/">Search results</a>
        <a href="https://www.linkedin.com/comm/jobs/alerts">Manage alerts</a>
        <a href="https://www.linkedin.com/jobs/view/123456?trackingId=abc">Analyst</a>
      </body>
    </html>
    """

    opportunities = parse_linkedin_alert_email_html(
        html,
        subject="“( impact investing )”: Example Capital - Analyst posted on 6/10/26",
    )

    assert len(opportunities) == 1
    assert opportunities[0].job_url == "https://www.linkedin.com/jobs/view/123456"


def test_parse_linkedin_alert_email_text_blocks():
    text = """
    Analyst
    Example Capital
    London Area, United Kingdom
    Fast growing
    Apply with resume & profile
    View job: https://www.linkedin.com/comm/jobs/view/123456/?trackingId=abc

    ---------------------------------------------------------

    Associate, Climate Finance
    Example Green Bank
    Chicago, IL
    This company is actively hiring
    View job: https://www.linkedin.com/comm/jobs/view/987654/?trackingId=def
    """

    opportunities = parse_linkedin_alert_email_text(
        text,
        subject="“( impact investing )”: Example Capital - Analyst posted on 6/10/26",
        date="Wed, 10 Jun 2026 06:00:00 -0500",
    )

    assert len(opportunities) == 2
    assert opportunities[0].job_title == "Analyst"
    assert opportunities[0].company == "Example Capital"
    assert opportunities[0].location == "London Area, United Kingdom"
    assert opportunities[0].job_url == "https://www.linkedin.com/jobs/view/123456/"
    assert opportunities[1].job_title == "Associate, Climate Finance"


def test_parse_linkedin_alert_eml_prefers_plain_text_part():
    message = EmailMessage()
    message["From"] = f"LinkedIn Job Alerts <{LINKEDIN_ALERT_SENDER}>"
    message["Subject"] = "“( impact investing )”: Example Capital - Analyst posted on 6/10/26"
    message["Date"] = "Wed, 10 Jun 2026 06:00:00 -0500"
    message.set_content(
        """
        Analyst
        Example Capital
        London
        View job: https://www.linkedin.com/comm/jobs/view/123456/?trackingId=abc
        """
    )
    message.add_alternative(
        """
        <html><body>
          <a href="https://www.linkedin.com/comm/jobs/alerts">Manage alerts</a>
        </body></html>
        """,
        subtype="html",
    )

    opportunities = parse_linkedin_alert_eml(message.as_bytes())

    assert len(opportunities) == 1
    assert opportunities[0].source_detail == "gmail_alert_text"
    assert opportunities[0].company == "Example Capital"


def test_parse_gmail_message_payload_decodes_base64url_text_body():
    body = """
    Analyst
    Example Capital
    London
    View job: https://www.linkedin.com/comm/jobs/view/123456/?trackingId=abc
    """
    encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8").rstrip("=")
    payload = {
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
        }
    }

    opportunities = parse_gmail_message_payload(payload)

    assert len(opportunities) == 1
    assert opportunities[0].job_url == "https://www.linkedin.com/jobs/view/123456/"


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


def test_local_linkedin_alert_eml_smoke_if_configured():
    """Optional private smoke test for a maintainer-provided `.eml` file.

    This does not ship private email contents or local paths in the repository.
    """
    sample_path = os.environ.get("LINKEDIN_ALERT_SAMPLE_EML")
    if not sample_path:
        return

    path = Path(sample_path)
    if not path.exists():
        return

    opportunities = parse_linkedin_alert_eml(path.read_bytes())

    assert opportunities
    assert all(opportunity.source == "linkedin_email" for opportunity in opportunities)
