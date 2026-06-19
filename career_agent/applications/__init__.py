"""Application document generation modules."""

from career_agent.applications.cover_letter import (
    COVER_LETTER_SYSTEM_PROMPT,
    build_cover_letter_prompt,
    cover_letter_document,
    normalize_cover_letter,
    write_cover_letter_content,
)
from career_agent.applications.docx_cover_letter import generate_cover_letter_docx
from career_agent.applications.docx_resume import generate_resume_docx
from career_agent.applications.packets import generate_application_packet
from career_agent.applications.packet_outputs import (
    LocalApplicationPacketSink,
    PacketOutputResult,
)
from career_agent.applications.pdf_converter import docx_to_pdf, find_libreoffice
from career_agent.applications.resume import (
    RESUME_TAILOR_SYSTEM_PROMPT,
    build_resume_tailoring_prompt,
    normalize_tailored_resume,
    tailor_resume_content,
    tailored_resume_document,
)

__all__ = [
    "COVER_LETTER_SYSTEM_PROMPT",
    "RESUME_TAILOR_SYSTEM_PROMPT",
    "build_cover_letter_prompt",
    "build_resume_tailoring_prompt",
    "cover_letter_document",
    "docx_to_pdf",
    "find_libreoffice",
    "generate_application_packet",
    "generate_cover_letter_docx",
    "generate_resume_docx",
    "LocalApplicationPacketSink",
    "normalize_cover_letter",
    "normalize_tailored_resume",
    "PacketOutputResult",
    "tailor_resume_content",
    "tailored_resume_document",
    "write_cover_letter_content",
]
