import json

import pytest

import career_agent.scoring.job_fit as job_fit_module
from career_agent.core import CandidateProfile, FitScore, Opportunity
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


def test_build_prompt_allows_longer_description_for_final_rescore():
    opportunity = demo_opportunity().model_copy(update={"description": "A" * 7000})

    prompt = build_job_fit_prompt(
        demo_candidate(),
        [opportunity],
        description_limit=6000,
    )

    assert "A" * 6000 in prompt
    assert "A" * 6001 not in prompt


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
    assert "Review before acting" not in scored.fit.match_summary
    assert "skills: Python, SQL" in scored.fit.match_summary


def test_fallback_seniority_exclusion_only_applies_to_job_title():
    junior_role = demo_opportunity().model_copy(
        update={"description": "Work with senior leaders. Python SQL impact finance."}
    )
    senior_role = junior_role.model_copy(update={"job_title": "Senior Investment Analyst"})

    junior_scored = fallback_score_opportunity(junior_role, demo_candidate())
    senior_scored = fallback_score_opportunity(senior_role, demo_candidate())

    assert junior_scored.fit.total > 45
    assert senior_scored.fit.total <= 45
    assert "Excluded seniority keyword detected." in senior_scored.fit.risks


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


def test_score_opportunities_with_fallback_isolates_failed_batch(monkeypatch):
    opportunities = [
        demo_opportunity().model_copy(update={"job_title": f"Analyst {index}"})
        for index in range(3)
    ]
    batch_sizes = []

    def fake_score(batch, candidate, provider, *, description_limit):
        batch_sizes.append(len(batch))
        if len(batch) == 1:
            raise LLMProviderError("second batch failed")
        return [
            opportunity.model_copy(
                update={"fit": FitScore(total=84, recommended_action="apply_now")}
            )
            for opportunity in batch
        ]

    monkeypatch.setattr(job_fit_module, "score_opportunities", fake_score)

    scored = score_opportunities_with_fallback(
        opportunities,
        demo_candidate(),
        MockLLMProvider(),
        batch_size=2,
    )

    assert batch_sizes == [2, 1]
    assert [item.metadata["scoring_source"] for item in scored] == [
        "llm",
        "llm",
        "fallback",
    ]
