from email import message_from_bytes
import base64

from career_agent.core import FitScore, Opportunity
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
    assert "Unscored (1)" in digest["text"]
    assert "Impact Career Agent Digest" in digest["html"]
    assert "deduped_total" in digest["html"]


def test_build_digest_subject_counts_actions():
    opportunities = [
        scored_opportunity("Impact Analyst", "apply_now", 88),
        scored_opportunity("Portfolio Analyst", "review", 72),
    ]

    subject = build_digest_subject(opportunities)

    assert "1 Apply Now, 1 Review" in subject


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
