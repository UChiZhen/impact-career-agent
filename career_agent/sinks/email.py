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
    today = format_digest_date(datetime.now())
    lines = ["Impact Career Agent Digest", today, ""]
    lines.extend(render_signal_text_section(signals))
    lines.extend(render_text_section("Apply Now", apply_now))
    lines.extend(render_text_section("Review", review))
    lines.extend(render_text_section("Not Scored Yet", unscored))
    return "\n".join(lines).strip()


def render_text_section(title: str, opportunities: list[Opportunity]) -> list[str]:
    if not opportunities:
        return []
    lines = [f"{title} ({len(opportunities)})"]
    for opportunity in sort_opportunities(opportunities)[:20]:
        score = f"{opportunity.fit.total}/100" if opportunity.fit else "not scored"
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
        subtype = format_signal_subtype(signal.signal_subtype)
        action = format_signal_action(signal.suggested_action)
        lines.append(f"- [{score}/10, confidence {confidence}] {signal.title}")
        lines.append(f"  Source: {signal.source} | Type: {subtype} | Action: {action}")
        if signal.career_hypothesis:
            lines.append(f"  Why it matters: {signal.career_hypothesis}")
        if signal.url:
            lines.append(f"  URL: {signal.url}")
    lines.append("")
    return lines


# Visual theme shared across the HTML digest. Inline styles only, since most
# email clients strip <style> blocks and ignore flexbox/grid.
_BRAND = "#0f766e"  # teal header banner
_BRAND_DARK = "#115e59"
_INK = "#1f2937"  # primary text
_MUTED = "#6b7280"  # secondary text
_PAGE_BG = "#f1f5f9"  # outer page background
_CARD_BG = "#ffffff"
_BORDER = "#e5e7eb"
_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Per-section accent colors (heading bar + card left border).
_SECTION_THEME = {
    "Apply Now": "#16a34a",  # green
    "Review": "#2563eb",  # blue
    "Not Scored Yet": "#94a3b8",  # slate
    "Capital Signals": "#7c3aed",  # purple
}

_SIGNAL_ACTION_LABELS = {
    "rescan_org_jobs": "Check careers page",
    "add_to_watchlist": "Add to watchlist",
    "search_linkedin": "Search LinkedIn",
    "review_keywords": "Review search keywords",
    "ignore": "No action",
    "review": "Review",
}


def render_job_digest_html(
    apply_now: list[Opportunity],
    review: list[Opportunity],
    unscored: list[Opportunity],
    source_summary: dict[str, int],
    signals: list[Signal],
) -> str:
    today = format_digest_date(datetime.now())
    apply_count = len(apply_now)
    review_count = len(review)
    headline = (
        f"{apply_count} to apply now &middot; {review_count} to review"
        if (apply_count or review_count)
        else "Your latest impact-career scan"
    )
    body = "".join(
        [
            render_signal_html_section(signals),
            render_html_section("Apply Now", apply_now),
            render_html_section("Review", review),
            render_html_section("Not Scored Yet", unscored),
        ]
    )
    if not body:
        body = (
            f'<p style="margin:24px 0;color:{_MUTED};font-size:15px;">'
            "No new opportunities or signals in this scan. We&rsquo;ll keep watching.</p>"
        )
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{_PAGE_BG};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PAGE_BG};">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:{_CARD_BG};border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,0.08);font-family:{_FONT};">
            <tr>
              <td style="background:{_BRAND};background-image:linear-gradient(135deg,{_BRAND} 0%,{_BRAND_DARK} 100%);padding:28px 32px;">
                <div style="color:#d1fae5;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">Impact Career Agent</div>
                <div style="color:#ffffff;font-size:22px;font-weight:700;margin-top:6px;">{headline}</div>
                <div style="color:#a7f3d0;font-size:13px;margin-top:6px;">{escape(today)}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 12px 32px;color:{_INK};">
                {body}
              </td>
            </tr>
            <tr>
              <td style="padding:8px 32px 28px 32px;border-top:1px solid {_BORDER};">
                <div style="color:{_MUTED};font-size:12px;line-height:1.6;">
                  Curated by your Impact Career Agent. Scores are directional guidance, not gospel &mdash; trust your own read.
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def render_section_heading(title: str, count: int) -> str:
    accent = _SECTION_THEME.get(title, _BRAND)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:18px 0 10px 0;"><tr>'
        f'<td style="font-size:15px;font-weight:700;color:{_INK};">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:3px;'
        f'background:{accent};margin-right:8px;"></span>{escape(title)}</td>'
        f'<td align="right"><span style="display:inline-block;background:{accent};color:#ffffff;'
        f'font-size:12px;font-weight:700;padding:2px 9px;border-radius:999px;">{count}</span></td>'
        "</tr></table>"
    )


