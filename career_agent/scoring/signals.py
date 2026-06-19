"""Career-oriented signal scoring."""

from __future__ import annotations

import json
from typing import Any

from career_agent.core import CandidateProfile, Signal
from career_agent.llm import LLMProvider, LLMProviderError
from career_agent.sources.news import (
    career_hypothesis_for_subtype,
    classify_capital_signal,
    suggested_action_for_subtype,
)


SIGNAL_SCORING_SYSTEM_PROMPT = """You are a careful career intelligence analyst.

Score news and capital-market signals for mission-driven job seekers. Prioritize
signals that reveal where teams may hire soon: new funds, LP commitments,
transactions, portfolio growth, new geographies, partnerships, programs, and
direct hiring/team expansion. Return valid JSON only.
"""


def build_signal_scoring_prompt(
    signals: list[Signal],
    candidate: CandidateProfile | None = None,
) -> str:
    """Build a provider-agnostic signal scoring prompt."""
    signal_payload = [
        {
            "id": index,
            "source": signal.source,
            "title": signal.title,
            "category": signal.category,
            "signal_subtype": signal.signal_subtype,
            "summary": (signal.summary or signal.raw_text or "")[:900],
            "url": signal.url,
        }
        for index, signal in enumerate(signals)
    ]
    profile_payload = None
    if candidate:
        profile_payload = {
            "location": candidate.location,
            "skills": candidate.skills,
            "target_geography": candidate.target_geography,
            "target_org_types": candidate.target_org_types,
            "preferred_levels": candidate.preferred_levels,
            "excluded_keywords": candidate.excluded_keywords,
        }

    return f"""Candidate profile, if provided:
{json.dumps(profile_payload, ensure_ascii=False, indent=2)}

Signals to score:
{json.dumps(signal_payload, ensure_ascii=False, indent=2)}

Return a JSON array with one object per signal, in the same order:
[
  {{
    "id": 0,
    "signal_subtype": "fund_launch | fund_close | lp_commitment | transaction | portfolio_investment | new_office_or_region | strategic_partnership | program_or_grant | macro_tailwind | hiring_signal",
    "relevance_score": 0-10,
    "confidence": 0-10,
    "category": "impact_investing | development_finance | climate_finance | community_finance | macro | other",
    "entities": ["organizations, funds, LPs, DFIs, portfolio companies"],
    "geography": "short geography or empty string",
    "sector": "short sector or empty string",
    "capital_amount": "capital amount if present or empty string",
    "career_hypothesis": "one sentence on why this may create job leads",
    "suggested_action": "rescan_org_jobs | add_to_watchlist | search_linkedin | review_keywords | ignore",
    "rationale": "short reason for score"
  }}
]

Use relevance_score 8-10 only when the signal points to concrete near-term
career action. Macro-only articles should usually be 3-6 unless they clearly
change target sectors, keywords, or hiring demand.
"""


def score_signals(
    signals: list[Signal],
    provider: LLMProvider,
    *,
    candidate: CandidateProfile | None = None,
) -> list[Signal]:
    """Score signals with an LLM provider."""
    if not signals:
        return []

    prompt = build_signal_scoring_prompt(signals, candidate)
    response = provider.generate(prompt, system=SIGNAL_SCORING_SYSTEM_PROMPT)
    payload = response.json_array()

    if len(payload) != len(signals):
        raise LLMProviderError(f"Expected {len(signals)} scored signals, got {len(payload)}")

    return [
        apply_signal_score(signal, item)
        for signal, item in zip(signals, payload)
    ]


def score_signal(signal: Signal, provider: LLMProvider, *, candidate: CandidateProfile | None = None) -> Signal:
    """Score a single signal."""
    return score_signals([signal], provider, candidate=candidate)[0]


def apply_signal_score(signal: Signal, item: dict[str, Any]) -> Signal:
    """Return a copy of a signal with LLM scoring fields attached."""
    subtype = normalize_signal_subtype(item.get("signal_subtype"), signal)
    suggested_action = normalize_signal_action(
        item.get("suggested_action"),
        subtype,
        _bounded_int(item.get("relevance_score", signal.relevance_score or 0), 0, 10),
    )
    metadata = {
        **signal.metadata,
        "score_rationale": str(item.get("rationale", "")),
    }
    return signal.model_copy(
        update={
            "signal_subtype": subtype,
            "relevance_score": _bounded_int(item.get("relevance_score", 0), 0, 10),
            "confidence": _bounded_int(item.get("confidence", signal.confidence or 0), 0, 10),
            "category": str(item.get("category", signal.category or "")) or signal.category,
            "entities": _coerce_string_list(item.get("entities")),
            "geography": str(item.get("geography", "")) or signal.geography,
            "sector": str(item.get("sector", "")) or signal.sector,
            "capital_amount": str(item.get("capital_amount", "")) or signal.capital_amount,
            "career_hypothesis": (
                str(item.get("career_hypothesis", "")) or career_hypothesis_for_subtype(subtype)
            ),
            "suggested_action": suggested_action,
            "metadata": metadata,
        }
    )


def normalize_signal_subtype(value: Any, signal: Signal) -> str:
    """Normalize provider signal type values."""
    allowed = {
        "fund_launch",
        "fund_close",
        "lp_commitment",
        "transaction",
        "portfolio_investment",
        "new_office_or_region",
        "strategic_partnership",
        "program_or_grant",
        "macro_tailwind",
        "hiring_signal",
    }
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in allowed:
        return normalized
    if signal.signal_subtype:
        return signal.signal_subtype
    return classify_capital_signal(f"{signal.title} {signal.summary or ''} {signal.raw_text or ''}".lower())


def normalize_signal_action(value: Any, subtype: str, score: int) -> str:
    """Normalize provider action values into workflow actions."""
    allowed = {
        "rescan_org_jobs",
        "add_to_watchlist",
        "search_linkedin",
        "review_keywords",
        "ignore",
    }
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in allowed:
        return normalized
    if score <= 2:
        return "ignore"
    return suggested_action_for_subtype(subtype)


def top_signals(signals: list[Signal], *, limit: int = 5) -> list[Signal]:
    """Return the highest-value signals for a digest."""
    return sorted(
        signals,
        key=lambda signal: (
            signal.relevance_score if signal.relevance_score is not None else -1,
            signal.confidence if signal.confidence is not None else -1,
            signal.published_at or signal.created_at,
        ),
        reverse=True,
    )[:limit]


def mock_signal_score_response(signals: list[Signal]) -> str:
    """Return deterministic signal scores for CLI demos and tests."""
    payload = []
    for index, signal in enumerate(signals):
        subtype = signal.signal_subtype or normalize_signal_subtype(None, signal)
        action = suggested_action_for_subtype(subtype)
        base_score = 8 if subtype in {"fund_close", "fund_launch", "lp_commitment", "hiring_signal"} else 6
        if subtype == "macro_tailwind":
            base_score = 4
        payload.append(
            {
                "id": index,
                "signal_subtype": subtype,
                "relevance_score": base_score,
                "confidence": signal.confidence or 6,
                "category": signal.category or "impact_investing",
                "entities": signal.entities,
                "geography": signal.geography or "",
                "sector": signal.sector or "",
                "capital_amount": signal.capital_amount or "",
                "career_hypothesis": signal.career_hypothesis
                or career_hypothesis_for_subtype(subtype),
                "suggested_action": action,
                "rationale": "Deterministic mock signal score for local validation.",
            }
        )
    return json.dumps(payload)


def _coerce_string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))
