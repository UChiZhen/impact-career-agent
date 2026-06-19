"""News and capital-signal source connectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import os
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import yaml

from career_agent.core import Signal
from career_agent.sources.linkedin_email import (
    GMAIL_READONLY_SCOPES,
    extract_email_message_body,
    extract_gmail_payload_body,
    resolve_path,
)


IMPACTALPHA_SENDER = "editor@impactalpha.com"
DEFAULT_NEWS_SOURCE_PACK = Path("examples/source_packs/impact_capital_signals.yaml")


@dataclass(frozen=True)
class NewsFeedConfig:
    """Configuration for one public news feed."""

    name: str
    url: str
    category: str = "impact_investing"
    vertical: str = "impact_investing"


@dataclass(frozen=True)
class NewsSourcePack:
    """Public-safe source-pack configuration."""

    name: str
    verticals: tuple[str, ...]
    rss_feeds: tuple[NewsFeedConfig, ...]
    web_sources: tuple[dict[str, str], ...] = ()
    regulatory_sources: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class RSSNewsSourceConfig:
    """Configuration for RSS/Atom fetching."""

    feeds: tuple[NewsFeedConfig, ...]
    timeout_seconds: int = 20
    user_agent: str = "ImpactCareerAgent/0.1 (+https://github.com/UChiZhen)"


class RSSNewsSource:
    """Fetch public RSS/Atom feeds and normalize entries into Signals."""

    source_name = "rss_news"

    def __init__(self, config: RSSNewsSourceConfig):
        self.config = config

    def fetch(self) -> list[Signal]:
        """Fetch all configured RSS/Atom feeds."""
        signals: list[Signal] = []
        for feed in self.config.feeds:
            request = Request(feed.url, headers={"User-Agent": self.config.user_agent})
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                xml_text = response.read().decode("utf-8", errors="replace")
            signals.extend(signals_from_rss_xml(xml_text, feed))
        return dedupe_signals(signals)


@dataclass(frozen=True)
class ImpactAlphaNewsletterConfig:
    """Configuration for ImpactAlpha newsletter emails in Gmail."""

    sender: str = IMPACTALPHA_SENDER
    query: str | None = None
    hours_back: int = 26
    max_results: int = 10
    credentials_path: str | None = None
    token_path: str | None = None

    @classmethod
    def from_env(cls) -> "ImpactAlphaNewsletterConfig":
        """Build config from local environment variables."""
        return cls(
            sender=os.getenv("IMPACTALPHA_NEWSLETTER_SENDER", IMPACTALPHA_SENDER),
            query=os.getenv("IMPACTALPHA_NEWSLETTER_QUERY"),
            hours_back=int(os.getenv("IMPACTALPHA_NEWSLETTER_HOURS_BACK", "26")),
            max_results=int(os.getenv("IMPACTALPHA_NEWSLETTER_MAX_RESULTS", "10")),
            credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=os.getenv("GOOGLE_TOKEN_PATH"),
        )

    def gmail_query(self, after_date: str) -> str:
        """Build the Gmail query for ImpactAlpha newsletters."""
        if self.query:
            return self.query.format(after_date=after_date, sender=self.sender)
        return f"from:{self.sender} after:{after_date}"


class ImpactAlphaNewsletterSource:
    """Live Gmail source for ImpactAlpha newsletter emails."""

    source_name = "impactalpha_newsletter"

    def __init__(self, config: ImpactAlphaNewsletterConfig):
        self.config = config

    def fetch(self) -> list[Signal]:
        """Fetch ImpactAlpha newsletter signals through the Gmail API."""
        service = self.build_gmail_service()
        return self.fetch_from_service(service)

    def fetch_from_service(self, service: Any, *, now: datetime | None = None) -> list[Signal]:
        """Fetch and parse ImpactAlpha newsletters from an existing Gmail service."""
        query = self.gmail_query(now=now)
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=self.config.max_results)
            .execute()
        )
        signals: list[Signal] = []
        for message_meta in results.get("messages", []):
            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_meta["id"], format="full")
                .execute()
            )
            for signal in parse_impactalpha_gmail_payload(message):
                metadata = {
                    **signal.metadata,
                    "gmail_query": query,
                    "gmail_message_id": str(message.get("id", "")),
                }
                signals.append(signal.model_copy(update={"metadata": metadata}))
        return dedupe_signals(signals)

    def gmail_query(self, *, now: datetime | None = None) -> str:
        """Build the relative-date Gmail query."""
        reference_time = now or datetime.now()
        after_date = (reference_time - timedelta(hours=self.config.hours_back)).strftime("%Y/%m/%d")
        return self.config.gmail_query(after_date)

    def build_gmail_service(self):
        """Build a Gmail API service using local OAuth credentials."""
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "ImpactAlpha Gmail source requires optional Google dependencies. "
                "Install with `pip install 'impact-career-agent[gmail]'`."
            ) from exc

        credentials = self.get_credentials()
        return build("gmail", "v1", credentials=credentials)

    def get_credentials(self):
        """Load, refresh, or create local OAuth credentials for Gmail readonly."""
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
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
                "ImpactAlpha Gmail source needs credentials_path and token_path."
            )

        credentials = None
        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_path), GMAIL_READONLY_SCOPES)

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleAuthRequest())
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


class _NewsletterHTMLParser(HTMLParser):
    """Collect readable text and anchors from newsletter HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self.text_chunks: list[str] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        self._href = attrs_dict.get("href")
        self._anchor_text = []

    def handle_endtag(self, tag: str):
        if tag.lower() != "a" or self._href is None:
            return
        self.anchors.append(
            {
                "href": self._href,
                "text": clean_news_text(" ".join(self._anchor_text)),
            }
        )
        self._href = None
        self._anchor_text = []

    def handle_data(self, data: str):
        if data:
            self.text_chunks.append(data)
        if self._href is not None and data:
            self._anchor_text.append(data)


