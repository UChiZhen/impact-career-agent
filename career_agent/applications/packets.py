"""Application packet generation."""

from __future__ import annotations

from career_agent.applications.cover_letter import cover_letter_document, write_cover_letter_content
from career_agent.applications.resume import tailor_resume_content, tailored_resume_document
from career_agent.core import ApplicationPacket, CandidateProfile, Opportunity
from career_agent.llm import LLMProvider


def generate_application_packet(
    opportunity: Opportunity,
    candidate: CandidateProfile,
    provider: LLMProvider,
    *,
    include_cover_letter: bool = True,
) -> ApplicationPacket:
    """Generate structured application documents for one opportunity."""
    tailored_resume = tailor_resume_content(opportunity, candidate, provider)
    documents = [tailored_resume_document(tailored_resume)]
    audit_notes = list(tailored_resume.get("audit_notes", []))

    if include_cover_letter:
        cover_letter = write_cover_letter_content(
            opportunity,
            candidate,
            tailored_resume,
            provider,
        )
        documents.append(cover_letter_document(cover_letter))
        audit_notes.extend(cover_letter.get("audit_notes", []))

    return ApplicationPacket(
        opportunity=opportunity,
        candidate_name=candidate.name,
        documents=documents,
        audit_notes=audit_notes,
    )
