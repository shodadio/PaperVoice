"""On-disk library: one directory per document, one JSON file of state."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import clean, ingest

_DATA: Optional[Path] = None
_LOCKS: Dict[str, threading.Lock] = {}
_GUARD = threading.Lock()


def init(data_dir: Path) -> None:
    global _DATA
    _DATA = Path(data_dir).expanduser().resolve()
    (_DATA).mkdir(parents=True, exist_ok=True)
    (_DATA / ".gitignore").write_text("*\n", encoding="utf-8")


def data_dir() -> Path:
    if _DATA is None:
        init(Path.cwd() / "library")
    assert _DATA is not None
    return _DATA


def book_dir(book_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "", book_id)
    if safe != book_id or not safe:
        raise KeyError(book_id)
    return data_dir() / safe


def lock(book_id: str) -> threading.Lock:
    with _GUARD:
        if book_id not in _LOCKS:
            _LOCKS[book_id] = threading.Lock()
        return _LOCKS[book_id]


def new_book(source: Path, original_name: str) -> dict:
    """Ingest `source`, store its text chapter by chapter, return the book record."""
    parsed = ingest.ingest(Path(source))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    book_id = f"{stamp}-{secrets.token_hex(2)}"
    directory = data_dir() / book_id
    (directory / "text").mkdir(parents=True, exist_ok=True)
    (directory / "audio").mkdir(parents=True, exist_ok=True)
    (directory / "export").mkdir(parents=True, exist_ok=True)

    suffix = Path(original_name).suffix.lower() or ".bin"
    try:
        target = directory / ("source" + suffix)
        shutil.copyfile(str(source), str(target))
    except OSError:
        target = None

    chapters = []
    total = 0
    for index, (title, text) in enumerate(parsed.chapters):
        relative = f"text/{index + 1:04d}.txt"
        (directory / relative).write_text(text, encoding="utf-8")
        include = not clean.looks_like_front_matter(title, text)
        chars = len(text)
        total += chars if include else 0
        chapters.append(
            {
                "idx": index,
                "title": title,
                "chars": chars,
                "text_file": relative,
                "include": include,
                "audio": "",
                "sha": "",
                "status": "pending",
            }
        )

    book = {
        "id": book_id,
        "title": parsed.title,
        "source_name": Path(original_name).name,
        "source_file": target.name if target else "",
        "created": datetime.now().isoformat(timespec="seconds"),
        "format": "m4b",
        "engine": "",
        "voice": "",
        "speed": 1.0,
        "status": "ready",
        "error": "",
        "chapters": chapters,
        "progress": {},
        "exports": {},
    }
    save(book)
    return book


def load(book_id: str) -> dict:
    path = book_dir(book_id) / "book.json"
    if not path.exists():
        raise KeyError(book_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save(book: dict) -> None:
    """Write the book's state atomically.

    More than one thread saves the same book (a render reporting progress, the
    page saving a chapter selection), so every write gets its own temporary
    file and writes are serialised. Sharing one temporary name made the second
    writer fail with "No such file or directory" after the first one had
    already renamed it.
    """
    directory = book_dir(book["id"])
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(book, indent=1, ensure_ascii=False)
    with lock(book["id"]):
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(directory),
            prefix=".book.json.",
            suffix=".tmp",
            delete=False,
        )
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, str(directory / "book.json"))
        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise


def all_books() -> List[dict]:
    books = []
    for entry in data_dir().iterdir():
        if not entry.is_dir():
            continue
        try:
            books.append(load(entry.name))
        except (KeyError, json.JSONDecodeError, OSError):
            continue
    books.sort(key=lambda b: b.get("created", ""), reverse=True)
    return books


def remove(book_id: str) -> None:
    shutil.rmtree(str(book_dir(book_id)), ignore_errors=True)


def summary(book: dict) -> dict:
    included = [c for c in book.get("chapters", []) if c.get("include")]
    chars = sum(c["chars"] for c in included)
    chapters = [
        {
            "idx": c["idx"],
            "title": c["title"],
            "chars": c["chars"],
            "include": bool(c.get("include")),
            "status": c.get("status", "pending"),
            "minutes": round(clean.estimate_seconds(c["chars"]) / 60.0, 1),
        }
        for c in book.get("chapters", [])
    ]
    exports = book.get("exports") or {}
    return {
        "id": book["id"],
        "title": book["title"],
        "sourceName": book.get("source_name", ""),
        "created": book.get("created", ""),
        "status": book.get("status", "ready"),
        "error": book.get("error", ""),
        "engine": book.get("engine", ""),
        "voice": book.get("voice", ""),
        "format": book.get("format", "m4b"),
        "chapters": chapters,
        "includedCount": len(included),
        "charsIncluded": chars,
        "minutesEstimate": round(clean.estimate_seconds(chars) / 60.0, 1),
        "progress": book.get("progress") or {},
        "exports": sorted(exports.keys()),
        "sourceFile": book.get("source_file", ""),
    }
