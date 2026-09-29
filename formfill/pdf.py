"""DOCX -> PDF conversion with headless LibreOffice."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class ConversionError(RuntimeError):
    pass


def soffice_binary() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def docx_to_pdf(docx_path: str | Path, timeout: int = 180) -> Path:
    """Convert ``docx_path`` to a PDF next to it and return the PDF path.

    Each call uses its own LibreOffice profile directory, so concurrent conversions
    (several users finishing at once) do not fight over a shared profile lock.
    """
    binary = soffice_binary()
    if not binary:
        raise ConversionError("LibreOffice (soffice) is not installed.")
    docx_path = Path(docx_path).resolve()
    with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile:
        # Path.as_uri() (not a hand-built "file://" string) so the profile URI is well
        # formed on Windows too, where the path has a drive letter and backslashes.
        profile_uri = Path(profile).as_uri()
        cmd = [binary, f"-env:UserInstallation={profile_uri}", "--headless",
               "--convert-to", "pdf", "--outdir", str(docx_path.parent), str(docx_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("PDF conversion timed out.") from exc
    pdf = docx_path.with_suffix(".pdf")
    if proc.returncode != 0 or not pdf.exists():
        raise ConversionError(f"PDF conversion failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return pdf
