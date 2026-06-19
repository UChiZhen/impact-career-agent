"""Gmail email sender and digest renderer."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any

from career_agent.core import Opportunity, Signal
from career_agent.sources.watchlist import JOB_RADAR_GOOGLE_SCOPES, resolve_path


@dataclass(frozen=True)
class GmailSenderConfig:
    """Configuration for sending email through Gmail API."""

    to_email: str
    from_email: str | None = None
    credentials_path: str | None = None
    token_path: str | None = None


class GmailEmailSender:
    """Send rendered digests through Gmail API."""

    def __init__(self, config: GmailSenderConfig):
        self.config = config

    def send_digest(
        self,
        *,
        opportunities: list[Opportunity],
        source_summary: dict[str, int],
        signals: list[Signal] | None = None,
        subject: str | None = None,
    ) -> dict:
        digest = render_job_digest(opportunities, source_summary, signals=signals)
        return self.send_email(
            subject=subject or build_digest_subject(opportunities),
            html=digest["html"],
            text=digest["text"],
        )

    def send_email(self, *, subject: str, html: str, text: str) -> dict:
        service = self.build_gmail_service()
        return self.send_email_with_service(service, subject=subject, html=html, text=text)

    def send_email_with_service(self, service: Any, *, subject: str, html: str, text: str) -> dict:
        message = build_mime_message(
            to_email=self.config.to_email,
            from_email=self.config.from_email or self.config.to_email,
            subject=subject,
            html=html,
            text=text,
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {
            "success": True,
            "message_id": sent.get("id", ""),
            "thread_id": sent.get("threadId", ""),
        }

    def build_gmail_service(self):
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Gmail email sending requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[gmail]'`."
            ) from exc

        credentials = self.get_credentials()
        return build("gmail", "v1", credentials=credentials)

    def get_credentials(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError(
                "Gmail authentication requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[gmail]'`."
            ) from exc

        credentials_path = resolve_path(self.config.credentials_path)
        token_path = resolve_path(self.config.token_path)
        if credentials_path is None or token_path is None:
            raise FileNotFoundError("Gmail sending needs credentials_path and token_path.")

        credentials = None
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(
                str(token_path),
                JOB_RADAR_GOOGLE_SCOPES,
            )

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(f"OAuth credentials not found at {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                JOB_RADAR_GOOGLE_SCOPES,
            )
            credentials = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials


def build_mime_message(
    *,
    to_email: str,
    from_email: str,
    subject: str,
    html: str,
    text: str,
) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["to"] = to_email
    message["from"] = from_email
    message["subject"] = subject
    message.attach(MIMEText(text, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))
    return message


def build_digest_subject(opportunities: list[Opportunity]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    apply_now = count_action(opportunities, "apply_now")
    review = count_action(opportunities, "review")
    return f"Impact Career Agent | {today} | {apply_now} Apply Now, {review} Review"


def render_job_digest(
    opportunities: list[Opportunity],
    source_summary: dict[str, int],
    *,
    signals: list[Signal] | None = None,
) -> dict[str, str]:
    """Render text and HTML job digest bodies."""
    apply_now = by_action(opportunities, "apply_now")
    review = by_action(opportunities, "review")
    unscored = [opportunity for opportunity in opportunities if opportunity.fit is None]
    digest_signals = signals or []

    return {
        "text": render_job_digest_text(
            apply_now,
            review,
            unscored,
            source_summary,
            digest_signals,
        ),
        "html": render_job_digest_html(
            apply_now,
            review,
            unscored,
            source_summary,
            digest_signals,
        ),
    }


def render_job_digest_text(
    apply_now: list[Opportunity],
    review: list[Opportunity],
    unscored: list[Opportunity],
    source_summary: dict[str, int],
    signals: list[Signal],
) -> str:
    lines = ["Impact Career Agent Digest", "", "Source summary"]
    lines.extend(f"- {key}: {value}" for key, value in source_summary.items())
    lines.append("")
    lines.extend(render_signal_text_section(signals))
    lines.extend(render_text_section("Apply Now", apply_now))
    lines.extend(render_text_section("Review", review))
    lines.extend(render_text_section("Unscored", unscored))
    return "\n".join(lines).strip()


def render_text_section(title: str, opportunities: list[Opportunity]) -> list[str]:
    if not opportunities:
        return []
    lines = [f"{title} ({len(opportunities)})"]
    for opportunity in sort_opportunities(opportunities)[:20]:
        score = f"{opportunity.fit.total}/100" if opportunity.fit else "unscored"
        lines.append(f"- [{score}] {opportunity.job_title} @ {opportunity.company}")
        if opportunity.location:
            lines.append(f"  Location: {opportunity.location}")
        if opportunity.job_url:
            lines.append(f"  URL: {opportunity.job_url}")
        if opportunity.fit and opportunity.fit.match_summary:
            lines.append(f"  Summary: {opportunity.fit.match_summary}")
    lines.append("")
    return lines


def render_signal_text_section(signals: list[Signal]) -> list[str]:
    if not signals:
        return []
    lines = [f"Capital Signals ({len(signals)})"]
    for signal in signals[:5]:
        score = signal.relevance_score if signal.relevance_score is not None else "unscored"
        confidence = signal.confidence if signal.confidence is not None else "n/a"
        subtype = signal.signal_subtype or "news"
        action = signal.suggested_action or "review"
        lines.append(f"- [{score}/10, confidence {confidence}] {signal.title}")
        lines.append(f"  Source: {signal.source} | Type: {subtype} | Action: {action}")
        if signal.career_hypothesis:
            lines.append(f"  Why it matters: {signal.career_hypothesis}")
        if signal.url:
            lines.append(f"  URL: {signal.url}")
    lines.append("")
    return lines


def render_job_digest_html(
    apply_now: list[Opportunity],
    review: list[Opportunity],
    unscored: list[Opportunity],
    source_summary: dict[str, int],
    signals: list[Signal],
) -> str:
    summary_html = "".join(
        f"<li><strong>{escape(key)}</strong>: {value}</li>" for key, value in source_summary.items()
    )
    return f"""<!doctype html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;">
    <h1>Impact Career Agent Digest</h1>
    <h2>Source Summary</h2>
    <ul>{summary_html}</ul>
    {render_signal_html_section(signals)}
    {render_html_section("Apply Now", apply_now)}
    {render_html_section("Review", review)}
    {render_html_section("Unscored", unscored)}
  </body>
