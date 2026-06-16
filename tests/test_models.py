import pytest
from pydantic import ValidationError

from career_agent.core.models import (
    ApplicationPacket,
    CandidateProfile,
    FitScore,
    GeneratedDocument,
    Opportunity,
    Signal,
)


def test_signal_uses_url_dedup_key():
    signal = Signal(
        source="demo_rss",
        title="Community finance fund closes new vehicle",
        url="https://example.org/news?id=123",
    )

    assert signal.dedup_key.startswith("signal:url:")
    assert "example-org" in signal.dedup_key


def test_opportunity_uses_hash_without_url():
    first = Opportunity(
        source="demo",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        location="Chicago, IL",
    )
    second = Opportunity(
        source="manual",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        location="Chicago, IL",
    )

    assert first.dedup_key == second.dedup_key


def test_fit_score_rejects_bad_action_band():
    with pytest.raises(ValidationError):
        FitScore(total=42, recommended_action="apply_now")


def test_candidate_profile_coerces_single_strings():
    profile = CandidateProfile(
        name="Jane Doe",
        education="Master of Public Policy",
        skills="Python",
    )

    assert profile.education == ["Master of Public Policy"]
    assert profile.skills == ["Python"]


def test_application_packet_has_stable_id():
    opportunity = Opportunity(
        source="demo",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        job_url="https://example.org/jobs/123",
    )
    packet = ApplicationPacket(
        opportunity=opportunity,
        candidate_name="Jane Doe",
        documents=[GeneratedDocument(document_type="resume", content="Resume draft")],
    )

    assert packet.packet_id.startswith("packet:")
    assert len(packet.documents) == 1
