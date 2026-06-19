"""Application packet output sinks."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from career_agent.applications.docx_cover_letter import generate_cover_letter_docx
from career_agent.applications.docx_resume import generate_resume_docx
from career_agent.applications.pdf_converter import docx_to_pdf
from career_agent.core import ApplicationPacket, CandidateProfile, GeneratedDocument


@dataclass
class PacketOutputResult:
    """Paths produced by an application packet sink."""

    folder: Path
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class LocalApplicationPacketSink:
    """Save user-facing application materials to a local folder."""

    root_dir: Path = Path("application_packets")
    render_pdf: bool = False
    debug_output: bool = False

    def save(self, packet: ApplicationPacket, candidate: CandidateProfile) -> PacketOutputResult:
        """Render and save an application packet locally."""
        folder = self.root_dir / packet_folder_name(packet)
        folder.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        warnings: list[str] = []

        resume_payload = document_json(packet.documents, "resume")
        cover_letter_payload = document_json(packet.documents, "cover_letter")

        if resume_payload:
            resume_docx = folder / user_facing_filename(packet, "Resume", ".docx")
            generate_resume_docx(resume_payload, candidate, resume_docx)
            files.append(resume_docx)
            if self.render_pdf:
                maybe_pdf = render_pdf_with_warning(resume_docx, folder, warnings)
                if maybe_pdf:
                    files.append(maybe_pdf)

        if cover_letter_payload:
            cover_letter_docx = folder / user_facing_filename(packet, "Cover Letter", ".docx")
            generate_cover_letter_docx(cover_letter_payload, candidate, cover_letter_docx)
            files.append(cover_letter_docx)
            if self.render_pdf:
                maybe_pdf = render_pdf_with_warning(cover_letter_docx, folder, warnings)
                if maybe_pdf:
                    files.append(maybe_pdf)

        manifest_path = folder / "manifest.json"
        manifest_path.write_text(
            json.dumps(packet_manifest(packet, files, warnings=warnings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files.append(manifest_path)

        if self.debug_output:
            files.extend(write_debug_files(folder, packet))

        return PacketOutputResult(folder=folder, files=files, warnings=warnings)


def document_json(documents: list[GeneratedDocument], document_type: str) -> dict[str, Any]:
    """Return a generated document JSON payload."""
    for document in documents:
        if document.document_type == document_type and document.content:
            return json.loads(document.content)
    return {}


def packet_manifest(
    packet: ApplicationPacket,
    files: list[Path],
    *,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a lightweight manifest for local and cloud storage."""
    opportunity = packet.opportunity
    fit = opportunity.fit
    return {
        "packet_id": packet.packet_id,
        "created_at": packet.created_at.isoformat(),
        "candidate_name": packet.candidate_name,
        "opportunity": {
            "company": opportunity.company,
            "job_title": opportunity.job_title,
            "location": opportunity.location,
            "job_url": opportunity.job_url,
            "source": opportunity.source,
        },
        "fit": {
            "total": fit.total if fit else None,
            "recommended_action": fit.recommended_action if fit else None,
            "resume_angle": fit.resume_angle if fit else "",
        },
        "files": [path.name for path in files],
        "warnings": warnings or [],
    }


def render_pdf_with_warning(
    docx_path: Path,
    folder: Path,
    warnings: list[str],
) -> Path | None:
    """Render a PDF, recording a warning instead of failing the whole packet."""
    try:
        return docx_to_pdf(docx_path, folder)
    except Exception as exc:
        warnings.append(f"PDF rendering failed for {docx_path.name}: {exc}")
        return None


def write_debug_files(folder: Path, packet: ApplicationPacket) -> list[Path]:
    """Write local-only debugging artifacts."""
    files = []
    for document in packet.documents:
        if not document.content:
            continue
        path = folder / f"{document.document_type}.json"
        path.write_text(document.content, encoding="utf-8")
        files.append(path)

    audit_path = folder / "audit_notes.txt"
    audit_path.write_text("\n".join(packet.audit_notes), encoding="utf-8")
    files.append(audit_path)
    return files


def packet_folder_name(packet: ApplicationPacket) -> str:
    """Create a stable readable folder name for one application packet."""
    date_part = packet.created_at.date().isoformat()
    opportunity = packet.opportunity
    readable = "__".join(
        compact_slug(part)
        for part in (
            opportunity.company,
            opportunity.job_title,
            opportunity.location,
        )
        if part
    )
    short_hash = packet.packet_id.split(":")[-1][:8]
    return f"{date_part}__{readable}__{short_hash}"[:180]


def user_facing_filename(packet: ApplicationPacket, label: str, suffix: str) -> str:
    """Create a readable document filename."""
    opportunity = packet.opportunity
    stem = " - ".join(
        part
        for part in (
            label,
            opportunity.company,
            opportunity.job_title,
        )
        if part
    )
    return f"{compact_filename(stem)}{suffix}"


def compact_slug(value: str) -> str:
    """Normalize a string for folder path components."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:70] or "item"


def compact_filename(value: str) -> str:
    """Normalize a string for a user-facing filename."""
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9 ._-]+", "", ascii_text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:140] or "Application Document"
