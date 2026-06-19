import json

import pytest

from career_agent.applications import (
    build_cover_letter_prompt,
    build_resume_tailoring_prompt,
    generate_application_packet,
    normalize_cover_letter,
    normalize_tailored_resume,
    tailor_resume_content,
    write_cover_letter_content,
)
from career_agent.core import CandidateProfile, FitScore, Opportunity
from career_agent.llm import LLMProviderError, LLMResponse


class SequenceProvider:
    provider_name = "sequence"
    model = "sequence-local"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        self.calls.append({"prompt": prompt, "system": system})
        text = self.responses.pop(0)
        return LLMResponse(provider=self.provider_name, model=self.model, text=text)


def demo_candidate():
    return CandidateProfile(
        name="Jane Doe",
        location="Chicago, IL",
        education=["Master of Public Policy"],
        skills=["Python", "SQL", "financial analysis"],
        master_resume={
            "work_experience": [
                {
                    "company": "Example Impact Fund",
                    "role": "Investment Research Fellow",
                    "dates": "2025",
                    "bullets": ["Screened climate investments with Python."],
                }
            ],
            "skills": {"data_analysis": ["Python", "SQL"]},
        },
    )


def demo_opportunity():
    return Opportunity(
        source="demo",
        company="Example Impact Fund",
        job_title="Impact Investment Analyst",
        location="Chicago, IL",
        job_url="https://example.org/jobs/impact-investment-analyst",
        description="Analyze climate investments using Python, SQL, and financial models.",
        fit=FitScore(
            total=88,
            recommended_action="apply_now",
            resume_angle="Lead with climate investment analytics.",
            top_reasons=["Strong finance and Python overlap."],
        ),
    )


def tailored_resume_payload():
    return {
        "role_type": "finance",
        "summary_text": "Impact finance analyst with Python and diligence experience.",
        "work_experience": [
            {
                "company": "Example Impact Fund",
                "role": "Investment Research Fellow",
                "location": "Chicago, IL",
                "dates": "2025",
                "bullets": ["Screened climate investments using Python and market research."],
            }
        ],
        "combined_section_header": "SELECTED PROJECTS",
        "combined_section": [
            {
                "name": "Impact Fund Tracker",
                "role": "Builder",
                "dates": "2026",
                "bullets": ["Classified capital signals into job-search actions."],
            }
        ],
        "skills": [
            {"label": "Data Analysis & Programming", "value": "Python, SQL"},
            {"label": "Finance", "value": "Financial modeling, due diligence"},
            {"label": "Tools", "value": "Excel, Google Sheets"},
        ],
        "audit_notes": ["Selected finance-forward experience."],
    }


def cover_letter_payload():
    return {
        "greeting": "Dear Hiring Committee at Example Impact Fund,",
        "paragraphs": [
            "I am excited to apply for the Impact Investment Analyst role.",
            "My investment research experience aligns with the climate diligence needs.",
            "I would welcome the chance to contribute to your investment process.",
        ],
        "closing": "Best regards,",
        "signature": "Jane Doe",
        "audit_notes": ["Aligned letter to tailored resume."],
    }


def test_build_resume_tailoring_prompt_contains_master_resume_and_fit_angle():
    prompt = build_resume_tailoring_prompt(demo_candidate(), demo_opportunity())

    assert "Example Impact Fund" in prompt
    assert "Lead with climate investment analytics" in prompt
    assert "master_resume" in prompt
    assert "Return ONLY this JSON object" in prompt


def test_tailor_resume_content_normalizes_provider_response():
    provider = SequenceProvider([json.dumps(tailored_resume_payload())])

    content = tailor_resume_content(demo_opportunity(), demo_candidate(), provider)

    assert content["role_type"] == "finance"
    assert content["work_experience"][0]["company"] == "Example Impact Fund"
    assert content["skills"][0] == {
        "label": "Data Analysis & Programming",
        "value": "Python, SQL",
    }


def test_normalize_tailored_resume_rejects_missing_required_fields():
    with pytest.raises(LLMProviderError, match="work_experience"):
        normalize_tailored_resume({"skills": []})


def test_build_cover_letter_prompt_uses_tailored_resume():
    prompt = build_cover_letter_prompt(
        demo_candidate(),
        demo_opportunity(),
        tailored_resume_payload(),
    )

    assert "Impact Investment Analyst" in prompt
    assert "Selected finance-forward experience" in prompt
    assert "Do not invent facts" in prompt


def test_write_cover_letter_content_normalizes_provider_response():
    provider = SequenceProvider([json.dumps(cover_letter_payload())])

    content = write_cover_letter_content(
        demo_opportunity(),
        demo_candidate(),
        tailored_resume_payload(),
        provider,
    )

    assert content["signature"] == "Jane Doe"
    assert len(content["paragraphs"]) == 3


def test_normalize_cover_letter_rejects_too_few_paragraphs():
    with pytest.raises(LLMProviderError, match="at least 3 paragraphs"):
        normalize_cover_letter(
            {"paragraphs": ["One", "Two"]},
            candidate=demo_candidate(),
            opportunity=demo_opportunity(),
        )


def test_generate_application_packet_returns_resume_and_cover_letter_documents():
    provider = SequenceProvider(
        [
            json.dumps(tailored_resume_payload()),
            json.dumps(cover_letter_payload()),
        ]
    )

    packet = generate_application_packet(demo_opportunity(), demo_candidate(), provider)

    assert packet.candidate_name == "Jane Doe"
    assert packet.packet_id.startswith("packet:")
    assert [document.document_type for document in packet.documents] == [
        "resume",
        "cover_letter",
    ]
    assert packet.documents[0].format == "json"
    assert "Selected finance-forward experience." in packet.audit_notes
    assert "Aligned letter to tailored resume." in packet.audit_notes
