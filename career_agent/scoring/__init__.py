"""Scoring and ranking modules."""

from career_agent.scoring.job_fit import (
    JOB_FIT_SYSTEM_PROMPT,
    apply_fit_score,
    build_job_fit_prompt,
    fit_score_from_dict,
    fallback_score_opportunity,
    normalize_action,
    score_opportunities,
    score_opportunities_with_fallback,
    score_opportunity,
)
from career_agent.scoring.signals import (
    SIGNAL_SCORING_SYSTEM_PROMPT,
    apply_signal_score,
    build_signal_scoring_prompt,
    mock_signal_score_response,
    normalize_signal_action,
    normalize_signal_subtype,
    score_signal,
    score_signals,
    top_signals,
)

__all__ = [
    "JOB_FIT_SYSTEM_PROMPT",
    "apply_fit_score",
    "build_job_fit_prompt",
    "fit_score_from_dict",
    "fallback_score_opportunity",
    "normalize_action",
    "score_opportunities",
    "score_opportunities_with_fallback",
    "score_opportunity",
    "SIGNAL_SCORING_SYSTEM_PROMPT",
    "apply_signal_score",
    "build_signal_scoring_prompt",
    "mock_signal_score_response",
    "normalize_signal_action",
    "normalize_signal_subtype",
    "score_signal",
    "score_signals",
    "top_signals",
]