</html>"""


def render_html_section(title: str, opportunities: list[Opportunity]) -> str:
    if not opportunities:
        return ""
    cards = "".join(render_html_card(opportunity) for opportunity in sort_opportunities(opportunities)[:20])
    return f"<h2>{escape(title)} ({len(opportunities)})</h2>{cards}"


def render_signal_html_section(signals: list[Signal]) -> str:
    if not signals:
        return ""
    cards = "".join(render_signal_html_card(signal) for signal in signals[:5])
    return f"<h2>Capital Signals ({len(signals)})</h2>{cards}"


def render_signal_html_card(signal: Signal) -> str:
    score = signal.relevance_score if signal.relevance_score is not None else "unscored"
    confidence = signal.confidence if signal.confidence is not None else "n/a"
    subtype = signal.signal_subtype or "news"
    action = signal.suggested_action or "review"
    title = (
        f'<a href="{escape(signal.url)}">{escape(signal.title)}</a>'
        if signal.url
        else escape(signal.title)
    )
    hypothesis = signal.career_hypothesis or ""
    return f"""
    <div style="border:1px solid #ddd;border-radius:6px;padding:12px;margin:10px 0;">
      <div style="font-weight:600;">{title}</div>
      <div>{escape(signal.source)} | {escape(subtype)} | {escape(str(score))}/10 | confidence {escape(str(confidence))}</div>
      <div>Suggested action: {escape(action)}</div>
      <p>{escape(hypothesis)}</p>
    </div>
    """


def render_html_card(opportunity: Opportunity) -> str:
    score = f"{opportunity.fit.total}/100" if opportunity.fit else "unscored"
    summary = opportunity.fit.match_summary if opportunity.fit else ""
    link = (
        f'<a href="{escape(opportunity.job_url)}">{escape(opportunity.job_title)}</a>'
        if opportunity.job_url
        else escape(opportunity.job_title)
    )
    return f"""
    <div style="border:1px solid #ddd;border-radius:6px;padding:12px;margin:10px 0;">
      <div style="font-weight:600;">{link}</div>
      <div>{escape(opportunity.company)} | {escape(opportunity.location)} | {escape(score)}</div>
      <p>{escape(summary)}</p>
    </div>
    """


def by_action(opportunities: list[Opportunity], action: str) -> list[Opportunity]:
    return [
        opportunity
        for opportunity in opportunities
        if opportunity.fit and opportunity.fit.recommended_action == action
    ]


def count_action(opportunities: list[Opportunity], action: str) -> int:
    return len(by_action(opportunities, action))


def sort_opportunities(opportunities: list[Opportunity]) -> list[Opportunity]:
    return sorted(
        opportunities,
        key=lambda opportunity: opportunity.fit.total if opportunity.fit else -1,
        reverse=True,
    )


def config_from_env(
    *,
    to_email: str | None = None,
    credentials_path: str | None = None,
    token_path: str | None = None,
) -> GmailSenderConfig:
    import os

    recipient = to_email or os.getenv("GMAIL_ADDRESS")
    if not recipient:
        raise RuntimeError("Email sending requires --email-to or GMAIL_ADDRESS.")
    return GmailSenderConfig(
        to_email=recipient,
        from_email=os.getenv("GMAIL_ADDRESS"),
        credentials_path=credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH"),
        token_path=token_path or os.getenv("GOOGLE_TOKEN_PATH"),
    )