def load_news_source_pack(path: Path = DEFAULT_NEWS_SOURCE_PACK) -> NewsSourcePack:
    """Load a public source-pack YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    feeds = tuple(
        NewsFeedConfig(
            name=str(item["name"]),
            url=str(item["url"]),
            category=str(item.get("category", "impact_investing")),
            vertical=str(item.get("vertical", item.get("category", "impact_investing"))),
        )
        for item in data.get("rss_feeds", [])
    )
    return NewsSourcePack(
        name=str(data.get("name", path.stem)),
        verticals=tuple(str(item) for item in data.get("verticals", [])),
        rss_feeds=feeds,
        web_sources=tuple(dict(item) for item in data.get("web_sources", [])),
        regulatory_sources=tuple(dict(item) for item in data.get("regulatory_sources", [])),
    )


def signals_from_rss_xml(xml_text: str, feed: NewsFeedConfig) -> list[Signal]:
    """Parse RSS or Atom XML into Signal objects."""
    root = ET.fromstring(xml_text)
    entries = root.findall(".//item")
    if not entries:
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    signals: list[Signal] = []
    for entry in entries:
        title = first_xml_text(entry, ("title", "{http://www.w3.org/2005/Atom}title"))
        url = first_xml_text(entry, ("link",))
        if not url:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            url = atom_link.attrib.get("href", "") if atom_link is not None else ""
        summary = first_xml_text(
            entry,
            (
                "description",
                "summary",
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            ),
        )
        published_raw = first_xml_text(
            entry,
            ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}updated"),
        )
        if not title:
            continue
        signals.append(
            enrich_capital_signal(
                Signal(
                    source=feed.name,
                    title=clean_news_text(title),
                    signal_type="news",
                    url=clean_news_text(url) or None,
                    category=feed.category,
                    summary=clean_news_text(summary) or None,
                    raw_text=clean_news_text(summary) or None,
                    published_at=parse_email_date(published_raw),
                    metadata={"vertical": feed.vertical, "source_type": "rss"},
                )
            )
        )
    return dedupe_signals(signals)


def parse_impactalpha_newsletter_eml(raw_email: bytes) -> list[Signal]:
    """Parse a raw ImpactAlpha newsletter `.eml` export into capital signals."""
    message = BytesParser(policy=policy.default).parsebytes(raw_email)
    subject = str(message.get("Subject", ""))
    date = str(message.get("Date", ""))

    html_body = extract_email_message_body(message, "text/html")
    if html_body:
        signals = parse_impactalpha_newsletter_html(html_body, subject=subject, date=date)
        if signals:
            return signals

    text_body = extract_email_message_body(message, "text/plain")
    if not text_body:
        return []
    return parse_impactalpha_newsletter_text(text_body, subject=subject, date=date)


def parse_impactalpha_gmail_payload(message: dict) -> list[Signal]:
    """Parse a Gmail API `format=full` ImpactAlpha message payload."""
    payload = message.get("payload", {})
    headers = {
        header.get("name", ""): header.get("value", "")
        for header in payload.get("headers", [])
        if isinstance(header, dict)
    }
    subject = headers.get("Subject", "")
    date = headers.get("Date", "")
    html_body = extract_gmail_payload_body(payload, "text/html")
    if html_body:
        signals = parse_impactalpha_newsletter_html(html_body, subject=subject, date=date)
        if signals:
            return signals
    text_body = extract_gmail_payload_body(payload, "text/plain")
    if not text_body:
        return []
    return parse_impactalpha_newsletter_text(text_body, subject=subject, date=date)


def parse_impactalpha_newsletter_html(
    html: str,
    *,
    subject: str = "",
    date: str = "",
) -> list[Signal]:
    """Extract likely article/deal signals from ImpactAlpha newsletter HTML."""
    parser = _NewsletterHTMLParser()
    parser.feed(html)
    newsletter_context = clean_news_text(" ".join(parser.text_chunks))[:1200]
    signals: list[Signal] = []

    for anchor in parser.anchors:
        title = clean_news_text(anchor["text"])
        if not is_content_link(anchor["href"], title):
            continue
        signals.append(
            build_newsletter_signal(
                title=title,
                url=anchor["href"],
                subject=subject,
                date=date,
                raw_text=newsletter_context,
                source_detail="impactalpha_html",
            )
        )

    return dedupe_signals(signals)


def parse_impactalpha_newsletter_text(
    text: str,
    *,
    subject: str = "",
    date: str = "",
) -> list[Signal]:
    """Extract likely article/deal signals from newsletter plain text."""
    lines = [clean_news_text(line) for line in text.splitlines()]
    signals: list[Signal] = []
    for index, line in enumerate(lines):
        if not line.startswith("http"):
            continue
        title = previous_content_line(lines, index)
        if not title or not is_content_link(line, title):
            continue
        signals.append(
            build_newsletter_signal(
                title=title,
                url=line,
                subject=subject,
                date=date,
                raw_text=" ".join(lines[max(0, index - 4) : index + 1]),
                source_detail="impactalpha_text",
            )
        )
    return dedupe_signals(signals)


def build_newsletter_signal(
    *,
    title: str,
    url: str,
    subject: str,
    date: str,
    raw_text: str,
    source_detail: str,
) -> Signal:
    """Build an enriched ImpactAlpha newsletter signal."""
    return enrich_capital_signal(
        Signal(
            source="ImpactAlpha",
            title=title,
            signal_type="news",
            url=clean_news_url(url),
            category="impact_investing",
            summary=None,
            raw_text=raw_text or None,
            published_at=parse_email_date(date),
            metadata={
                "email_subject": subject,
                "email_date": date,
                "source_type": "newsletter",
                "source_detail": source_detail,
                "vertical": "impact_investing",
            },
        )
    )


def enrich_capital_signal(signal: Signal) -> Signal:
    """Add a simple deterministic career-signal classification."""
    combined = f"{signal.title} {signal.summary or ''} {signal.raw_text or ''}".lower()
    subtype = classify_capital_signal(combined)
    hypothesis = career_hypothesis_for_subtype(subtype)
    action = suggested_action_for_subtype(subtype)
    return signal.model_copy(
        update={
            "signal_subtype": subtype,
            "career_hypothesis": hypothesis,
            "suggested_action": action,
            "confidence": 6 if subtype != "macro_tailwind" else 4,
        }
    )


def classify_capital_signal(text: str) -> str:
    """Classify a text snippet into a career-oriented capital signal type."""
    if has_any(text, ("final close", "fund close", "closed its", "raised", "new fund")):
        return "fund_close"
    if has_any(text, ("launch", "launched", "forms", "formation", "new gp")):
        return "fund_launch"
    if has_any(text, ("commitment", "committed", "lp", "limited partner", "pension")):
        return "lp_commitment"
    if has_any(text, ("investment", "invests", "invested", "backs", "financing", "loan")):
        return "transaction"
    if has_any(text, ("portfolio company", "portfolio companies")):
        return "portfolio_investment"
    if has_any(text, ("new office", "expands", "expansion", "new region", "opens in")):
        return "new_office_or_region"
    if has_any(text, ("hire", "hiring", "team", "appoints", "joins as")):
        return "hiring_signal"
    if has_any(text, ("grant", "program", "accelerator", "fellowship")):
        return "program_or_grant"
    return "macro_tailwind"


def career_hypothesis_for_subtype(subtype: str) -> str:
    """Explain why a signal may matter for career search."""
    mapping = {
        "fund_close": "Fresh committed capital often precedes portfolio work, operations buildout, and investment-team hiring.",
        "fund_launch": "A new vehicle or GP formation can create early team, platform, and research roles.",
        "lp_commitment": "LP commitments identify active allocators and managers that may expand mandate coverage.",
        "transaction": "Recent transactions identify active investors, portfolio companies, and advisors worth checking for roles.",
        "portfolio_investment": "Portfolio growth can create operating, impact, data, and finance roles at backed companies.",
        "new_office_or_region": "Geographic expansion often creates local hiring and business-development needs.",
        "hiring_signal": "People moves and team buildout are direct prompts to check openings or network.",
        "program_or_grant": "New programs can create fellowship, grant-management, research, or implementation roles.",
        "macro_tailwind": "A market or policy shift can guide search keywords and target sectors.",
    }
    return mapping.get(subtype, mapping["macro_tailwind"])


def suggested_action_for_subtype(subtype: str) -> str:
    """Map a signal type to a workflow action."""
    if subtype in {"fund_close", "fund_launch", "new_office_or_region", "hiring_signal"}:
        return "rescan_org_jobs"
    if subtype in {"transaction", "portfolio_investment", "lp_commitment"}:
        return "add_to_watchlist"
    if subtype == "program_or_grant":
        return "search_linkedin"
    return "review_keywords"


def dedupe_signals(signals: list[Signal]) -> list[Signal]:
    """Deduplicate signals while preserving order."""
    seen: set[str] = set()
    deduped: list[Signal] = []
    for signal in signals:
        if signal.dedup_key in seen:
            continue
        seen.add(signal.dedup_key)
        deduped.append(signal)
    return deduped


def first_xml_text(entry: ET.Element, names: tuple[str, ...]) -> str:
    """Return the first matching child text."""
    for name in names:
        child = entry.find(name)
        if child is not None and child.text:
            return child.text
    return ""


def parse_email_date(value: str) -> datetime | None:
    """Parse common email/RSS datetime strings."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_news_text(value: str) -> str:
    """Normalize newsletter/RSS text."""
    value = unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\u200f", " ").replace("\u034f", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_news_url(value: str) -> str:
    """Normalize newsletter URLs enough for stable dedupe."""
    return clean_news_text(value).replace("&amp;", "&")


def is_content_link(url: str, title: str) -> bool:
    """Heuristic filter for newsletter links that likely represent content."""
    if not url.startswith("http") or not title:
        return False
    lowered_title = title.lower()
    if len(title) < 8 or not re.search(r"[a-zA-Z]", title):
        return False
    blocked_titles = (
        "unsubscribe",
        "manage preferences",
        "view in browser",
        "privacy policy",
        "subscribe",
        "facebook",
        "linkedin",
        "twitter",
        "instagram",
        "read more",
    )
    if any(blocked in lowered_title for blocked in blocked_titles):
        return False
    blocked_url_parts = ("w3.org", "hubfs", "unsubscribe", "preferences")
    return not any(blocked in url.lower() for blocked in blocked_url_parts)


def previous_content_line(lines: list[str], index: int) -> str:
    """Find a likely title just before a URL line."""
    for candidate in reversed(lines[max(0, index - 5) : index]):
        if is_content_link("https://example.org", candidate):
            return candidate
    return ""


def has_any(text: str, needles: tuple[str, ...]) -> bool:
    """Return whether any keyword appears in text."""
    return any(needle in text for needle in needles)
