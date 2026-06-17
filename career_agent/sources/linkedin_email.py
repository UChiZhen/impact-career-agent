"""Live LinkedIn alert email source connector boundary.

This module is the future home for the working Gmail parser currently in:

- `linkedin_email/src/gmail_reader.py`

The legacy source searches Gmail using:

`from:jobalerts-noreply@linkedin.com after:YYYY/MM/DD`
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from html import unescape
from html.parser import HTMLParser
import os
from pathlib import Path
import re
from typing import Any

from career_agent.core import Opportunity
from career_agent.sources.opportunities import LINKEDIN_ALERT_SENDER, dedupe_opportunities


GMAIL_READONLY_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)


@dataclass(frozen=True)
class LinkedInEmailSourceConfig:
    """Configuration for LinkedIn job alert emails."""

    sender: str = LINKEDIN_ALERT_SENDER
    hours_back: int = 26
    max_results: int = 20
    credentials_path: str | None = None
    token_path: str | None = None

    @classmethod
    def from_env(cls) -> "LinkedInEmailSourceConfig":
        """Build config from environment variables used by the migration path."""
        return cls(
            sender=os.getenv("LINKEDIN_ALERT_SENDER", LINKEDIN_ALERT_SENDER),
            hours_back=int(os.getenv("LINKEDIN_ALERT_HOURS_BACK", "26")),
            max_results=int(os.getenv("LINKEDIN_ALERT_MAX_RESULTS", "20")),
            credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=os.getenv("GOOGLE_TOKEN_PATH"),
        )

    def gmail_query(self, after_date: str) -> str:
        """Build the Gmail query used by the legacy parser."""
        return f"from:{self.sender} after:{after_date}"


class LinkedInEmailSource:
    """Live source for LinkedIn alert emails in Gmail."""

    source_name = "linkedin_email"

    def __init__(self, config: LinkedInEmailSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch LinkedIn alert opportunities through the Gmail API."""
        service = self.build_gmail_service()
        return self.fetch_from_service(service)

    def fetch_from_service(
        self,
        service: Any,
        *,
        now: datetime | None = None,
    ) -> list[Opportunity]:
        """Fetch and parse LinkedIn alerts from an already-built Gmail service.

        This mirrors the working legacy flow from `linkedin_email/src/gmail_reader.py`:
        list messages by sender/date, get each message with `format=full`, then
        parse the Gmail payload into normalized `Opportunity` objects.
        """
        query = self.gmail_query(now=now)
        messages = self.list_message_metadata(service, query)
        return self.fetch_message_metadata_from_service(service, messages, query)

    def list_message_metadata(self, service: Any, query: str) -> list[dict]:
        """List Gmail message metadata for a query."""
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=self.config.max_results)
            .execute()
        )
        return results.get("messages", [])

    def fetch_message_metadata_from_service(
        self,
        service: Any,
        messages: list[dict],
        query: str,
    ) -> list[Opportunity]:
        """Fetch full Gmail messages from metadata and parse opportunities."""
        opportunities: list[Opportunity] = []
        for message_meta in messages:
            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_meta["id"], format="full")
                .execute()
            )
            for opportunity in parse_gmail_message_payload(message):
                opportunities.append(with_gmail_metadata(opportunity, message, query))

        return dedupe_opportunities(opportunities)

    def gmail_query(self, *, now: datetime | None = None) -> str:
        reference_time = now or datetime.now()
        after_date = (reference_time - timedelta(hours=self.config.hours_back)).strftime("%Y/%m/%d")
        return self.config.gmail_query(after_date)

    def build_gmail_service(self):
        """Build a Gmail API service using local OAuth credentials."""
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Gmail live source requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[gmail]'`."
            ) from exc

        credentials = self.get_credentials()
        return build("gmail", "v1", credentials=credentials)

    def get_credentials(self):
        """Load, refresh, or create local OAuth credentials for Gmail readonly."""
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
            raise FileNotFoundError(
                "Gmail live source needs credentials_path and token_path. "
                "For your existing setup, point them at the old shared Google OAuth files."
            )

        credentials = None
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_path), GMAIL_READONLY_SCOPES)

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(f"OAuth credentials not found at {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                GMAIL_READONLY_SCOPES,
            )
            credentials = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials


