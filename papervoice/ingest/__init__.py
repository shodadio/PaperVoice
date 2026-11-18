"""Turn a document file into an ordered list of (title, text) chapters."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, NamedTuple, Tuple

from .. import clean


class IngestError(Exception):
    """Raised when a document cannot be read, with a message safe to show users."""


class Book(NamedTuple):
    title: str
    chapters: List[Tuple[str, str]]


SUPPORTED = {".epub", ".pdf", ".txt", ".md", ".markdown", ".html", ".htm", ".docx"}
CONVERTIBLE = {".mobi", ".azw", ".azw3", ".fb2", ".rtf", ".odt", ".lit", ".pdb"}


def ingest(path: Path) -> Book:
    """Read `path` and return its title and chapters, in reading order."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in CONVERTIBLE:
        path = _convert_with_calibre(path)
        suffix = ".epub"
    if suffix not in SUPPORTED:
        raise IngestError(
            f"Cannot read {suffix or 'that file type'}. Supported: "
            "EPUB, PDF, DOCX, TXT, Markdown, HTML."
        )

    from . import docs, epub, pdf

    if suffix == ".epub":
        title, chapters = epub.parse(path)
    elif suffix == ".pdf":
        title, chapters = pdf.parse(path)
    else:
        title, chapters = docs.parse(path)

    chapters = _tidy(chapters)
    if not chapters:
        raise IngestError(
            "No readable text found. This may be a scanned PDF (needs OCR) or a DRM-protected book."
        )
    return Book(clean.clean_title(title) or path.stem, chapters)


def _tidy(chapters: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Normalise text, drop empties and merge fragments that are too short to narrate."""
    out: List[Tuple[str, str]] = []
    for title, text in chapters:
        body = clean.normalize_text(text)
        title = clean.clean_title(title) or "Untitled section"
        if not body:
            continue
        if out and len(body) < 200:
            prev_title, prev_text = out[-1]
            out[-1] = (prev_title, prev_text + "\n\n" + body)
            continue
        out.append((title, body))
    if not out:
        return []
    # A lone chapter with no useful title still deserves a name.
    if len(out) == 1 and not out[0][0].strip():
        out[0] = ("Full text", out[0][1])
    return out


def _convert_with_calibre(path: Path) -> Path:
    """Use Calibre's ebook-convert for MOBI/AZW3/RTF/ODT when it is installed."""
    exe = shutil.which("ebook-convert")
    if not exe:
        raise IngestError(
            f"{path.suffix.upper()} needs Calibre. Install it (brew install --cask calibre) "
            "or convert the file to EPUB first."
        )
    target = Path(tempfile.mkdtemp(prefix="papervoice-convert-")) / (path.stem + ".epub")
    result = subprocess.run(
        [exe, str(path), str(target)], capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0 or not target.exists():
        raise IngestError("Calibre could not convert this file to EPUB.")
    return target
