"""Job-fit scoring contract."""

from __future__ import annotations

import json
from typing import Any

from career_agent.core import CandidateProfile, FitScore, Opportunity
from career_agent.llm import LLMProvider, LLMProviderError


JOB_FIT_SYSTEM_PROMPT = """You are a careful job matching analyst.

Score opportunities for a mission-driven candidate. Be strict: recommend
apply_now only when the role is a strong fit. Return valid JSON only.
"""


def build_job_fit_prompt(
    candidate: CandidateProfile,
    opportunities: list[Opportunity],
) -> str:
    """Build a provider-agnostic job-fit prompt."""
    jobs_payload = [
        {
            "job_title": job.job_title,
            "company": job.company,
            "location": job.location,
            "job_url": job.job_url,
            "description": job.description[:1200],
            "source": job.source,
        }
        for job in opportunities
    ]

    profile_payload = {
        "name": candidate.name,
        "location": candidate.location,
        "education": candidate.education,
        "skills": candidate.skills,
        "target_geography": candidate.target_geography,
        "target_org_types": candidate.target_org_types,
        "preferred_levels": candidate.preferred_levels,
        "excluded_keywords": candidate.excluded_keywords,
    }

    return f"""Candidate profile:
{json.dumps(profile_payload, ensure_ascii=False, indent=2)}

Jobs to score:
{json.dumps(jobs_payload, ensure_ascii=False, indent=2)}

Return a JSON array with one object per job, in the same order:
[
  {{
    "job_url": "same job_url value or null",
    "company": "company",
    "job_title": "job title",
    "total": 0-100,
    "recommended_action": "apply_now" | "review" | "skip",
    "skills_match": 0-25,
    "experience_relevance": 0-25,
    "geography_match": 0-15,
    "org_type_match": 0-15,
    "level_match": 0-10,
    "background_fit": 0-10,
    "match_summary": "2-3 sentence explanation",
    "top_reasons": ["short reason"],
    "risks": ["short risk"],
    "resume_angle": "how to tailor the application"
  }}
]

Legacy action values are not allowed. If a role should be saved for later,
use "review". If a role should be archived, use "skip".
"""


def score_opportunities(
    opportunities: list[Opportunity],
    candidate: CandidateProfile,
    provider: LLMProvider,
) -> list[Opportunity]:
    """Score opportunities with an LLM provider."""
    if not opportunities:
        return []

    prompt = build_job_fit_prompt(candidate, opportunities)
    response = provider.generate(prompt, system=JOB_FIT_SYSTEM_PROMPT)
    payload = response.json_array()

    if len(payload) != len(opportunities):
        raise LLMProviderError(
            f"Expected {len(opportunities)} scored jobs, got {len(payload)}"
        )

    return [
        apply_fit_score(opportunity, fit_score_from_dict(item))
        for opportunity, item in zip(opportunities, payload)
    ]


def score_opportunities_with_fallback(
    opportunities: list[Opportunity],
    candidate: CandidateProfile,
    provider: LLMProvider,
) -> list[Opportunity]:
    """Score opportunities with an LLM provider, falling back locally on failure."""
    try:
        scored = score_opportunities(opportunities, candidate, provider)
        return [
            opportunity.model_copy(
                update={"metadata": {**opportunity.metadata, "scoring_source": "llm"}}
            )
            for opportunity in scored
        ]
    except Exception as exc:
        return [
            fallback_score_opportunity(opportunity, candidate, reason=str(exc))
            for opportunity in opportunities
        ]


def score_opportunity(
    opportunity: Opportunity,
    candidate: CandidateProfile,
    provider: LLMProvider,
) -> Opportunity:
    """Score a single opportunity."""
    return score_opportunities([opportunity], candidate, provider)[0]


def apply_fit_score(opportunity: Opportunity, fit: FitScore) -> Opportunity:
    """Return a copy of an opportunity with a fit score attached."""
    return opportunity.model_copy(update={"fit": fit})


