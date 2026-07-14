from email import message_from_bytes
import base64

from career_agent.core import FitScore, Opportunity, Signal
from career_agent.sinks.email import (
    GmailEmailSender,
    GmailSenderConfig,
    build_digest_subject,
    render_job_digest,
)


def test_render_job_digest_groups_by_action():
    opportunities = [
        scored_opportunity("Impact Analyst", "apply_now", 88),
        scored_opportunity("Portfolio Analyst", "review", 72),
        Opportunity(source="linkedin_search", company="Example Bank", job_title="Data Analyst"),
    ]

    digest = render_job_digest(opportunities, {"deduped_total": 3})

    assert "Apply Now (1)" in digest["text"]
    assert "Review (1)" in digest["text"]
    assert "Not Scored Yet" not in digest["text"]
    assert "Impact Career Agent" in digest["html"]
    # Internal source diagnostics should not leak into the reader-facing digest.
    assert "deduped_total" not in digest["html"]
    assert "Source Summary" not in digest["html"]
    assert "Impact Analyst" in digest["html"]
    assert "Data Analyst" not in digest["text"]
    assert "Data Analyst" not in digest["html"]


def test_render_job_digest_can_include_unscored_when_requested():
    opportunities = [
        scored_opportunity("Impact Analyst", "apply_now", 88),
        Opportunity(source="linkedin_search", company="Example Bank", job_title="Data Analyst"),
    ]

    digest = render_job_digest(
        opportunities,
        {"deduped_total": 2},
        include_unscored=True,
    )

    assert "Not Scored Yet (1)" in digest["text"]
    assert "Data Analyst" in digest["text"]
    assert "Not Scored Yet" in digest["html"]


def test_render_job_digest_can_include_capital_signals_before_jobs():
    opportunities = [scored_opportunity("Impact Analyst", "apply_now", 88)]
    signals = [
        Signal(
            source="ImpactAlpha",
            title="Example fund closes new vehicle",
            url="https://example.org/signal",
            signal_subtype="fund_close",
            relevance_score=9,
            confidence=8,
            suggested_action="rescan_org_jobs",
            career_hypothesis="Fresh capital may create investment-team hiring.",
        )
    ]

    digest = render_job_digest(
        opportunities,
        {"deduped_total": 1, "top_signals": 1},
        signals=signals,
    )

    assert "Capital Signals (1)" in digest["text"]
    assert "Example fund closes new vehicle" in digest["text"]
    assert "https://example.org/signal" in digest["text"]
    assert digest["text"].index("Capital Signals") < digest["text"].index("Apply Now")
    assert "Capital Signals" in digest["html"]
    assert "Fresh capital may create investment-team hiring." in digest["html"]
    assert "rescan_org_jobs" not in digest["html"]
    assert "Check careers page" in digest["html"]
    assert "Fund Close" in digest["html"]
    assert digest["html"].index("Capital Signals") < digest["html"].index("Apply Now")


def test_build_digest_subject_counts_actions():
    opportunities = [
        scored_opportunity("Impact Analyst", "apply_now", 88),
        scored_opportunity("Portfolio Analyst", "review", 72),
    ]

    subject = build_digest_subject(opportunities)

    assert "1 Apply Now, 1 Review" in subject


def test_digest_shows_application_status_and_drive_link():
    ready = scored_opportunity("Impact Analyst", "apply_now", 88).model_copy(
        update={
            "metadata": {
                "application_status": "materials_ready",
                "application_drive_url": "https://drive.google.com/drive/folders/example",
            }
        }
    )
    needs_jd = scored_opportunity("Climate Analyst", "apply_now", 84).model_copy(
        update={"metadata": {"application_status": "needs_jd"}}
    )

    digest = render_job_digest([ready, needs_jd], {"deduped_total": 2})

    assert "Application: Application materials ready" in digest["text"]
    assert "Application: Needs full job description" in digest["text"]
    assert "https://drive.google.com/drive/folders/example" in digest["text"]
    assert "Application materials ready" in digest["html"]
    assert "Needs full job description" in digest["html"]
    assert "Open files" in digest["html"]


def test_digest_shows_already_generated_materials_as_ready():
    existing = scored_opportunity("Impact Analyst", "apply_now", 88).model_copy(
        update={
            "metadata": {
                "application_status": "already_generated",
                "application_drive_url": "https://drive.google.com/drive/folders/existing",
            }
        }
    )

    digest = render_job_digest([existing], {"deduped_total": 1})

    assert "Application materials already available" in digest["text"]
    assert "Application materials already available" in digest["html"]
    assert "Open files" in digest["html"]


def test_digest_hides_removed_application_opportunities():
    removed = scored_opportunity("Closed Role", "apply_now", 88).model_copy(
        update={"metadata": {"application_status": "removed"}}
    )

    digest = render_job_digest([removed], {"deduped_total": 1})

    assert "Closed Role" not in digest["text"]
    assert "Closed Role" not in digest["html"]


def test_gmail_email_sender_uses_fake_service():
    service = FakeGmailService()
    sender = GmailEmailSender(
        GmailSenderConfig(
            to_email="to@example.com",
            from_email="from@example.com",
            credentials_path="~/credentials.json",
            token_path="~/token.json",
        )
    )

    result = sender.send_email_with_service(
        service,
        subject="Digest",
        html="<p>Hello</p>",
        text="Hello",
    )

    assert result == {"success": True, "message_id": "message-1", "thread_id": "thread-1"}
    raw = service.sent_body["raw"]
    message = message_from_bytes(base64.urlsafe_b64decode(raw.encode("utf-8")))
    assert message["to"] == "to@example.com"
    assert message["from"] == "from@example.com"
    assert message["subject"] == "Digest"


def scored_opportunity(title: str, action: str, total: int) -> Opportunity:
    return Opportunity(
        source="career_page",
        company="Example Org",
        job_title=title,
        location="Chicago",
        fit=FitScore(
            total=total,
            recommended_action=action,
            match_summary="Good fit.",
        ),
    )


class FakeExecutable:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeMessagesResource:
    def __init__(self, service):
        self.service = service

    def send(self, *, userId, body):
        self.service.sent_user_id = userId
        self.service.sent_body = body
        return FakeExecutable({"id": "message-1", "threadId": "thread-1"})


class FakeUsersResource:
    def __init__(self, service):
        self.service = service

    def messages(self):
        return FakeMessagesResource(self.service)


class FakeGmailService:
    def __init__(self):
        self.sent_user_id = None
        self.sent_body = None

    def users(self):
        return FakeUsersResource(self)
