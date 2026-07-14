"""Credential-free demo workflow."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from career_agent.core import CandidateProfile, FitScore, Opportunity, Signal
from career_agent.sources import (
    CareerPageFixtureSource,
    LinkedInEmailFixtureSource,
    LinkedInSearchFixtureSource,
    fetch_all_opportunities,
)


DEFAULT_CONFIG_PATH = Path("examples/demo_config.yaml")


def load_demo_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load a YAML demo configuration file."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_candidate_profile(path: Path) -> CandidateProfile:
    """Load the fictional demo candidate profile."""
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    background = raw.get("background", {})
    preferences = raw.get("preferences", {})
    personal = raw.get("personal", {})

    education = [
        item
        for item in [
            background.get("degree"),
            background.get("school"),
            background.get("graduation_date"),
        ]
        if item
    ]

    return CandidateProfile(
        name=personal.get("name", "Demo Candidate"),
        location=personal.get("location", ""),
        education=education,
        skills=background.get("skills", []),
        target_geography=preferences.get("target_geography", []),
        target_org_types=preferences.get("target_org_types", []),
        preferred_levels=preferences.get("preferred_levels", []),
        excluded_keywords=preferences.get("excluded_keywords", []),
        master_resume=raw,
    )


def load_signals(path: Path) -> list[Signal]:
    """Load demo career signals."""
    with path.open("r", encoding="utf-8") as handle:
        raw_signals = json.load(handle)

    return [
        Signal(
            source=item["source"],
            title=item["title"],
            signal_type=item.get("signal_type", "news"),
            url=item.get("url"),
            category=item.get("category"),
            summary=item.get("summary"),
            relevance_score=item.get("relevance_score"),
        )
        for item in raw_signals
    ]


def load_opportunities(path: Path) -> list[Opportunity]:
    """Load demo opportunities."""
    with path.open("r", encoding="utf-8") as handle:
        raw_jobs = json.load(handle)

    return [
        Opportunity(
            source=item.get("source", "demo"),
            job_title=item["job_title"],
            company=item["company"],
            location=item.get("location", ""),
            job_url=item.get("job_url"),
            description=item.get("description", ""),
            search_keyword=item.get("search_keyword"),
        )
        for item in raw_jobs
    ]


def load_demo_opportunities(config: dict, base_dir: Path) -> tuple[list[Opportunity], dict[str, int]]:
    """Load and merge all configured demo opportunity sources."""
    sources_config = config.get("sources", {})
    source_providers = []

    career_config = sources_config.get("career_pages", {})
    if career_config.get("fixture_jobs"):
        source_providers.append(
            CareerPageFixtureSource(base_dir / career_config["fixture_jobs"])
        )

    email_config = sources_config.get("linkedin_email", {})
    if email_config.get("fixture_jobs"):
        source_providers.append(
            LinkedInEmailFixtureSource(
                base_dir / email_config["fixture_jobs"],
                sender=email_config.get("sender", "jobalerts-noreply@linkedin.com"),
                hours_back=int(email_config.get("hours_back", 26)),
            )
        )

    search_config = sources_config.get("linkedin_search", {})
    if search_config.get("fixture_jobs") and search_config.get("searches"):
        source_providers.append(
            LinkedInSearchFixtureSource(
                base_dir / search_config["fixture_jobs"],
                base_dir / search_config["searches"],
            )
        )

    if not source_providers:
        opportunities = load_opportunities(base_dir / config["jobs"])
        return opportunities, {"legacy_jobs": len(opportunities), "deduped_total": len(opportunities)}

    source_summary = {source.source_name: len(source.fetch()) for source in source_providers}
    opportunities = fetch_all_opportunities(source_providers)
    source_summary["deduped_total"] = len(opportunities)
    return opportunities, source_summary


def score_demo_opportunity(
    opportunity: Opportunity,
    candidate: CandidateProfile,
) -> Opportunity:
    """Score an opportunity with deterministic local heuristics.

    This is intentionally not an LLM call. It gives contributors a predictable
    demo and test path before configuring any provider credentials.
    """
    combined_text = " ".join(
        [
            opportunity.job_title,
            opportunity.company,
            opportunity.location,
            opportunity.description,
        ]
    ).lower()

    title_text = opportunity.job_title.lower()
    excluded_hit = any(
        keyword.lower() in title_text for keyword in candidate.excluded_keywords
    )
    skill_hits = [
        skill
        for skill in candidate.skills
        if skill.lower() in combined_text
    ]
    geography_hit = any(
        geo.lower() in opportunity.location.lower() or geo.lower() in combined_text
        for geo in candidate.target_geography
    )
    org_hit = any(org_type.lower() in combined_text for org_type in candidate.target_org_types)
    level_hit = any(level.lower() in combined_text for level in candidate.preferred_levels)

    skills_match = min(25, len(skill_hits) * 10)
    experience_relevance = 22 if "impact" in combined_text else 12
    geography_match = 15 if geography_hit else 5
    org_type_match = 15 if org_hit else 8
    level_match = 10 if level_hit else 6
    background_fit = 10 if {"impact", "finance"} <= set(combined_text.split()) else 7

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

    if total >= 80:
        action = "apply_now"
    elif total >= 60:
        action = "review"
    else:
        action = "skip"

    top_reasons = []
    if skill_hits:
        top_reasons.append(f"Matches candidate skills: {', '.join(skill_hits)}.")
    if "impact" in combined_text:
        top_reasons.append("Role language is aligned with impact-focused work.")
    if geography_hit:
        top_reasons.append("Location matches target geography.")

    risks = []
    if not skill_hits:
        risks.append("No explicit skill overlap found in the short demo description.")
    if excluded_hit:
        risks.append("Excluded seniority keyword detected.")

    opportunity.fit = FitScore(
        total=total,
        recommended_action=action,
        skills_match=skills_match,
        experience_relevance=experience_relevance,
        geography_match=geography_match,
        org_type_match=org_type_match,
        level_match=level_match,
        background_fit=background_fit,
        match_summary=(
            f"{opportunity.job_title} at {opportunity.company} scores {total}/100 "
            f"for {candidate.name} in the local demo workflow."
        ),
        top_reasons=top_reasons,
        risks=risks,
        resume_angle=build_resume_angle(opportunity, candidate, skill_hits),
    )
    return opportunity


def build_resume_angle(
    opportunity: Opportunity,
    candidate: CandidateProfile,
    skill_hits: list[str],
) -> str:
    """Create a deterministic resume angle for the demo."""
    skills = ", ".join(skill_hits[:3]) if skill_hits else ", ".join(candidate.skills[:3])
    return (
        f"Position {candidate.name} as a mission-driven analyst who combines "
        f"{skills} with impact finance judgment for {opportunity.company}."
    )


def build_digest(
    candidate: CandidateProfile,
    signals: list[Signal],
    opportunities: list[Opportunity],
    source_summary: dict[str, int] | None = None,
) -> str:
    """Render a plain-text digest preview."""
    lines = [
        "Impact Career Agent demo digest",
        f"Candidate: {candidate.name} ({candidate.location})",
    ]
    if source_summary:
        summary = ", ".join(f"{key}={value}" for key, value in source_summary.items())
        lines.append(f"Sources: {summary}")

    lines.extend(["", "Top signals"])

    for signal in signals[:3]:
        summary = f" - {signal.title}"
        if signal.category:
            summary += f" [{signal.category}]"
        if signal.summary:
            summary += f": {signal.summary}"
        lines.append(summary)

    lines.extend(["", "Opportunities"])
    for opportunity in opportunities:
        fit = opportunity.fit
        score = fit.total if fit else 0
        action = fit.recommended_action if fit else "review"
        lines.append(
            f" - {opportunity.company} | {opportunity.job_title} | "
            f"{score}/100 | {action}"
        )
        if fit and fit.resume_angle:
            lines.append(f"   Resume angle: {fit.resume_angle}")
        if fit and fit.top_reasons:
            lines.append(f"   Why: {' '.join(fit.top_reasons)}")

    lines.extend(
        [
            "",
            "Note: this demo used deterministic local scoring, not an external LLM.",
        ]
    )
    return "\n".join(lines)


def run_demo(config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Run the credential-free demo and return a digest preview."""
    config = load_demo_config(config_path)
    base_dir = config_path.parent.parent if config_path.parent.name == "examples" else Path(".")

    candidate = load_candidate_profile(base_dir / config["candidate_profile"])
    signals = load_signals(base_dir / config["signals"])
    opportunities, source_summary = load_demo_opportunities(config, base_dir)
    scored = [score_demo_opportunity(opportunity, candidate) for opportunity in opportunities]

    return build_digest(candidate, signals, scored, source_summary)
