"""LLM-backed cover letter drafting contracts."""

from __future__ import annotations

import json
from typing import Any

from career_agent.core import CandidateProfile, GeneratedDocument, Opportunity
from career_agent.llm import LLMProvider, LLMProviderError


COVER_LETTER_SYSTEM_PROMPT = """You are a professional career strategist.

Write a concise, specific cover letter that aligns with the tailored resume and
the job description. Preserve candidate facts and avoid invented claims. Return
valid JSON only.
"""


def build_cover_letter_prompt(
    candidate: CandidateProfile,
    opportunity: Opportunity,
    tailored_resume: dict[str, Any],
) -> str:
    """Build a provider-agnostic cover letter prompt."""
    payload = {
        "candidate": {
            "name": candidate.name,
            "location": candidate.location,
            "education": candidate.education,
        },
        "opportunity": {
            "company": opportunity.company,
            "job_title": opportunity.job_title,
            "location": opportunity.location,
            "description": opportunity.description,
            "resume_angle": opportunity.fit.resume_angle if opportunity.fit else "",
        },
        "tailored_resume": tailored_resume,
    }
    return f"""Input:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Task:
Draft a matching cover letter for this application.

Requirements:
- Use the same experience selection and positioning as the tailored resume.
- Write 4-6 concise paragraphs.
- Reference concrete achievements from the provided resume data.
- Use a professional but human tone.
- Do not invent facts, names, awards, metrics, or credentials.

Return ONLY this JSON object:
{{
  "greeting": "Dear Hiring Committee at [Company Name],",
  "paragraphs": [
    "Opening paragraph...",
    "Body paragraph...",
    "Closing paragraph..."
  ],
  "closing": "Best regards,",
  "signature": "Candidate Name",
  "audit_notes": ["short note on positioning"]
}}
"""


def write_cover_letter_content(
    opportunity: Opportunity,
    candidate: CandidateProfile,
    tailored_resume: dict[str, Any],
    provider: LLMProvider,
) -> dict[str, Any]:
    """Generate structured cover letter content."""
    prompt = build_cover_letter_prompt(candidate, opportunity, tailored_resume)
    response = provider.generate(prompt, system=COVER_LETTER_SYSTEM_PROMPT)
    payload = response.json_object()
    return normalize_cover_letter(payload, candidate=candidate, opportunity=opportunity)


def cover_letter_document(content: dict[str, Any]) -> GeneratedDocument:
    """Wrap structured cover letter data as a generated document."""
    return GeneratedDocument(
        document_type="cover_letter",
        content=json.dumps(content, ensure_ascii=False, indent=2),
        format="json",
    )


def normalize_cover_letter(
    payload: dict[str, Any],
    *,
    candidate: CandidateProfile,
    opportunity: Opportunity,
) -> dict[str, Any]:
    """Normalize provider JSON into the v0.1 cover letter shape."""
    if "paragraphs" not in payload:
        raise LLMProviderError("Cover letter response missing paragraphs")
    paragraphs = [str(item) for item in coerce_list(payload.get("paragraphs")) if str(item).strip()]
    if len(paragraphs) < 3:
        raise LLMProviderError("Cover letter response must include at least 3 paragraphs")

    return {
        "greeting": str(
            payload.get("greeting")
            or f"Dear Hiring Committee at {opportunity.company},"
        ),
        "paragraphs": paragraphs,
        "closing": str(payload.get("closing") or "Best regards,"),
        "signature": str(payload.get("signature") or candidate.name),
        "audit_notes": [str(item) for item in coerce_list(payload.get("audit_notes"))],
    }


def coerce_list(value: Any) -> list[Any]:
    """Coerce provider values into a list."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]