class _AnchorTextParser(HTMLParser):
    """Collect anchors and surrounding text from an HTML fragment."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self.text_chunks: list[str] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        self._current_href = attrs_dict.get("href")
        self._current_text = []

    def handle_endtag(self, tag: str):
        if tag.lower() != "a" or self._current_href is None:
            return
        self.anchors.append(
            {
                "href": self._current_href,
                "text": clean_text(" ".join(self._current_text)),
            }
        )
        self._current_href = None
        self._current_text = []

    def handle_data(self, data: str):
        if data:
            self.text_chunks.append(data)
        if self._current_href is not None and data:
            self._current_text.append(data)


def resolve_path(value: str | None) -> Path | None:
    """Resolve an optional local path without assuming a private machine layout."""
    if not value:
        return None
    return Path(value).expanduser()


def with_gmail_metadata(opportunity: Opportunity, message: dict, query: str) -> Opportunity:
    """Attach Gmail provenance while keeping the core parser credential-free."""
    metadata = {
        **opportunity.metadata,
        "gmail_query": query,
    }
    if message.get("id"):
        metadata["gmail_message_id"] = str(message["id"])
    if message.get("threadId"):
        metadata["gmail_thread_id"] = str(message["threadId"])

    return opportunity.model_copy(update={"metadata": metadata})


def parse_linkedin_alert_email_html(
    html: str,
    *,
    subject: str = "",
    date: str = "",
) -> list[Opportunity]:
    """Parse a LinkedIn job alert email body into opportunities.

    This ports the pure parsing behavior from `linkedin_email/src/gmail_reader.py`
    while keeping it independent from Gmail authentication. It supports raw
    LinkedIn alert email HTML and a fallback for Gmail saved-page metadata.
    """
    parser = _AnchorTextParser()
    parser.feed(html)

    opportunities: list[Opportunity] = []
    seen_urls: set[str] = set()
    text = "\n".join(clean_text(chunk) for chunk in parser.text_chunks if clean_text(chunk))

    for anchor in parser.anchors:
        href = anchor["href"]
        if not is_linkedin_job_url(href):
            continue
        clean_url = clean_linkedin_url(href)
        if not clean_url or clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)

        title = anchor["text"] or infer_title_from_subject(subject)
        company = infer_company_from_subject(subject)
        location = infer_location_from_text(text)

        opportunities.append(
            Opportunity(
                source="linkedin_email",
                source_detail="gmail_alert",
                job_title=title or "LinkedIn job alert",
                company=company or "",
                location=location or "",
                job_url=clean_url,
                metadata={
                    "email_subject": subject,
                    "email_date": date,
                },
            )
        )

    if opportunities:
        return opportunities

    return parse_gmail_saved_linkedin_threads(html)


def parse_linkedin_alert_email_text(
    text: str,
    *,
    subject: str = "",
    date: str = "",
) -> list[Opportunity]:
    """Parse LinkedIn's plain-text job alert body.

    The real LinkedIn `.eml` export includes a text/plain part with compact
    repeated blocks:

    title, company, location, optional badges, then `View job: <url>`.
    """
    lines = [clean_text(line) for line in text.splitlines()]
    opportunities: list[Opportunity] = []
    seen_urls: set[str] = set()
    block_start = 0

    for index, line in enumerate(lines):
        if is_separator_line(line):
            block_start = index + 1
            continue

        if not line.lower().startswith("view job:"):
            continue

        raw_url = line.split(":", 1)[1].strip()
        if not is_linkedin_job_url(raw_url):
            continue

        clean_url = clean_linkedin_url(raw_url)
        if not clean_url or clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)

        context_start = max(block_start, index - 12)
        block_lines = [
            candidate
            for candidate in lines[context_start:index]
            if candidate
            and not is_linkedin_alert_badge(candidate)
            and not is_linkedin_alert_control_line(candidate)
        ][-3:]
        title = block_lines[0] if block_lines else infer_title_from_subject(subject)
        company = (
            block_lines[1]
            if len(block_lines) > 1
            else infer_company_from_subject(subject) or "LinkedIn"
        )
        location = block_lines[2] if len(block_lines) > 2 else ""

        if not title:
            continue

        opportunities.append(
            Opportunity(
                source="linkedin_email",
                source_detail="gmail_alert_text",
                job_title=title,
                company=company,
                location=location,
                job_url=clean_url,
                metadata={
                    "email_subject": subject,
                    "email_date": date,
                },
            )
        )

    return opportunities


def parse_linkedin_alert_eml(raw_email: bytes) -> list[Opportunity]:
    """Parse a raw `.eml` LinkedIn alert export into opportunities."""
    message = BytesParser(policy=policy.default).parsebytes(raw_email)
    subject = str(message.get("Subject", ""))
    date = str(message.get("Date", ""))

    text_body = extract_email_message_body(message, "text/plain")
    if text_body:
        opportunities = parse_linkedin_alert_email_text(text_body, subject=subject, date=date)
        if opportunities:
            return opportunities

    html_body = extract_email_message_body(message, "text/html")
    if not html_body:
        return []
    return parse_linkedin_alert_email_html(html_body, subject=subject, date=date)


def parse_gmail_message_payload(message: dict) -> list[Opportunity]:
    """Parse a Gmail API `format=full` message payload into opportunities."""
    payload = message.get("payload", {})
    headers = {
        header.get("name", ""): header.get("value", "")
        for header in payload.get("headers", [])
        if isinstance(header, dict)
    }
    subject = headers.get("Subject", "")
    date = headers.get("Date", "")

    text_body = extract_gmail_payload_body(payload, "text/plain")
    if text_body:
        opportunities = parse_linkedin_alert_email_text(text_body, subject=subject, date=date)
        if opportunities:
            return opportunities

    html_body = extract_gmail_payload_body(payload, "text/html")
    if not html_body:
        return []
    return parse_linkedin_alert_email_html(html_body, subject=subject, date=date)


def extract_email_message_body(message, mime_type: str) -> str:
    """Return the first body part matching `mime_type` from a parsed email."""
    if message.get_content_type() == mime_type:
        try:
            return message.get_content()
        except (LookupError, UnicodeDecodeError):
            return ""

    for part in message.iter_parts() if message.is_multipart() else []:
        body = extract_email_message_body(part, mime_type)
        if body:
            return body

    return ""


def extract_gmail_payload_body(payload: dict, mime_type: str) -> str:
    """Recursively decode the first Gmail payload body matching `mime_type`."""
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data", "")
        if data:
            return decode_gmail_body_data(data)

    for part in payload.get("parts", []):
        body = extract_gmail_payload_body(part, mime_type)
        if body:
            return body

    return ""


def parse_gmail_saved_linkedin_threads(html: str) -> list[Opportunity]:
    """Parse LinkedIn job-alert thread metadata from a saved Gmail page.

    A full Gmail page export is not the raw email body. It stores thread
    metadata in escaped JavaScript strings. This fallback extracts useful
    job-alert metadata from subject/snippet pairs without relying on private
    Gmail APIs.
    """
    decoded = decode_js_escaped_text(html)
    opportunities: list[Opportunity] = []
    seen: set[tuple[str, str, str]] = set()

    sender_positions = [match.start() for match in re.finditer(LINKEDIN_ALERT_SENDER, decoded)]
    for sender_pos in sender_positions:
        window_start = max(0, sender_pos - 1200)
        window_end = min(len(decoded), sender_pos + 1200)
        window = decoded[window_start:window_end]

        subject = extract_linkedin_subject(window)
        if not subject:
            continue

        parsed = parse_job_alert_subject(subject)
        if not parsed:
            continue

        location = infer_location_from_text(window)
        key = (parsed["company"], parsed["job_title"], location)
        if key in seen:
            continue
        seen.add(key)

        opportunities.append(
            Opportunity(
                source="linkedin_email",
                source_detail="gmail_saved_page",
                job_title=parsed["job_title"],
                company=parsed["company"],
                location=location,
                metadata={
                    "email_sender": LINKEDIN_ALERT_SENDER,
                    "email_subject": subject,
                    "posted_date": parsed.get("posted_date", ""),
                },
            )
        )

    return opportunities


def parse_job_alert_subject(subject: str) -> dict[str, str] | None:
    """Extract company/title/date from LinkedIn job alert subjects."""
    cleaned = clean_text(subject)
    if ":" not in cleaned or " posted on " not in cleaned:
        return None

    after_colon = cleaned.split(":", 1)[1].strip()
    before_date, posted_date = after_colon.rsplit(" posted on ", 1)
    posted_date = posted_date.strip()

    if " - " in before_date:
        company, job_title = before_date.split(" - ", 1)
    else:
        company, job_title = "", before_date

    company = company.strip()
    job_title = job_title.strip()
    if not job_title:
        return None

    return {
        "company": company,
        "job_title": job_title,
        "posted_date": posted_date,
    }


def clean_linkedin_url(url: str) -> str:
    """Normalize LinkedIn job URLs from alerts and tracking wrappers."""
    match = re.search(r"(https?://(?:www\.)?linkedin\.com/jobs/view/[^?&\s\"'<>]+)", url)
    if match:
        return match.group(1)

    match = re.search(r"(https?://(?:www\.)?linkedin\.com/(?:comm/)?jobs/view/[^?&\s\"'<>]+)", url)
    if match:
        return match.group(1).replace("linkedin.com/comm/jobs", "linkedin.com/jobs")

    return url.split("?", 1)[0] if "linkedin.com" in url and "/jobs/" in url else ""


def is_linkedin_job_url(url: str) -> bool:
    return bool(re.search(r"linkedin\.com/(?:comm/)?jobs/view/", url))


def is_separator_line(value: str) -> bool:
    return len(value) >= 8 and set(value) <= {"-"}


def is_linkedin_alert_badge(value: str) -> bool:
    lowered = value.lower()
    badge_prefixes = (
        "apply with ",
        "fast growing",
        "this company is actively hiring",
    )
    return lowered.startswith(badge_prefixes) or " connection" in lowered


def is_linkedin_alert_control_line(value: str) -> bool:
    lowered = value.lower()
    control_prefixes = (
        "your job alert for ",
        "manage alerts",
        "see all jobs",
        "edit alert",
        "results from ",
        "new jobs from ",
    )
    return (
        lowered.startswith(control_prefixes)
        or "new jobs match your preferences" in lowered
        or "linkedin.com/jobs/search-results" in lowered
        or "linkedin.com/comm/jobs/search-results" in lowered
        or "<strong" in lowered
    )


def clean_text(value: str) -> str:
    value = unescape(value)
    value = value.replace("\u200f", " ").replace("\u034f", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def decode_js_escaped_text(value: str) -> str:
    """Best-effort decoding for Gmail's escaped JavaScript payload strings."""
    decoded = value
    decoded = decoded.replace(r"\\u0026", "&")
    decoded = decoded.replace(r"\\\"", '"')
    decoded = decoded.replace(r"\/", "/")
    decoded = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        decoded,
    )
    return clean_text(decoded)


def decode_gmail_body_data(data: str) -> str:
    """Decode Gmail API base64url body data with optional missing padding."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def extract_linkedin_subject(text: str) -> str:
    """Find a likely LinkedIn job-alert subject in a text window."""
    pattern = re.compile(r"“[^”]+”: [^\"\\]+? posted on \d{1,2}/\d{1,2}/\d{2,4}")
    match = pattern.search(text)
    if match:
        return clean_text(match.group())
    return ""


def infer_company_from_subject(subject: str) -> str:
    parsed = parse_job_alert_subject(subject)
    return parsed["company"] if parsed else ""


def infer_title_from_subject(subject: str) -> str:
    parsed = parse_job_alert_subject(subject)
    return parsed["job_title"] if parsed else ""


def infer_location_from_text(text: str) -> str:
    match = re.search(r"View jobs in ([^\n\r\"\\]+)", text)
    if not match:
        return ""
    location = clean_text(match.group(1))
    location = re.split(r"\s{2,}| posted on ", location, maxsplit=1)[0]
    return location.strip()
