from pathlib import Path

from career_agent.demo import load_candidate_profile, run_demo, score_demo_opportunity
from career_agent.core import Opportunity


def test_load_candidate_profile_from_demo_yaml():
    profile = load_candidate_profile(Path("examples/sample_data/candidate_profile.yaml"))

    assert profile.name == "Jane Doe"
    assert "Python" in profile.skills
    assert "impact fund" in profile.target_org_types


def test_demo_scoring_is_local_and_predictable():
    profile = load_candidate_profile(Path("examples/sample_data/candidate_profile.yaml"))
    opportunity = Opportunity(
        source="demo",
        job_title="Impact Investment Analyst",
        company="Example Impact Fund",
        location="Chicago, IL",
        description="Python SQL impact finance analyst role",
    )

    scored = score_demo_opportunity(opportunity, profile)

    assert scored.fit is not None
    assert scored.fit.total >= 80
    assert scored.fit.recommended_action == "apply_now"


def test_run_demo_returns_digest_text():
    digest = run_demo()

    assert "Impact Career Agent demo digest" in digest
    assert "Example Impact Fund" in digest
    assert "deterministic local scoring" in digest
