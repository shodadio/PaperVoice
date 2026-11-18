"""PDF reading: outline (bookmarks) first, then heading heuristics, then page blocks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .. import clean

_HEADING = re.compile(
    r"^\s*(?:chapter|part|book|section|prologue|epilogue|introduction|preface|appendix)\b.{0,60}$",
    re.I,
)
_PAGES_PER_BLOCK = 8


def parse(path: Path) -> Tuple[str, List[Tuple[str, str]]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise ValueError(
            "Reading PDFs needs pypdf. Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("This PDF is password protected; remove the password first.") from exc

    title = Path(path).stem
    try:
        meta_title = (reader.metadata or {}).get("/Title")  # type: ignore[union-attr]
        if meta_title:
            title = str(meta_title)
    except Exception:
        pass

    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(clean.normalize_text(page.extract_text() or ""))
        except Exception:
            pages.append("")

    total = len(pages)
    if total == 0:
        return title, []

    outline = _outline_entries(reader)
    if len(outline) >= 2:
        chapters = _from_outline(outline, pages)
        if len(chapters) >= 2:
            return title, chapters

    heading_chapters = _from_headings(pages)
    if len(heading_chapters) >= 2:
        return title, heading_chapters

    blocks: List[Tuple[str, str]] = []
    for start in range(0, total, _PAGES_PER_BLOCK):
        end = min(start + _PAGES_PER_BLOCK, total)
        label = f"Pages {start + 1}-{end}" if total > _PAGES_PER_BLOCK else title
        blocks.append((label, "\n\n".join(p for p in pages[start:end] if p)))
    return title, blocks


def _outline_entries(reader) -> List[Tuple[str, int]]:
    """Flatten nested PDF bookmarks into (title, zero-based page) pairs."""
    entries: List[Tuple[str, int]] = []
    try:
        outline = reader.outline or []
    except Exception:
        return entries

    def walk(items, depth: int = 0) -> None:
        for item in items:
            if isinstance(item, list):
                if depth < 4:
                    walk(item, depth + 1)
                continue
            try:
                page = reader.get_destination_page_number(item)
            except Exception:
                continue
            label = clean.clean_title(getattr(item, "title", "") or "")
            if label and page is not None and page >= 0:
                entries.append((label, int(page)))
            if len(entries) > 400:
                return

    try:
        walk(outline)
    except Exception:
        return entries
    return entries


def _from_outline(entries: List[Tuple[str, int]], pages: List[str]) -> List[Tuple[str, str]]:
    ordered = sorted(entries, key=lambda e: e[1])
    # Keep one entry per starting page; the first title found wins.
    seen = set()
    starts: List[Tuple[str, int]] = []
    for label, page in ordered:
        if page in seen or page >= len(pages):
            continue
        seen.add(page)
        starts.append((label, page))

    chapters: List[Tuple[str, str]] = []
    for index, (label, page) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(pages)
        body = "\n\n".join(p for p in pages[page:end] if p)
        if body.strip():
            chapters.append((label, body))
    if starts and starts[0][1] > 0:
        front = "\n\n".join(p for p in pages[: starts[0][1]] if p)
        if front.strip():
            chapters.insert(0, ("Front matter", front))
    return chapters


def _from_headings(pages: List[str]) -> List[Tuple[str, str]]:
    """Look for stand-alone 'Chapter 7' style lines at the top of each page."""
    starts: List[Tuple[str, int]] = []
    for index, text in enumerate(pages):
        head = "\n".join(text.split("\n")[:3])
        for line in head.split("\n"):
            if _HEADING.match(line) and len(line) < 90:
                label = clean.clean_title(line)
                if label:
                    starts.append((label, index))
                break

    if len(starts) < 3:
        return []

    chapters: List[Tuple[str, str]] = []
    for index, (label, page) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(pages)
        if end <= page:
            end = min(page + 1, len(pages))
        body = "\n\n".join(p for p in pages[page:end] if p)
        if body.strip():
            chapters.append((label, body))
    return chapters


def _unused(reference: Optional[str]) -> None:  # pragma: no cover
    return None
