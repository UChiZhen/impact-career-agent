"""LLM-backed resume tailoring contracts."""

from __future__ import annotations

import json
from typing import Any

from career_agent.core import CandidateProfile, GeneratedDocument, Opportunity
from career_agent.llm import LLMProvider, LLMProviderError


RESUME_TAILOR_SYSTEM_PROMPT = """You are an expert resume strategist.

Tailor a master resume to one job posting. Preserve facts, numbers, employers,
schools, dates, and tools from the master resume. You may select, reorder, and
reframe content, but you must not invent experience. Return valid JSON only.
"""


def build_resume_tailoring_prompt(candidate: CandidateProfile, opportunity: Opportunity) -> str:
    """Build a provider-agnostic resume tailoring prompt.

    This migrates the core `auto_resume/src/resume_tailor.py` behavior into the
    unified project while keeping private resume data out of fixtures.
    """
    payload = {
        "candidate": {
            "name": candidate.name,
            "location": candidate.location,
            "education": candidate.education,
            "skills": candidate.skills,
            "master_resume": candidate.master_resume,
        },
        "opportunity": {
            "company": opportunity.company,
            "job_title": opportunity.job_title,
            "location": opportunity.location,
            "description": opportunity.description,
            "job_url": opportunity.job_url,
            "fit_score": opportunity.fit.total if opportunity.fit else None,
            "resume_angle": opportunity.fit.resume_angle if opportunity.fit else "",
            "top_reasons": opportunity.fit.top_reasons if opportunity.fit else [],
            "risks": opportunity.fit.risks if opportunity.fit else [],
        },
    }

    return f"""Input:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Task:
Create a targeted one-page resume plan for this role.

Instructions:
- Classify the role as "finance" or "non_finance".
- Select the strongest work, leadership, and project entries from master_resume.
- Rewrite bullets to match the job description while preserving facts.
- Use the resume_angle if provided.
- Keep the output compact enough for a one-page resume.
- Do not include private commentary or markdown.

Return ONLY this JSON object:
{{
  "role_type": "finance | non_finance",
  "summary_text": "2-3 sentence role-specific summary",
  "work_experience_header": "WORK EXPERIENCE",
  "work_experience": [
    {{
      "company": "Company Name",
      "role": "Role Title",
      "location": "City, State/Country",
      "dates": "Date range",
      "bullets": ["2-3 targeted bullets"]
    }}
  ],
  "combined_section_header": "SELECTED PROJECTS or LEADERSHIP & PROJECT EXPERIENCE",
  "combined_section": [
    {{
      "name": "Entry Name",
      "role": "Role or subtitle",
      "location": "City, State/Country",
      "dates": "Date range",
      "bullets": ["1-2 targeted bullets"]
    }}
  ],
  "skills": [
    {{"label": "Data Analysis & Programming", "value": "Python, SQL"}},
    {{"label": "Methods", "value": "Financial modeling, due diligence"}},
    {{"label": "Languages", "value": "English"}}
  ],
  "audit_notes": ["short note on selection strategy"]
}}
"""


def tailor_resume_content(
    opportunity: Opportunity,
    candidate: CandidateProfile,
    provider: LLMProvider,
) -> dict[str, Any]:
    """Generate structured tailored resume content."""
    prompt = build_resume_tailoring_prompt(candidate, opportunity)
    response = provider.generate(prompt, system=RESUME_TAILOR_SYSTEM_PROMPT)
    payload = response.json_object()
    return normalize_tailored_resume(payload)


def tailored_resume_document(content: dict[str, Any]) -> GeneratedDocument:
    """Wrap structured tailored resume data as a generated document."""
    return GeneratedDocument(
        document_type="resume",
        content=json.dumps(content, ensure_ascii=False, indent=2),
        format="json",
    )


def normalize_tailored_resume(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize provider JSON into the v0.1 tailored resume shape."""
    if "work_experience" not in payload:
        raise LLMProviderError("Tailored resume response missing work_experience")
    if "skills" not in payload:
        raise LLMProviderError("Tailored resume response missing skills")

    normalized = dict(payload)
    normalized["role_type"] = normalize_role_type(normalized.get("role_type"))
    normalized.setdefault("summary_text", "")
    normalized.setdefault("work_experience_header", "WORK EXPERIENCE")
    normalized.setdefault("combined_section_header", "LEADERSHIP & PROJECT EXPERIENCE")
    normalized.setdefault("combined_section", [])
    normalized["work_experience"] = [
        normalize_resume_entry(item, company_key="company")
        for item in coerce_list(normalized.get("work_experience"))
    ]
    normalized["combined_section"] = [
        normalize_resume_entry(item, company_key="name")
        for item in coerce_list(normalized.get("combined_section"))
    ]
    normalized["skills"] = normalize_skills(normalized.get("skills"))
    normalized["audit_notes"] = [str(item) for item in coerce_list(normalized.get("audit_notes"))]
    return normalized


def normalize_resume_entry(item: Any, *, company_key: str) -> dict[str, Any]:
    """Normalize one resume entry."""
    if not isinstance(item, dict):
        raise LLMProviderError("Resume entries must be objects")
    name_value = item.get(company_key) or item.get("company") or item.get("name") or ""
    return {
        company_key: str(name_value),
        "role": str(item.get("role", item.get("title", ""))),
        "location": str(item.get("location", "")),
        "dates": str(item.get("dates", "")),
        "bullets": [str(bullet) for bullet in coerce_list(item.get("bullets")) if str(bullet).strip()],
    }


def normalize_skills(value: Any) -> list[dict[str, str]]:
    """Normalize skills into label/value rows."""
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            if isinstance(item, list):
                skill_value = ", ".join(str(skill) for skill in item)
            else:
                skill_value = str(item)
            if skill_value.strip():
                rows.append({"label": str(key).replace("_", " ").title(), "value": skill_value})
        return rows

    rows = []
    for item in coerce_list(value):
        if isinstance(item, dict):
            label = item.get("label", item.get("name", item.get("category", "Skills")))
            skill_value = item.get("value", item.get("content", item.get("skills", "")))
            if isinstance(skill_value, list):
                skill_value = ", ".join(str(skill) for skill in skill_value)
            if str(skill_value).strip():
                rows.append({"label": str(label), "value": str(skill_value)})
        elif str(item).strip():
            rows.append({"label": "Skills", "value": str(item)})
    return rows


def normalize_role_type(value: Any) -> str:
    """Normalize role type into the supported v0.1 set."""
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in {"finance", "non_finance"} else "non_finance"


def coerce_list(value: Any) -> list[Any]:
    """Coerce provider values into a list."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]
