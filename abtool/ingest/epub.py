"""EPUB reading: spine order plus the navigation document (EPUB3 nav, EPUB2 NCX)."""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .. import clean

_HEADING = re.compile(r"<h([12])[^>]*>(.*?)</h\1>", re.I | re.S)


def parse(path: Path) -> Tuple[str, List[Tuple[str, str]]]:
    with zipfile.ZipFile(str(path)) as archive:
        opf_path = _find_opf(archive)
        opf = ET.fromstring(archive.read(opf_path))
        base = posixpath.dirname(opf_path)

        title = _first_text(opf, ".//{*}metadata/{*}title") or Path(path).stem
        items = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            if item.get("id"):
                items[item.get("id")] = item
        spine = []
        for ref in opf.findall(".//{*}spine/{*}itemref"):
            item = items.get(ref.get("idref") or "")
            if item is not None and item.get("href"):
                spine.append(item)

        toc = _toc_titles(archive, opf, items, base)
        chapters = _assemble(archive, spine, base, toc)

    return title, chapters


def _find_opf(archive: zipfile.ZipFile) -> str:
    try:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is not None and rootfile.get("full-path"):
            return rootfile.get("full-path")
    except (KeyError, ET.ParseError):
        pass
    for name in archive.namelist():
        if name.lower().endswith(".opf"):
            return name
    raise ValueError("This EPUB has no package document (container.xml).")


def _first_text(node, selector: str) -> str:
    found = node.find(selector)
    if found is None:
        return ""
    return re.sub(r"\s+", " ", "".join(found.itertext())).strip()


def _norm(base: str, href: str) -> str:
    href = unquote(href.split("#")[0])
    return posixpath.normpath(posixpath.join(base, href)).lstrip("/")


def _toc_titles(archive, opf, items, base: str) -> Dict[str, str]:
    """Map spine document path -> chapter title, preferring the EPUB3 nav document."""
    titles: Dict[str, str] = {}

    nav_item = None
    for item in items.values():
        if "nav" in (item.get("properties") or "").split():
            nav_item = item
            break

    if nav_item is not None and nav_item.get("href"):
        try:
            html = archive.read(_norm(base, nav_item.get("href"))).decode("utf-8", "replace")
            for href, label in _parse_nav(html):
                target = _norm(posixpath.dirname(_norm(base, nav_item.get("href"))), href)
                titles.setdefault(target, label)
        except (KeyError, ET.ParseError):
            pass

    if not titles:
        ncx = None
        for item in items.values():
            if (item.get("media-type") or "").endswith("dtbncx+xml"):
                ncx = item
                break
        if ncx is None:
            for ref in opf.findall(".//{*}spine"):
                if ref.get("toc"):
                    ncx = items.get(ref.get("toc"))
                    break
        if ncx is not None and ncx.get("href"):
            try:
                ncx_base = posixpath.dirname(_norm(base, ncx.get("href")))
                root = ET.fromstring(archive.read(_norm(base, ncx.get("href"))))
                for point in root.findall(".//{*}navPoint"):
                    label = ""
                    text_node = point.find(".//{*}navLabel/{*}text")
                    if text_node is not None:
                        label = re.sub(r"\s+", " ", "".join(text_node.itertext())).strip()
                    content = point.find("{*}content")
                    if content is not None and content.get("src") and label:
                        titles.setdefault(_norm(ncx_base, content.get("src")), label)
            except (KeyError, ET.ParseError):
                pass

    return titles


def _parse_nav(html: str) -> List[Tuple[str, str]]:
    """Pull (href, label) pairs out of an EPUB3 nav document's toc list."""
    pairs: List[Tuple[str, str]] = []
    match = re.search(r"<nav[^>]*epub:type\s*=\s*[\"']toc[\"'][^>]*>(.*?)</nav>", html, re.I | re.S)
    body = match.group(1) if match else html
    for href, inner in re.findall(r"<a[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", body, re.I | re.S):
        label = clean.clean_title(re.sub(r"<[^>]+>", " ", inner))
        if label:
            pairs.append((href, label))
    return pairs


def _assemble(archive, spine, base: str, toc: Dict[str, str]) -> List[Tuple[str, str]]:
    """Walk the spine, starting a new chapter at every document named by the TOC."""
    chapters: List[Tuple[str, str]] = []
    current_title: Optional[str] = None
    current_parts: List[str] = []
    section_no = 0

    def flush():
        nonlocal current_title, current_parts
        if current_parts:
            chapters.append((current_title or f"Section {section_no}", "\n\n".join(current_parts)))
        current_parts = []

    for item in spine:
        path = _norm(base, item.get("href") or "")
        try:
            raw = archive.read(path).decode("utf-8", "replace")
        except KeyError:
            continue

        named = toc.get(path)
        if named:
            flush()
            current_title = named
            current_parts = [clean.html_to_text(raw)]
            section_no += 1
            continue

        text = clean.html_to_text(raw)
        if not text:
            continue
        if current_title is None:
            # Front matter before the first TOC entry: split on headings if any.
            chunks = _split_by_headings(raw)
            if len(chunks) > 1:
                for heading, body in chunks:
                    section_no += 1
                    chapters.append((heading or f"Section {section_no}", body))
            else:
                current_title = _document_title(raw)
                current_parts = [text]
                section_no += 1
        else:
            current_parts.append(text)

    flush()
    return [(t, body) for t, body in chapters if body.strip()]


def _document_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if match:
        label = clean.clean_title(re.sub(r"<[^>]+>", " ", match.group(1)))
        if label:
            return label
    return ""


def _split_by_headings(html: str) -> List[Tuple[str, str]]:
    """Fallback for books with no usable TOC: cut a long document at h1/h2 tags."""
    matches = list(_HEADING.finditer(html))
    if not matches:
        return []
    out: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        heading = clean.clean_title(re.sub(r"<[^>]+>", " ", match.group(2)))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        body = clean.html_to_text(html[match.end():end])
        if heading:
            out.append((heading, body))
    return out
