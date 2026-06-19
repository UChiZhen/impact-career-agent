from career_agent.llm import MockLLMProvider
from career_agent.sources.career_extraction import (
    build_career_page_extraction_prompt,
    extract_opportunities_from_snapshot,
    opportunities_from_extraction_payload,
)
from career_agent.sources.career_pages import CareerPageSnapshot
from career_agent.sources.opportunities import Organization


def test_build_career_page_extraction_prompt_includes_org_context():
    snapshot = make_snapshot()

    prompt = build_career_page_extraction_prompt(snapshot)

    assert "Example Impact Fund" in prompt
    assert "https://example.org/careers" in prompt
    assert "Analyst role" in prompt


def test_extract_opportunities_from_snapshot_with_mock_provider():
    snapshot = make_snapshot()
    provider = MockLLMProvider(
        default_response="""
        {
          "jobs": [
            {
              "job_title": "Impact Investment Analyst",
              "company": "Example Impact Fund",
              "location": "Chicago, IL",
              "job_url": "https://example.org/jobs/analyst",
              "post_date": "2026-06-18",
              "description": "Analyze impact investing opportunities."
            }
          ],
          "page_summary": "One analyst role is visible."
        }
        """
    )

    opportunities = extract_opportunities_from_snapshot(snapshot, provider)

    assert len(opportunities) == 1
    assert opportunities[0].source == "career_page"
    assert opportunities[0].source_detail == "organization_watchlist"
    assert opportunities[0].company == "Example Impact Fund"
    assert opportunities[0].job_title == "Impact Investment Analyst"
    assert opportunities[0].location == "Chicago, IL"
    assert opportunities[0].job_url == "https://example.org/jobs/analyst"
    assert opportunities[0].origin_url == "https://example.org/careers"
    assert opportunities[0].metadata["career_page_hash"] == "abc123"
    assert provider.calls


def test_extraction_payload_defaults_company_location_and_url():
    snapshot = make_snapshot()
    opportunities = opportunities_from_extraction_payload(
        snapshot,
        {
            "jobs": [
                {
                    "job_title": "Portfolio Fellow",
                },
                {
                    "job_title": "",
                },
            ]
        },
    )

    assert len(opportunities) == 1
    assert opportunities[0].company == "Example Impact Fund"
    assert opportunities[0].location == "United States"
    assert opportunities[0].job_url == "https://example.org/careers"


def test_failed_snapshot_returns_no_opportunities():
    snapshot = make_snapshot(success=False, raw_text="")
    provider = MockLLMProvider(default_response='{"jobs": [{"job_title": "Analyst"}]}')

    assert extract_opportunities_from_snapshot(snapshot, provider) == []
    assert provider.calls == []


def make_snapshot(*, success: bool = True, raw_text: str = "Analyst role") -> CareerPageSnapshot:
    return CareerPageSnapshot(
        organization=Organization(
            name="Example Impact Fund",
            career_url="https://example.org/careers",
            location="United States",
            industry="impact investing",
            tags=("climate",),
        ),
        url="https://example.org/careers",
        success=success,
        raw_text=raw_text,
        content_hash="abc123",
        char_count=len(raw_text),
        token_estimate=len(raw_text) // 4,
        fetched_at="2026-06-18T12:00:00+00:00",
    )
