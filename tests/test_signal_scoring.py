import json

import pytest

from career_agent.core import CandidateProfile, Signal
from career_agent.llm import LLMProviderError, MockLLMProvider
from career_agent.scoring.signals import (
    build_signal_scoring_prompt,
    mock_signal_score_response,
    normalize_signal_action,
    score_signals,
    top_signals,
)


def test_build_signal_scoring_prompt_includes_candidate_context():
    signal = Signal(
        source="ImpactAlpha",
        title="Impact fund closes new climate vehicle",
        signal_subtype="fund_close",
    )
    candidate = CandidateProfile(
        name="Jane Doe",
        skills=["Python", "impact measurement"],
        target_org_types=["impact fund"],
    )

    prompt = build_signal_scoring_prompt([signal], candidate)

    assert "Impact fund closes new climate vehicle" in prompt
    assert "impact measurement" in prompt
    assert "relevance_score" in prompt


def test_score_signals_applies_provider_payload():
    signals = [
        Signal(
            source="ImpactAlpha",
            title="LP commits to emerging impact fund",
            signal_subtype="lp_commitment",
        )
    ]
    payload = [
        {
            "id": 0,
            "signal_subtype": "lp_commitment",
            "relevance_score": 9,
            "confidence": 8,
            "category": "impact_investing",
            "entities": ["Example Pension", "Example Impact Fund"],
            "geography": "United States",
            "sector": "community finance",
            "capital_amount": "$50 million",
            "career_hypothesis": "The manager may expand investor relations coverage.",
            "suggested_action": "add_to_watchlist",
            "rationale": "Concrete LP commitment.",
        }
    ]
    provider = MockLLMProvider(default_response=json.dumps(payload))

    scored = score_signals(signals, provider)

    assert scored[0].relevance_score == 9
    assert scored[0].confidence == 8
    assert scored[0].entities == ["Example Pension", "Example Impact Fund"]
    assert scored[0].suggested_action == "add_to_watchlist"
    assert scored[0].metadata["score_rationale"] == "Concrete LP commitment."


def test_score_signals_rejects_wrong_payload_length():
    provider = MockLLMProvider(default_response="[]")

    with pytest.raises(LLMProviderError):
        score_signals([Signal(source="ImpactAlpha", title="Signal")], provider)


def test_top_signals_sorts_by_relevance_then_confidence():
    signals = [
        Signal(source="A", title="low", relevance_score=3, confidence=9),
        Signal(source="B", title="high", relevance_score=9, confidence=4),
        Signal(source="C", title="tie winner", relevance_score=9, confidence=8),
    ]

    assert [signal.title for signal in top_signals(signals, limit=2)] == [
        "tie winner",
        "high",
    ]


def test_mock_signal_score_response_scores_macro_lower():
    signals = [
        Signal(source="A", title="New GP launches climate fund", signal_subtype="fund_launch"),
        Signal(source="B", title="Macro outlook shifts", signal_subtype="macro_tailwind"),
    ]

    payload = json.loads(mock_signal_score_response(signals))

    assert payload[0]["relevance_score"] == 8
    assert payload[1]["relevance_score"] == 4


def test_normalize_signal_action_ignores_low_score_unknown_action():
    assert normalize_signal_action("unknown", "macro_tailwind", 1) == "ignore"