def render_html_section(title: str, opportunities: list[Opportunity]) -> str:
    if not opportunities:
        return ""
    accent = _SECTION_THEME.get(title, _BRAND)
    cards = "".join(
        render_html_card(opportunity, accent)
        for opportunity in sort_opportunities(opportunities)[:20]
    )
    return render_section_heading(title, len(opportunities)) + cards


def render_signal_html_section(signals: list[Signal]) -> str:
    if not signals:
        return ""
    accent = _SECTION_THEME["Capital Signals"]
    cards = "".join(render_signal_html_card(signal, accent) for signal in signals[:5])
    return render_section_heading("Capital Signals", len(signals)) + cards


def format_digest_date(value: datetime) -> str:
    """Format digest dates without platform-specific strftime directives."""
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


def format_signal_subtype(value: str | None) -> str:
    """Convert internal signal subtypes into reader-facing labels."""
    if not value:
        return "News"
    return value.replace("_", " ").title()


def format_signal_action(value: str | None) -> str:
    """Convert internal workflow actions into reader-facing labels."""
    normalized = (value or "review").strip().lower()
    return _SIGNAL_ACTION_LABELS.get(normalized, normalized.replace("_", " ").title())


def _score_pill(label: str, value: int | None, scale: int) -> str:
    """Colored badge whose color reflects the score band."""
    if value is None:
        bg, fg = "#f1f5f9", _MUTED
        text = label
    else:
        ratio = value / scale
        if ratio >= 0.8:
            bg, fg = "#dcfce7", "#166534"
        elif ratio >= 0.6:
            bg, fg = "#fef3c7", "#92400e"
        else:
            bg, fg = "#f1f5f9", "#475569"
        text = f"{value}/{scale}"
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};font-size:12px;'
        f'font-weight:700;padding:3px 10px;border-radius:999px;white-space:nowrap;">{escape(text)}</span>'
    )


def _card_shell(accent: str, inner: str) -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:0 0 10px 0;background:{_CARD_BG};border:1px solid {_BORDER};'
        f'border-left:4px solid {accent};border-radius:8px;">'
        f'<tr><td style="padding:14px 16px;">{inner}</td></tr></table>'
    )


def render_html_card(opportunity: Opportunity, accent: str) -> str:
    fit = opportunity.fit
    pill = _score_pill("not scored", fit.total if fit else None, 100)
    title_text = escape(opportunity.job_title)
    link = (
        f'<a href="{escape(opportunity.job_url)}" style="color:{_BRAND_DARK};text-decoration:none;">{title_text}</a>'
        if opportunity.job_url
        else title_text
    )
    meta_parts = [escape(opportunity.company)]
    if opportunity.location:
        meta_parts.append(escape(opportunity.location))
    meta = " &middot; ".join(meta_parts)
    summary = fit.match_summary if fit else ""
    summary_html = (
        f'<div style="margin-top:8px;font-size:14px;line-height:1.5;color:{_INK};">{escape(summary)}</div>'
        if summary
        else ""
    )
    inner = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="font-size:15px;font-weight:700;color:{_INK};">{link}</td>'
        f'<td align="right" style="vertical-align:top;padding-left:8px;">{pill}</td>'
        "</tr></table>"
        f'<div style="margin-top:3px;font-size:13px;color:{_MUTED};">{meta}</div>'
        f"{summary_html}"
    )
    return _card_shell(accent, inner)


def render_signal_html_card(signal: Signal, accent: str) -> str:
    pill = _score_pill("not scored", signal.relevance_score, 10)
    subtype = format_signal_subtype(signal.signal_subtype)
    action = format_signal_action(signal.suggested_action)
    title_text = escape(signal.title)
    title = (
        f'<a href="{escape(signal.url)}" style="color:{_BRAND_DARK};text-decoration:none;">{title_text}</a>'
        if signal.url
        else title_text
    )
    hypothesis = signal.career_hypothesis or ""
    hypothesis_html = (
        f'<div style="margin-top:8px;font-size:14px;line-height:1.5;color:{_INK};">{escape(hypothesis)}</div>'
        if hypothesis
        else ""
    )
    tag = (
        f'<span style="display:inline-block;background:#f3e8ff;color:#6b21a8;font-size:11px;'
        f'font-weight:700;padding:2px 8px;border-radius:999px;text-transform:uppercase;'
        f'letter-spacing:0.3px;">{escape(subtype)}</span>'
    )
    inner = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="font-size:15px;font-weight:700;color:{_INK};">{title}</td>'
        f'<td align="right" style="vertical-align:top;padding-left:8px;">{pill}</td>'
        "</tr></table>"
        f'<div style="margin-top:6px;">{tag}'
        f'<span style="font-size:13px;color:{_MUTED};margin-left:8px;">{escape(signal.source)} '
        f'&middot; Next: {escape(action)}</span></div>'
        f"{hypothesis_html}"
    )
    return _card_shell(accent, inner)


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
