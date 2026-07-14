"""Fetch and validate full job descriptions for application drafting."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import re
import time
from typing import Any, Callable, Literal
from urllib.parse import urlparse, urlunparse

from career_agent.core import Opportunity


JDEnrichmentStatus = Literal["existing", "enriched", "needs_jd", "removed"]

_RESPONSIBILITY_MARKERS = (
    "responsibilities",
    "key responsibilities",
    "about the role",
    "what you will do",
    "what you will be doing",
    "what you'll do",
    "what you'll be doing",
    "your role",
    "the role",
    "duties",
    "you will",
)
_QUALIFICATION_MARKERS = (
    "qualifications",
    "requirements",
    "what you will bring",
    "what you'll bring",
    "you have",
    "experience",
    "skills",
)
_BLOCKED_PAGE_MARKERS = (
    "access denied",
    "captcha",
    "enable javascript",
    "page not found",
    "sign in to continue",
    "temporarily unavailable",
)
_USER_AGENTS = (
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
)


@dataclass(frozen=True)
class JobDescriptionQuality:
    """Quality decision for text that may be used to tailor an application."""

    accepted: bool
    char_count: int
    word_count: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class JobDescriptionFetchResult:
    """Raw result from fetching and extracting one job page."""

    text: str = ""
    source: str = ""
    status: Literal["success", "removed", "failed"] = "failed"
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success" and bool(self.text)


@dataclass(frozen=True)
class JobDescriptionEnrichmentResult:
    """An opportunity plus the audit state of its full-JD enrichment."""

    opportunity: Opportunity
    status: JDEnrichmentStatus
    source: str = ""
    content_hash: str = ""
    quality: JobDescriptionQuality = field(
        default_factory=lambda: JobDescriptionQuality(False, 0, 0, ("missing_description",))
    )
    error: str = ""

    @property
    def ready_for_application(self) -> bool:
        return self.status in {"existing", "enriched"} and self.quality.accepted


def assess_job_description(
    text: str,
    *,
    min_chars: int = 800,
    min_words: int = 100,
) -> JobDescriptionQuality:
    """Decide whether extracted text is complete enough for application drafting."""
    normalized = normalize_description_text(text)
    lowered = normalized.lower()
    char_count = len(normalized)
    word_count = len(re.findall(r"\b[\w'-]+\b", normalized))
    reasons = []

    if not normalized:
        reasons.append("missing_description")
    if char_count < min_chars:
        reasons.append("description_too_short")
    if word_count < min_words:
        reasons.append("too_few_words")
    if any(marker in lowered for marker in _BLOCKED_PAGE_MARKERS):
        reasons.append("blocked_or_error_page")
    has_responsibility_signals = any(marker in lowered for marker in _RESPONSIBILITY_MARKERS)
    has_qualification_signals = any(marker in lowered for marker in _QUALIFICATION_MARKERS)
    if not has_responsibility_signals and not has_qualification_signals:
        reasons.append("missing_role_content_signals")

    return JobDescriptionQuality(
        accepted=not reasons,
        char_count=char_count,
        word_count=word_count,
        reasons=tuple(reasons),
    )


def enrich_job_description(
    opportunity: Opportunity,
    *,
    fetcher: Callable[[str], JobDescriptionFetchResult] | None = None,
) -> JobDescriptionEnrichmentResult:
    """Use existing text first, then fetch the job URL when enrichment is needed."""
    existing_quality = assess_job_description(opportunity.description)
    if existing_quality.accepted:
        return build_enrichment_result(
            opportunity,
            status="existing",
            source="source_description",
            quality=existing_quality,
        )

    if not opportunity.job_url:
        return build_enrichment_result(
            opportunity,
            status="needs_jd",
            quality=existing_quality,
            error="Opportunity has no job URL for enrichment.",
        )

    fetch_result = (fetcher or fetch_job_description)(opportunity.job_url)
    if fetch_result.status == "removed":
        return build_enrichment_result(
            opportunity,
            status="removed",
            source=fetch_result.source,
            quality=existing_quality,
            error=fetch_result.error,
        )
    if not fetch_result.ok:
        return build_enrichment_result(
            opportunity,
            status="needs_jd",
            source=fetch_result.source,
            quality=existing_quality,
            error=fetch_result.error or "Job description fetch failed.",
        )

    quality = assess_job_description(fetch_result.text)
    if not quality.accepted:
        return build_enrichment_result(
            opportunity,
            status="needs_jd",
            source=fetch_result.source,
            quality=quality,
            error="Fetched page did not contain a complete job description.",
        )

    metadata = {
        **opportunity.metadata,
        "jd_status": "enriched",
        "jd_source": fetch_result.source,
        "jd_char_count": str(quality.char_count),
        "jd_content_hash": description_hash(fetch_result.text),
    }
    enriched = opportunity.model_copy(
        update={
            "description": normalize_description_text(fetch_result.text),
            "metadata": metadata,
        }
    )
    return JobDescriptionEnrichmentResult(
        opportunity=enriched,
        status="enriched",
        source=fetch_result.source,
        content_hash=metadata["jd_content_hash"],
        quality=quality,
    )


def build_enrichment_result(
    opportunity: Opportunity,
    *,
    status: JDEnrichmentStatus,
    quality: JobDescriptionQuality,
    source: str = "",
    error: str = "",
) -> JobDescriptionEnrichmentResult:
    """Attach enrichment audit metadata without changing the source description."""
    content_hash = description_hash(opportunity.description) if opportunity.description else ""
    metadata = {
        **opportunity.metadata,
        "jd_status": status,
        "jd_source": source,
        "jd_char_count": str(quality.char_count),
        "jd_content_hash": content_hash,
    }
    updated = opportunity.model_copy(update={"metadata": metadata})
    return JobDescriptionEnrichmentResult(
        opportunity=updated,
        status=status,
        source=source,
        content_hash=content_hash,
        quality=quality,
        error=error,
    )


def fetch_job_description(
    url: str,
    *,
    timeout_seconds: int = 15,
    max_chars: int = 12_000,
    max_retries: int = 2,
    request_get: Callable[..., Any] | None = None,
    retry_sleep: Callable[[float], None] = time.sleep,
) -> JobDescriptionFetchResult:
    """Fetch a public job page and extract JSON-LD or article-like page text."""
    normalized_url = normalize_job_url(url)
    if not is_safe_public_url(normalized_url):
        return JobDescriptionFetchResult(
            status="failed",
            error="Job URL must be a public HTTP(S) URL.",
        )

    if request_get is None:
        try:
            import requests
        except ImportError:
            return JobDescriptionFetchResult(
                status="failed",
                error=(
                    "Job-description enrichment requires optional career-page dependencies. "
                    "Install with `pip install 'impact-career-agent[career-pages]'`."
                ),
            )
        request_get = requests.get

    candidates: list[tuple[str, str, bool]] = []
    guest_url = linkedin_guest_job_url(normalized_url)
    if guest_url:
        candidates.append(("linkedin_guest_page", guest_url, True))
    candidates.append(("job_url", normalized_url, False))

    errors = []
    best_incomplete: JobDescriptionFetchResult | None = None
    for source, candidate_url, allow_html_fragment in candidates:
        result = fetch_single_job_page(
            candidate_url,
            source=source,
            allow_html_fragment=allow_html_fragment,
            timeout_seconds=timeout_seconds,
            max_chars=max_chars,
            max_retries=max_retries,
            request_get=request_get,
            retry_sleep=retry_sleep,
        )
        if result.ok:
            if assess_job_description(result.text).accepted:
                return result
            if best_incomplete is None or len(result.text) > len(best_incomplete.text):
                best_incomplete = result
            errors.append(f"{source}: extracted text was incomplete")
            continue
        if result.status == "removed" and source == "job_url":
            return result
        if result.error:
            errors.append(f"{source}: {result.error}")

    if best_incomplete:
        return best_incomplete
    return JobDescriptionFetchResult(
        status="failed",
        source="job_url",
        error="; ".join(errors) or "Job description fetch failed.",
    )


def fetch_single_job_page(
    url: str,
    *,
    source: str,
    allow_html_fragment: bool,
    timeout_seconds: int,
    max_chars: int,
    max_retries: int,
    request_get: Callable[..., Any],
    retry_sleep: Callable[[float], None],
) -> JobDescriptionFetchResult:
    """Fetch and extract one candidate URL in the enrichment chain."""
    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            response = request_get(
                url,
                headers={"User-Agent": _USER_AGENTS[attempt % len(_USER_AGENTS)]},
                timeout=timeout_seconds,
                allow_redirects=True,
            )
            status_code = int(getattr(response, "status_code", 200))
            if status_code in {404, 410}:
                return JobDescriptionFetchResult(
                    status="removed",
                    source=source,
                    error=f"Job posting returned HTTP {status_code}.",
                )
            if status_code >= 400:
                last_error = f"Job posting returned HTTP {status_code}."
                if status_code in {403, 429, 500, 502, 503, 504} and attempt < max_retries:
                    retry_sleep(1.0 + attempt)
                    continue
                return JobDescriptionFetchResult(
                    status="failed",
                    source=source,
                    error=last_error,
                )

            html = str(getattr(response, "text", ""))
            extracted_source = source
            text = extract_jobposting_json_ld(html)
            if text:
                extracted_source = f"{source}_json_ld"
            else:
                text = extract_page_description(html)
            if not text and allow_html_fragment:
                text = html_fragment_to_text(html)
            if text:
                return JobDescriptionFetchResult(
                    text=normalize_description_text(text)[:max_chars],
                    source=extracted_source,
                    status="success",
                )
            return JobDescriptionFetchResult(
                status="failed",
                source=source,
                error="No job-description text could be extracted from the page.",
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries:
                retry_sleep(1.0 + attempt)
                continue

    return JobDescriptionFetchResult(status="failed", source=source, error=last_error)


def extract_jobposting_json_ld(html: str) -> str:
    """Extract descriptions from schema.org JobPosting JSON-LD blocks."""
    pattern = re.compile(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        try:
            payload = json.loads(unescape(match.group(1)).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in iter_json_ld_objects(payload):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" not in types:
                continue
            description = item.get("description") or ""
            if description:
                return html_fragment_to_text(str(description))
    return ""


def iter_json_ld_objects(payload: Any):
    """Yield objects from common JSON-LD list and graph containers."""
    if isinstance(payload, list):
        for item in payload:
            yield from iter_json_ld_objects(item)
    elif isinstance(payload, dict):
        yield payload
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from iter_json_ld_objects(item)


def extract_page_description(html: str) -> str:
    """Extract the main visible text through the optional trafilatura dependency."""
    try:
        import trafilatura
    except ImportError:
        return ""
    return (
        trafilatura.extract(
            html,
            include_links=False,
            include_tables=True,
            include_comments=False,
        )
        or ""
    )


def normalize_job_url(url: str) -> str:
    """Normalize LinkedIn redirect-style URLs and remove tracking parameters."""
    parsed = urlparse(url.strip())
    if "linkedin.com" not in parsed.netloc.lower():
        return url.strip()
    path = parsed.path.replace("/comm/", "/")
    return urlunparse((parsed.scheme or "https", "www.linkedin.com", path, "", "", ""))


def linkedin_guest_job_url(url: str) -> str:
    """Build LinkedIn's public guest job endpoint from a posting URL."""
    parsed = urlparse(url)
    if "linkedin.com" not in parsed.netloc.lower():
        return ""
    job_ids = re.findall(r"\d{6,}", parsed.path)
    if not job_ids:
        return ""
    return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_ids[-1]}"


def is_safe_public_url(url: str) -> bool:
    """Reject obvious local/private destinations before a hosted fetch is attempted."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def description_hash(text: str) -> str:
    """Return a stable hash for detecting meaningful JD changes."""
    normalized = normalize_description_text(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def normalize_description_text(text: str) -> str:
    """Normalize extracted text while retaining readable paragraph boundaries."""
    decoded = unescape(text or "").replace("\u2018", "'").replace("\u2019", "'")
    lines = [re.sub(r"\s+", " ", line).strip() for line in decoded.splitlines()]
    return "\n".join(line for line in lines if line).strip()


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def html_fragment_to_text(value: str) -> str:
    """Convert a JSON-LD HTML description into plain text."""
    parser = _HTMLTextExtractor()
    parser.feed(unescape(value))
    return "\n".join(parser.parts)