def fallback_score_opportunity(
    opportunity: Opportunity,
    candidate: CandidateProfile,
    *,
    reason: str = "",
) -> Opportunity:
    """Create a deterministic local fit score when provider scoring fails."""
    combined_text = " ".join(
        [
            opportunity.job_title,
            opportunity.company,
            opportunity.location,
            opportunity.description,
        ]
    ).lower()
    skill_hits = [
        skill
        for skill in candidate.skills
        if skill and skill.lower() in combined_text
    ]
    geography_hit = any(
        geo.lower() in opportunity.location.lower() or geo.lower() in combined_text
        for geo in candidate.target_geography
        if geo
    )
    org_type_hit = any(
        org_type.lower() in combined_text
        for org_type in candidate.target_org_types
        if org_type
    )
    level_hit = any(
        level.lower() in combined_text
        for level in candidate.preferred_levels
        if level
    )
    excluded_hit = any(
        keyword.lower() in combined_text
        for keyword in candidate.excluded_keywords
        if keyword
    )

    skills_match = min(25, max(8, len(skill_hits) * 8))
    experience_relevance = (
        22 if has_any(combined_text, ("impact", "finance", "investment")) else 12
    )
    geography_match = 15 if geography_hit else 6
    org_type_match = 15 if org_type_hit else 8
    level_match = 10 if level_hit else 6
    background_fit = 10 if skill_hits and has_any(combined_text, ("impact", "finance")) else 6

    total = (
        skills_match
        + experience_relevance
        + geography_match
        + org_type_match
        + level_match
        + background_fit
    )
    if excluded_hit:
        total = min(total, 45)
    total = _bounded_int(total, 0, 100)

    top_reasons = ["Fallback local scoring used because provider scoring failed."]
    if skill_hits:
        top_reasons.append(f"Keyword overlap: {', '.join(skill_hits[:4])}.")
    if geography_hit:
        top_reasons.append("Location matches target geography.")
    if org_type_hit:
        top_reasons.append("Role language matches target organization types.")

    risks = []
    if reason:
        risks.append(f"Provider scoring failed: {reason[:160]}")
    if not skill_hits:
        risks.append("Few explicit skill keywords found in the available description.")
    if excluded_hit:
        risks.append("Excluded seniority keyword detected.")

    fit = FitScore(
        total=total,
        recommended_action=normalize_action(None, total),
        skills_match=skills_match,
        experience_relevance=experience_relevance,
        geography_match=geography_match,
        org_type_match=org_type_match,
        level_match=level_match,
        background_fit=background_fit,
        match_summary=(
            f"Local fallback score for {opportunity.job_title} at {opportunity.company}. "
            "Review before acting because the LLM scorer did not complete."
        ),
        top_reasons=top_reasons,
        risks=risks,
        resume_angle=(
            f"Position {candidate.name} around "
            f"{', '.join(skill_hits[:3]) if skill_hits else 'mission-driven analysis'} "
            f"for {opportunity.company}."
        ),
    )
    metadata = {
        **opportunity.metadata,
        "scoring_source": "fallback",
    }
    if reason:
        metadata["scoring_fallback_reason"] = reason[:240]
    return opportunity.model_copy(update={"fit": fit, "metadata": metadata})


def fit_score_from_dict(item: dict[str, Any]) -> FitScore:
    """Normalize provider JSON into a `FitScore` model."""
    total = _bounded_int(item.get("total", item.get("fit_score", 0)), 0, 100)

    return FitScore(
        total=total,
        recommended_action=normalize_action(item.get("recommended_action"), total),
        skills_match=_bounded_optional_int(item.get("skills_match"), 0, 25),
        experience_relevance=_bounded_optional_int(item.get("experience_relevance"), 0, 25),
        geography_match=_bounded_optional_int(item.get("geography_match"), 0, 15),
        org_type_match=_bounded_optional_int(item.get("org_type_match"), 0, 15),
        level_match=_bounded_optional_int(item.get("level_match"), 0, 10),
        background_fit=_bounded_optional_int(item.get("background_fit"), 0, 10),
        match_summary=str(item.get("match_summary", "")),
        top_reasons=_coerce_string_list(item.get("top_reasons")),
        risks=_coerce_string_list(item.get("risks")),
        resume_angle=str(item.get("resume_angle", "")),
    )


def normalize_action(value: Any, total: int) -> str:
    """Normalize current and legacy action labels into v0.1 actions."""
    if value is None:
        if total >= 80:
            return "apply_now"
        if total >= 60:
            return "review"
        return "skip"

    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "apply": "apply_now",
        "apply_now": "apply_now",
        "review": "review",
        "save": "review",
        "save_for_later": "review",
        "save_for_weekly": "review",
        "skip": "skip",
        "archive": "skip",
        "archived": "skip",
    }
    action = mapping.get(normalized)
    if action:
        return action

    return normalize_action(None, total)


def _coerce_string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _bounded_optional_int(value: Any, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    return _bounded_int(value, minimum, maximum)


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def has_any(text: str, needles: tuple[str, ...]) -> bool:
    """Return whether any keyword appears in text."""
    return any(needle in text for needle in needles)
