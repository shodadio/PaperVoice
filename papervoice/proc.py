"""The render pipeline: chapters -> chunks -> speech -> one downloadable file."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from . import bundle, clean, store, tts
from .tts.base import TTSError

_RUNNING: Dict[str, threading.Thread] = {}
_CANCEL: Dict[str, threading.Event] = {}
_GUARD = threading.Lock()


class Cancelled(Exception):
    """Raised inside a render thread once the user has cancelled."""


def is_running(book_id: str) -> bool:
    thread = _RUNNING.get(book_id)
    return bool(thread and thread.is_alive())


def cancel(book_id: str) -> bool:
    """Ask a running render to stop. Chapters already finished are kept."""
    stop = _CANCEL.get(book_id)
    if stop is None or not is_running(book_id):
        return False
    stop.set()
    return True


def start(book_id: str) -> None:
    with _GUARD:
        if is_running(book_id):
            raise RuntimeError("This book is already being processed.")
        stop = threading.Event()
        thread = threading.Thread(
            target=run, args=(book_id, stop), name=f"render-{book_id}", daemon=True
        )
        _RUNNING[book_id] = thread
        _CANCEL[book_id] = stop
        thread.start()


def run(book_id: str, stop: Optional[threading.Event] = None) -> None:
    """Synthesise every included chapter, then mux the export files.

    Safe to run twice: chapters whose text and voice are unchanged and whose
    audio already exists are skipped, so an interrupted job resumes.

    Cancelling (see `cancel`) takes effect between chunks. Chapters that are
    already finished keep their audio, so processing again resumes there.
    """
    stop = stop or threading.Event()
    book = store.load(book_id)
    directory = store.book_dir(book_id)
    workdir = directory / "work"
    workdir.mkdir(parents=True, exist_ok=True)

    included = [c for c in book["chapters"] if c.get("include")]
    for chapter in book["chapters"]:
        if not chapter.get("include"):
            chapter["status"] = "skipped"

    try:
        if not included:
            raise TTSError("Select at least one chapter first.")

        engine = tts.get_engine(book.get("engine", ""), book.get("voice", ""), book.get("speed", 1.0))
        book["engine"] = engine.name
        book["voice"] = engine.voice
        book["status"] = "processing"
        book["error"] = ""
        total = max(1, sum(c["chars"] for c in included))
        book["progress"] = {
            "stage": "preparing",
            "done": 0,
            "total": total,
            "chapter": 0,
            "chapters": len(included),
            "eta": None,
        }
        store.save(book)

        started = time.time()
        done = 0
        for position, chapter in enumerate(included, start=1):
            _check(stop)
            text_path = directory / chapter["text_file"]
            text = text_path.read_text(encoding="utf-8")
            stamp = hashlib.sha1(
                f"{text}|{engine.name}|{engine.voice}|{engine.speed}".encode("utf-8")
            ).hexdigest()[:16]
            relative = f"audio/{chapter['idx'] + 1:04d}.wav"
            audio_path = directory / relative

            if audio_path.exists() and chapter.get("sha") == stamp:
                chapter["status"] = "done"
                done += chapter["chars"]
                _progress(book, done, total, position, len(included), chapter["title"], started, "synthesising")
                continue

            chunks = clean.chunk_text(text)
            if not chunks:
                chapter["status"] = "skipped"
                continue
            chapter["status"] = "working"
            _progress(book, done, total, position, len(included), chapter["title"], started, "synthesising")

            parts = []
            for index, chunk in enumerate(chunks):
                _check(stop)
                raw = workdir / f"chunk-{index:04d}{engine.suffix}"
                engine.synth(chunk, str(raw))
                normalized = workdir / f"part-{index:04d}.wav"
                bundle.normalize(raw, normalized)
                raw.unlink(missing_ok=True)
                parts.append(normalized)
                done += len(chunk)
                _progress(book, done, total, position, len(included), chapter["title"], started, "synthesising")

            _check(stop)
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            bundle.build_chapter(parts, audio_path, workdir)
            for part in parts:
                part.unlink(missing_ok=True)

            chapter["audio"] = relative
            chapter["sha"] = stamp
            chapter["status"] = "done"
            store.save(book)

        _progress(book, total, total, len(included), len(included), "", started, "bundling")
        _check(stop)
        chapters_audio = [
            (chapter["title"], directory / chapter["audio"])
            for chapter in included
            if chapter.get("audio") and (directory / chapter["audio"]).exists()
        ]
        written = bundle.export(
            chapters_audio,
            title=book["title"] or "Audiobook",
            out_dir=directory / "export",
            workdir=workdir,
            formats=("m4b", "mp3"),
        )
        book["exports"] = {fmt: path.name for fmt, path in written.items()}
        book["status"] = "done"
        book["progress"] = {
            "stage": "done",
            "done": total,
            "total": total,
            "chapter": len(included),
            "chapters": len(included),
            "eta": 0,
        }
        book["error"] = ""
        store.save(book)
    except Cancelled:
        for chapter in book["chapters"]:
            if chapter.get("status") == "working":
                chapter["status"] = ""
        book["status"] = "ready"
        book["error"] = ""
        progress = book.get("progress") or {}
        progress["stage"] = "cancelled"
        progress["eta"] = None
        book["progress"] = progress
        try:
            store.save(book)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001 - surfaced in the UI
        book["status"] = "error"
        book["error"] = str(exc)[:500]
        progress = book.get("progress") or {}
        progress["stage"] = "error"
        book["progress"] = progress
        try:
            store.save(book)
        except Exception:
            pass
    finally:
        _cleanup(workdir)
        with _GUARD:
            _RUNNING.pop(book_id, None)
            _CANCEL.pop(book_id, None)


def _check(stop: threading.Event) -> None:
    if stop.is_set():
        raise Cancelled()


def _progress(book, done, total, position, count, title, started, stage) -> None:
    elapsed = max(0.001, time.time() - started)
    rate = done / elapsed
    remaining = max(0, total - done)
    progress = {
        "stage": stage,
        "done": min(done, total),
        "total": total,
        "chapter": position,
        "chapters": count,
        "chapterTitle": title,
        "rate": round(rate, 1),
        "eta": int(remaining / rate) if rate > 0.5 else None,
    }
    book["progress"] = progress
    store.save(book)


def _cleanup(workdir: Path) -> None:
    for leftover in workdir.glob("*"):
        if leftover.is_file():
            try:
                leftover.unlink()
            except OSError:
                pass
