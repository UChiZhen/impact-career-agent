from career_agent.core import Opportunity
from career_agent.sources.job_descriptions import (
    JobDescriptionFetchResult,
    assess_job_description,
    enrich_job_description,
    extract_jobposting_json_ld,
    fetch_job_description,
    is_safe_public_url,
    linkedin_guest_job_url,
    normalize_job_url,
)


COMPLETE_JD = """
The Role
Key Responsibilities
You will analyze investments, build financial models, prepare investment committee
materials, conduct market research, support due diligence, and monitor portfolio
performance. You will work with partners across climate finance, community development,
and impact measurement. You will communicate findings clearly and help the team evaluate
new opportunities. The role includes ownership of analytical workstreams, coordination
with external advisers, and preparation of concise recommendations for senior leaders.

Qualifications
The successful candidate has experience in finance, consulting, investing, research, or
another analytical environment. Requirements include strong Excel and financial modeling
skills, clear writing, sound judgment, attention to detail, and comfort working with data.
Experience with Python, SQL, impact investing, development finance, or climate finance is
helpful. You should be able to manage several projects, explain complex analysis, work
collaboratively, and learn unfamiliar sectors quickly. We value curiosity, integrity,
initiative, and a demonstrated commitment to mission-driven work and inclusive economic
growth. Candidates should be comfortable presenting recommendations and improving tools.
"""


class FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code


def make_opportunity(*, description: str = "", job_url: str | None = "https://example.org/job"):
    return Opportunity(
        source="linkedin_email",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        job_url=job_url,
        description=description,
    )


def test_assess_job_description_accepts_complete_role_text():
    quality = assess_job_description(COMPLETE_JD)

    assert quality.accepted is True
    assert quality.char_count >= 800
    assert quality.word_count >= 100
    assert quality.reasons == ()


def test_assess_job_description_rejects_snippets_and_block_pages():
    short = assess_job_description("Analyst role supporting investments.")
    blocked = assess_job_description("Access denied. Enable JavaScript. " + COMPLETE_JD)

    assert short.accepted is False
    assert "description_too_short" in short.reasons
    assert "missing_role_content_signals" in short.reasons
    assert blocked.accepted is False
    assert "blocked_or_error_page" in blocked.reasons


def test_enrichment_keeps_an_existing_complete_description_without_fetching():
    def unexpected_fetch(_url):
        raise AssertionError("fetcher should not run")

    result = enrich_job_description(
        make_opportunity(description=COMPLETE_JD),
        fetcher=unexpected_fetch,
    )

    assert result.status == "existing"
    assert result.ready_for_application is True
    assert result.opportunity.metadata["jd_source"] == "source_description"


def test_enrichment_replaces_a_snippet_with_fetched_full_jd():
    result = enrich_job_description(
        make_opportunity(description="Short alert snippet."),
        fetcher=lambda _url: JobDescriptionFetchResult(
            text=COMPLETE_JD,
            source="job_url_json_ld",
            status="success",
        ),
    )

    assert result.status == "enriched"
    assert result.ready_for_application is True
    assert result.opportunity.description.startswith("The Role")
    assert result.opportunity.metadata["jd_status"] == "enriched"
    assert result.opportunity.metadata["jd_content_hash"] == result.content_hash


def test_enrichment_marks_failed_or_incomplete_fetch_as_needs_jd():
    failed = enrich_job_description(
        make_opportunity(),
        fetcher=lambda _url: JobDescriptionFetchResult(
            status="failed",
            source="job_url",
            error="blocked",
        ),
    )
    incomplete = enrich_job_description(
        make_opportunity(),
        fetcher=lambda _url: JobDescriptionFetchResult(
            text="Analyst role.",
            source="job_url_page_text",
            status="success",
        ),
    )

    assert failed.status == "needs_jd"
    assert failed.ready_for_application is False
    assert failed.error == "blocked"
    assert incomplete.status == "needs_jd"
    assert "description_too_short" in incomplete.quality.reasons


def test_enrichment_marks_removed_job_pages():
    result = enrich_job_description(
        make_opportunity(),
        fetcher=lambda _url: JobDescriptionFetchResult(
            status="removed",
            source="job_url",
            error="HTTP 404",
        ),
    )

    assert result.status == "removed"
    assert result.ready_for_application is False


