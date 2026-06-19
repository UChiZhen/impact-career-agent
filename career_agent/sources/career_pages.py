"""Live career-page source connector boundary.

This module is the future home for the working Job Radar scraper currently in:

- `jobsearch/job-radar/src/scraper.py`
- `jobsearch/job-radar/src/cache.py`
- `jobsearch/job-radar/src/job_extractor.py`

v0.1 defines the connector boundary without making network calls. The fixture
source in `career_agent.sources.opportunities` remains the credential-free demo
path until the live scraper is ported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import md5
from html.parser import HTMLParser
import re
from urllib.request import Request, urlopen

from career_agent.core import Opportunity
from career_agent.sources.opportunities import Organization


DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DEFAULT_MAX_TEXT_CHARS = 12_000


@dataclass(frozen=True)
class CareerPageSourceConfig:
    """Configuration for target-organization career-page scanning."""

    organizations: tuple[Organization, ...]
    timeout_seconds: int = 30
    max_retries: int = 3
    use_content_cache: bool = True
    user_agent: str = DEFAULT_USER_AGENT
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS


@dataclass(frozen=True)
class CareerPageSnapshot:
    """Fetched and normalized career-page text before job extraction."""

    organization: Organization
    url: str
    success: bool
    raw_text: str = ""
    content_hash: str = ""
    char_count: int = 0
    token_estimate: int = 0
    fetched_at: str = ""
    error: str | None = None


class CareerPageSource:
    """Live source for organization watchlist career pages."""

    source_name = "career_page"

    def __init__(self, config: CareerPageSourceConfig):
        self.config = config

    def fetch(self) -> list[Opportunity]:
        """Fetch opportunities from configured career pages.

        Porting target:
        1. Fetch each `Organization.career_url`.
        2. Use content hashing to avoid unnecessary LLM extraction.
        3. Extract visible jobs.
        4. Normalize each result into `Opportunity(source="career_page")`.
        """
        raise NotImplementedError("Live career-page scraping will be ported after v0.1 fixtures")

    def fetch_pages(self) -> list[CareerPageSnapshot]:
        """Fetch configured career pages and return extraction-ready snapshots."""
        return [self.fetch_page(organization) for organization in self.config.organizations]

    def fetch_page(self, organization: Organization) -> CareerPageSnapshot:
        """Fetch one organization's career page and extract visible text."""
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            html = fetch_url_text(
                organization.career_url,
                timeout_seconds=self.config.timeout_seconds,
                user_agent=self.config.user_agent,
            )
            extracted_text = truncate_text(
                extract_page_text(html),
                max_chars=self.config.max_text_chars,
            )
            if not extracted_text:
                return CareerPageSnapshot(
                    organization=organization,
                    url=organization.career_url,
                    success=False,
                    fetched_at=fetched_at,
                    error="No text could be extracted from page.",
                )

            content_hash = compute_content_hash(extracted_text)
            return CareerPageSnapshot(
                organization=organization,
                url=organization.career_url,
                success=True,
                raw_text=extracted_text,
                content_hash=content_hash,
                char_count=len(extracted_text),
                token_estimate=len(extracted_text) // 4,
                fetched_at=fetched_at,
            )
        except Exception as exc:
            return CareerPageSnapshot(
                organization=organization,
                url=organization.career_url,
                success=False,
                fetched_at=fetched_at,
                error=str(exc),
            )


def fetch_url_text(url: str, *, timeout_seconds: int, user_agent: str) -> str:
    """Fetch URL HTML using requests when available, urllib otherwise."""
    try:
        import requests
    except ImportError:
        request = Request(url, headers={"User-Agent": user_agent})
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")

    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    response.raise_for_status()
    return response.text


def extract_page_text(html: str) -> str:
    """Extract readable text from a career page.

    Prefer `trafilatura` when installed, then fall back to a small stdlib HTML
    text extractor so tests and demos remain dependency-light.
    """
    try:
        import trafilatura
    except ImportError:
        return extract_text_with_html_parser(html)

    extracted = trafilatura.extract(
        html,
        include_links=True,
        include_tables=True,
        include_comments=False,
        output_format="txt",
    )
    if extracted:
        return clean_text(extracted)
    return extract_text_with_html_parser(html)


class _VisibleTextParser(HTMLParser):
    """Small fallback visible text extractor."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        if data.strip():
            self.chunks.append(data)


def extract_text_with_html_parser(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return clean_text("\n".join(parser.chunks))


def clean_text(value: str) -> str:
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def compute_content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return md5(normalized.encode("utf-8")).hexdigest()


def truncate_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.8:
        truncated = truncated[: last_period + 1]
    return f"{truncated}\n\n[Content truncated...]"
