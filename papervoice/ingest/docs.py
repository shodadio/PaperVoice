"""Plain text, Markdown, HTML and DOCX reading."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import List, Tuple
from xml.etree import ElementTree as ET

from .. import clean

_MD_HEADING = re.compile(r"^#{1,2}\s+(.+?)\s*#*$", re.M)


def parse(path: Path) -> Tuple[str, List[Tuple[str, str]]]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _parse_docx(path)

    raw = _read_text(path)
    if suffix in (".html", ".htm"):
        title = _html_title(raw) or path.stem
        return title, [(title, clean.html_to_text(raw))]
    if suffix in (".md", ".markdown"):
        return _parse_markdown(raw, path.stem)
    return path.stem, _split_plain(raw, path.stem)


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", "replace")


def _html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return clean.clean_title(re.sub(r"<[^>]+>", " ", match.group(1))) if match else ""


def _split_plain(text: str, stem: str) -> List[Tuple[str, str]]:
    """Split a text file on explicit chapter markers, else treat it as one chapter."""
    parts = re.split(
        r"(?m)^(?=(?:chapter|part|book)\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b)",
        text,
    )
    parts = [p for p in parts if p.strip()]
    if len(parts) <= 1:
        return [(stem, text)]
    chapters = []
    for index, part in enumerate(parts):
        first_line = part.strip().split("\n")[0]
        label = clean.clean_title(first_line)[:80] if len(first_line) < 90 else ""
        chapters.append((label or f"Section {index + 1}", part))
    return chapters


def _parse_markdown(text: str, stem: str) -> Tuple[str, List[Tuple[str, str]]]:
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        return stem, [(stem, re.sub(r"[*_`>]+", "", text))]
    if len(matches) == 1 and matches[0].start() < 20:
        title = clean.clean_title(matches[0].group(1))
        body = text[matches[0].end():]
        return title or stem, [(title or stem, _strip_md(body))]

    title = clean.clean_title(matches[0].group(1)) or stem
    chapters = []
    for index, match in enumerate(matches):
        label = clean.clean_title(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = _strip_md(text[match.end():end])
        if label:
            chapters.append((label, body))
    return title, chapters


def _strip_md(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`>#]+", "", text)
    return text


def _parse_docx(path: Path) -> Tuple[str, List[Tuple[str, str]]]:
    with zipfile.ZipFile(str(path)) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    paragraphs: List[str] = []
    headings: List[Tuple[int, str]] = []
    for paragraph in root.iter(ns + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(ns + "t")).strip()
        if not text:
            continue
        style_node = paragraph.find(f"{ns}pPr/{ns}pStyle")
        style = (style_node.get(ns + "val") if style_node is not None else "") or ""
        if style.lower().startswith("heading") or style.lower() == "title":
            headings.append((len(paragraphs), text))
        paragraphs.append(text)

    title = headings[0][1] if headings else path.stem
    if len(headings) < 2:
        return title, [(title, "\n\n".join(paragraphs))]

    chapters: List[Tuple[str, str]] = []
    for index, (start, label) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(paragraphs)
        body = "\n\n".join(paragraphs[start + 1:end])
        if body.strip():
            chapters.append((label, body))
    return title, chapters
