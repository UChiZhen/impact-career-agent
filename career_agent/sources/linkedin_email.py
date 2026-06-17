"""Live LinkedIn alert email source connector boundary.

This module is the future home for the working Gmail parser currently in:

- `linkedin_email/src/gmail_reader.py`

The legacy source searches Gmail using:

`from:jobalerts-noreply@linkedin.com after:YYYY/MM/DD`
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re

from career_agent.core import Opportunity
from career_agent.sources.opportunities import LINKEDIN_ALERT_SENDER


@dataclass(frozen=True)
class LinkedInEmailSourceConfig:
    """Configuration for LinkedIn job alert emails."""

    sender: str = LINKEDIN_ALERT_SENDER
    hours_back: int = 26
    max_results: int = 20
    credentials_path: str | None = None
    token_path: str | None = None

    def gmail_query(self, after_date: str) -> str:
        """Build the Gmail query used by the legacy parser."""
        return f"from:{self.sender} after:{after_date}"


class LinkedInEmailSource:
    """Live source for LinkedIn alert emails in Gmail."""

    source_name = "linkedin_email"

    def __init__(self, config: LinkedInEmailSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch opportunities from LinkedIn alert emails.

        Porting target:
        1. Authenticate with Gmail readonly scope.
        2. Search for `config.gmail_query(after_date)`.
        3. Parse HTML job cards and `/jobs/view/` links with
           `parse_linkedin_alert_email_html`.
        4. Normalize each result into `Opportunity(source="linkedin_email")`.
        """
        raise NotImplementedError("Live LinkedIn email parsing will be ported after v0.1 fixtures")


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
    return "linkedin.com" in url and "/jobs/" in url


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
