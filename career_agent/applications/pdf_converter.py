"""DOCX to PDF conversion helpers."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def find_libreoffice() -> str:
    """Find a LibreOffice executable for DOCX to PDF conversion."""
    candidates = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/libreoffice",
        "/usr/local/bin/libreoffice",
        "/opt/homebrew/bin/soffice",
        "/usr/local/bin/soffice",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    result = subprocess.run(["which", "soffice"], capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    raise FileNotFoundError(
        "LibreOffice not found. Install LibreOffice to enable PDF rendering."
    )


def docx_to_pdf(docx_path: Path, output_dir: Path | None = None) -> Path:
    """Convert a DOCX file to PDF using LibreOffice."""
    docx_path = Path(docx_path).resolve()
    output_dir = (Path(output_dir) if output_dir else docx_path.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    soffice = find_libreoffice()
    with tempfile.TemporaryDirectory(prefix="career_agent_soffice_") as user_profile:
        command = [
            soffice,
            f"-env:UserInstallation=file://{user_profile}",
            "--invisible",
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                timeout=120,
                capture_output=True,
                env=libreoffice_env(user_profile),
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
            stdout = exc.stdout.decode("utf-8", errors="ignore") if exc.stdout else ""
            raise RuntimeError(
                "LibreOffice PDF conversion failed. "
                "Omit --render-pdf to save DOCX only, or verify LibreOffice can run locally. "
                f"stdout={stdout.strip()} stderr={stderr.strip()}"
            ) from exc
    pdf_path = output_dir / docx_path.with_suffix(".pdf").name
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF conversion failed: {pdf_path}")
    return pdf_path


def libreoffice_env(user_profile: str) -> dict[str, str]:
    """Build a writable environment for headless LibreOffice."""
    import os

    env = os.environ.copy()
    env["HOME"] = user_profile
    env.setdefault("XDG_CONFIG_HOME", str(Path(user_profile) / "xdg_config"))
    env.setdefault("XDG_CACHE_HOME", str(Path(user_profile) / "xdg_cache"))
    Path(env["XDG_CONFIG_HOME"]).mkdir(parents=True, exist_ok=True)
    Path(env["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
    return env
