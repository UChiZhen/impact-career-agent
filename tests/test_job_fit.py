import json

import pytest

from career_agent.core import CandidateProfile, Opportunity
from career_agent.llm import LLMProviderError, MockLLMProvider
from career_agent.scoring import (
    build_job_fit_prompt,
    fallback_score_opportunity,
    fit_score_from_dict,
    normalize_action,
    score_opportunities_with_fallback,
    score_opportunity,
)


def demo_candidate():
    return CandidateProfile(
        name="Jane Doe",
        location="Chicago, IL",
        education=["Master of Public Policy"],
        skills=["Python", "SQL", "impact measurement", "financial analysis"],
        target_geography=["United States"],
        target_org_types=["impact fund"],
        preferred_levels=["analyst", "associate"],
        excluded_keywords=["senior", "director"],
    )


def demo_opportunity():
    return Opportunity(
        source="demo",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        location="Chicago, IL",
        job_url="https://example.org/jobs/impact-investment-analyst",
        description="Python SQL impact finance analyst role.",
    )


def test_normalize_action_maps_legacy_values():
    assert normalize_action("save_for_weekly", 72) == "review"
    assert normalize_action("archive", 20) == "skip"
    assert normalize_action(None, 86) == "apply_now"


def test_fit_score_from_dict_clamps_dimensions_and_coerces_lists():
    fit = fit_score_from_dict(
        {
            "fit_score": 120,
            "recommended_action": "save_for_weekly",
            "skills_match": 99,
            "top_reasons": "Strong impact finance overlap",
        }
    )

    assert fit.total == 100
    assert fit.recommended_action == "review"
    assert fit.skills_match == 25
    assert fit.top_reasons == ["Strong impact finance overlap"]


def test_build_prompt_contains_candidate_and_job_context():
    prompt = build_job_fit_prompt(demo_candidate(), [demo_opportunity()])

    assert "Jane Doe" in prompt
    assert "Example Impact Fund" in prompt
    assert "apply_now" in prompt
    assert "Legacy action values are not allowed" in prompt


def test_score_opportunity_with_mock_provider():
    payload = [
        {
            "job_url": "https://example.org/jobs/impact-investment-analyst",
            "company": "Example Impact Fund",
            "job_title": "Impact Investment Analyst",
            "total": 84,
            "recommended_action": "apply_now",
            "skills_match": 25,
            "experience_relevance": 22,
            "geography_match": 15,
            "org_type_match": 12,
            "level_match": 10,
            "background_fit": 10,
            "match_summary": "Strong fit for the demo candidate.",
            "top_reasons": ["Matches Python and impact finance."],
            "risks": [],
            "resume_angle": "Lead with impact finance analytics.",
        }
    ]
    provider = MockLLMProvider(default_response=json.dumps(payload))

    scored = score_opportunity(demo_opportunity(), demo_candidate(), provider)

    assert scored.fit is not None
    assert scored.fit.total == 84
    assert scored.fit.recommended_action == "apply_now"
    assert scored.fit.resume_angle == "Lead with impact finance analytics."


def test_score_opportunity_rejects_wrong_number_of_results():
    provider = MockLLMProvider(default_response="[]")

    with pytest.raises(LLMProviderError, match="Expected 1 scored jobs"):
        score_opportunity(demo_opportunity(), demo_candidate(), provider)


def test_fallback_score_opportunity_adds_fit_and_metadata():
    scored = fallback_score_opportunity(
        demo_opportunity(),
        demo_candidate(),
        reason="provider unavailable",
    )

    assert scored.fit is not None
    assert scored.fit.total > 0
    assert scored.fit.recommended_action in {"apply_now", "review", "skip"}
    assert scored.metadata["scoring_source"] == "fallback"
    assert "provider unavailable" in scored.metadata["scoring_fallback_reason"]


def test_score_opportunities_with_fallback_marks_llm_success():
    payload = [
        {
            "total": 84,
            "recommended_action": "apply_now",
            "match_summary": "Strong fit.",
        }
    ]
    provider = MockLLMProvider(default_response=json.dumps(payload))

    scored = score_opportunities_with_fallback(
        [demo_opportunity()],
        demo_candidate(),
        provider,
    )

    assert scored[0].fit.total == 84
    assert scored[0].metadata["scoring_source"] == "llm"


def test_score_opportunities_with_fallback_handles_provider_shape_failure():
    provider = MockLLMProvider(default_response="[]")

    scored = score_opportunities_with_fallback(
        [demo_opportunity()],
        demo_candidate(),
        provider,
    )

    assert scored[0].fit is not None
    assert scored[0].metadata["scoring_source"] == "fallback"
    assert "Expected 1 scored jobs" in scored[0].metadata["scoring_fallback_reason"]
