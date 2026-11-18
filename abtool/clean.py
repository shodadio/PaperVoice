"""Text cleanup, front-matter detection and sentence chunking.

Everything here is dependency-free: HTML is reduced to text with the stdlib
parser so an EPUB can be read without pulling in an AGPL library.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import List

# Tags that end a run of inline text and start a new paragraph.
_BLOCK = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "header", "footer", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
    "figure", "figcaption", "hr", "dd", "dt", "dl", "td", "th", "aside", "main",
}

# Never text content: scripts, styles, the document head, and navigation chrome.
_SKIP = {"script", "style", "head", "title", "svg", "nav"}

# Chapter titles that are almost never worth narrating.
SKIP_TITLES = {
    "cover", "title page", "titlepage", "half title", "front matter", "frontmatter",
    "copyright", "contents", "table of contents", "toc", "dedication", "epigraph",
    "acknowledgements", "acknowledgments", "index", "also by", "about the author",
    "about the publisher", "colophon", "list of illustrations", "list of figures",
    "list of tables", "foreword by", "notes", "endnotes", "bibliography",
    "advertisement", "credits", "imprint", "permissions",
}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        HTMLParser.__init__(self, convert_charrefs=True)
        self._skip = 0
        self._parts: List[str] = []
        self._buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        if tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _BLOCK:
            self._flush()
        if tag in _SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def _flush(self):
        chunk = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if chunk:
            self._parts.append(chunk)

    def text(self) -> str:
        self._flush()
        return "\n\n".join(self._parts)


def html_to_text(html: str) -> str:
    """Reduce an XHTML/HTML document to normalised plain text."""
    if not html:
        return ""
    parser = _Extractor()
    try:
        parser.feed(html)
        parser.close()
        out = parser.text()
    except Exception:
        out = re.sub(r"<[^>]+>", " ", html)
    return normalize_text(out)


_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_PAGEISH = re.compile(r"^(?:[ivxlcdm]{1,7}|\d{1,4}|\d+\s*\|\s*page|page\s+\d+)$", re.I)


def normalize_text(text: str) -> str:
    """Collapse stray whitespace, reunite hyphenated line breaks, drop page numbers."""
    if not text:
        return ""
    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00a0", " ")
        .replace("\u00ad", "")
        .replace("\t", " ")
    )
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = []
    for line in text.split("\n"):
        stripped = re.sub(r"[ ]{2,}", " ", line).strip()
        if not stripped:
            lines.append("")
            continue
        if len(stripped) < 24 and _PAGEISH.match(stripped):
            continue
        lines.append(stripped)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "no", "vol", "fig", "ch", "pp", "cf", "al", "inc", "ltd", "dept", "approx",
}
_SENT_BREAK = re.compile(r"(?<=[.!?\u2026])[\"'\u201d\u2019)\]]*\s+")


def split_sentences(paragraph: str) -> List[str]:
    """Split a paragraph into sentences, keeping common abbreviations intact."""
    paragraph = paragraph.strip()
    if not paragraph:
        return []
    parts: List[str] = []
    start = 0
    for match in _SENT_BREAK.finditer(paragraph):
        candidate = paragraph[start:match.end()].strip()
        if candidate:
            last = candidate.rstrip(".!?\u2026\"'\u201d\u2019)]").split()[-1:]
            word = last[0].lower() if last else ""
            if word in _ABBREV or (len(word) == 1 and word.isalpha()):
                continue
            parts.append(candidate)
        start = match.end()
    tail = paragraph[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [paragraph]


def _hard_split(sentence: str, limit: int) -> List[str]:
    pieces: List[str] = []
    rest = sentence.strip()
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind(", "), window.rfind("; "), window.rfind(" - "), window.rfind(" "))
        if cut < limit // 3:
            cut = limit
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def chunk_text(text: str, max_chars: int = 400) -> List[str]:
    """Break a chapter into TTS-sized chunks, never mid-sentence if avoidable."""
    chunks: List[str] = []
    for paragraph in re.split(r"\n\s*\n", text or ""):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        current = ""
        for sentence in split_sentences(paragraph):
            if len(sentence) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(_hard_split(sentence, max_chars))
                continue
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= max_chars:
                current = current + " " + sentence
            else:
                chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
    return [c for c in chunks if c.strip()]


def clean_title(title: str) -> str:
    """Tidy a chapter title: drop dot leaders, trailing numbers and stray markup."""
    title = re.sub(r"<[^>]+>", " ", title or "")
    title = re.sub(r"\s+", " ", title).strip(" .\u00b7\u2022-\u2013\u2014\t")
    title = re.sub(r"\.{3,}\s*\d*$", "", title).strip()
    title = re.sub(r"\s+\d{1,4}$", "", title).strip() if len(title) > 8 else title
    return title[:120]


def looks_like_front_matter(title: str, text: str) -> bool:
    """True for sections that are structure rather than content."""
    key = re.sub(r"[^a-z ]", "", (title or "").lower()).strip()
    key = " ".join(key.split())
    if key in SKIP_TITLES:
        return True
    if any(key.startswith(prefix) for prefix in ("also by", "table of contents", "list of ")):
        return True
    body = (text or "").strip()
    if len(body) < 140:
        return True
    # A table of contents: many short lines, most of them ending in a number.
    lines = [ln for ln in body.split("\n") if ln.strip()]
    if len(lines) >= 6:
        dotted = sum(1 for ln in lines if re.search(r"\d$", ln))
        if dotted / len(lines) > 0.7 and sum(len(ln) for ln in lines) / len(lines) < 70:
            return True
    return False


def estimate_seconds(chars: int, chars_per_second: float = 15.0) -> int:
    """Rough narration length: ~15 chars/second is a natural 165 wpm."""
    return int(round((chars or 0) / max(chars_per_second, 1.0)))