def test_extract_jobposting_json_ld_uses_full_description():
    html = f"""
    <script type="application/ld+json">
      {{"@context":"https://schema.org","@type":"JobPosting",
        "description": {COMPLETE_JD.replace(chr(10), '<br>').__repr__()} }}
    </script>
    """.replace("'", '"')

    extracted = extract_jobposting_json_ld(html)

    assert "Key Responsibilities" in extracted
    assert "Qualifications" in extracted


def test_fetch_job_description_prefers_json_ld():
    description = COMPLETE_JD.replace("\n", "<br>")
    payload = {"@context": "https://schema.org", "@type": "JobPosting", "description": description}
    html = f'<script type="application/ld+json">{__import__("json").dumps(payload)}</script>'

    result = fetch_job_description(
        "https://example.org/jobs/analyst",
        request_get=lambda *args, **kwargs: FakeResponse(html),
        retry_sleep=lambda _seconds: None,
    )

    assert result.ok is True
    assert result.source == "job_url_json_ld"
    assert "Qualifications" in result.text


def test_fetch_job_description_treats_404_as_removed():
    result = fetch_job_description(
        "https://example.org/jobs/missing",
        request_get=lambda *args, **kwargs: FakeResponse(status_code=404),
        retry_sleep=lambda _seconds: None,
    )

    assert result.status == "removed"


def test_fetch_job_description_uses_linkedin_guest_fragment_first():
    calls = []

    def request_get(url, **_kwargs):
        calls.append(url)
        return FakeResponse(f"<section><h2>About the role</h2><p>{COMPLETE_JD}</p></section>")

    result = fetch_job_description(
        "https://www.linkedin.com/jobs/view/example-role-1234567890/",
        request_get=request_get,
        retry_sleep=lambda _seconds: None,
    )

    assert result.ok is True
    assert result.source == "linkedin_guest_page"
    assert calls == ["https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1234567890"]


def test_linkedin_guest_failure_falls_back_to_normalized_job_page():
    calls = []
    payload = {"@type": "JobPosting", "description": COMPLETE_JD}

    def request_get(url, **_kwargs):
        calls.append(url)
        if "jobs-guest" in url:
            return FakeResponse(status_code=500)
        return FakeResponse(
            f'<script type="application/ld+json">{__import__("json").dumps(payload)}</script>'
        )

    result = fetch_job_description(
        "https://uk.linkedin.com/comm/jobs/view/1234567890/?trackingId=secret",
        max_retries=0,
        request_get=request_get,
        retry_sleep=lambda _seconds: None,
    )

    assert result.ok is True
    assert result.source == "job_url_json_ld"
    assert calls == [
        "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1234567890",
        "https://www.linkedin.com/jobs/view/1234567890/",
    ]


def test_incomplete_linkedin_guest_text_falls_back_to_normal_job_page():
    calls = []
    payload = {"@type": "JobPosting", "description": COMPLETE_JD}

    def request_get(url, **_kwargs):
        calls.append(url)
        if "jobs-guest" in url:
            return FakeResponse("<p>Sign in to view this job.</p>")
        return FakeResponse(
            f'<script type="application/ld+json">{__import__("json").dumps(payload)}</script>'
        )

    result = fetch_job_description(
        "https://www.linkedin.com/jobs/view/1234567890/",
        max_retries=0,
        request_get=request_get,
        retry_sleep=lambda _seconds: None,
    )

    assert result.ok is True
    assert result.source == "job_url_json_ld"
    assert len(calls) == 2


def test_linkedin_url_normalization_and_private_url_rejection():
    assert normalize_job_url(
        "https://uk.linkedin.com/comm/jobs/view/123/?trackingId=secret"
    ) == "https://www.linkedin.com/jobs/view/123/"
    assert linkedin_guest_job_url(
        "https://www.linkedin.com/jobs/view/example-role-1234567890/"
    ) == "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1234567890"
    assert is_safe_public_url("https://example.org/jobs/analyst") is True
    assert is_safe_public_url("http://127.0.0.1/private") is False
    assert is_safe_public_url("http://localhost/private") is False
