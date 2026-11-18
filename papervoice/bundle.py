"""Audio assembly: normalise, join, and mux into a chaptered M4B or an MP3."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

RATE = 24000
CHANNELS = 1
LEAD_MS = 700  # small pause before each chapter
GAP_MS = 80  # pause between chunks inside a chapter
BITRATE = "64k"


class AudioError(Exception):
    """Raised when ffmpeg is missing or fails."""


def ffmpeg_path() -> str:
    """A usable ffmpeg: system install first, then the pip-packaged static build."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    raise AudioError(
        "ffmpeg is required to build the audio file. Install it with "
        "`brew install ffmpeg` (or `pip install imageio-ffmpeg`) and try again."
    )


def _run(args: Sequence[str]) -> None:
    result = subprocess.run(list(args), capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        tail = " / ".join(detail[-3:]) if detail else "unknown error"
        raise AudioError(f"ffmpeg failed: {tail[:400]}")


def wav_duration(path: Path) -> float:
    """Exact duration of a canonical WAV without needing ffprobe."""
    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate() or RATE
        return frames / float(rate)


def write_silence(path: Path, milliseconds: int) -> None:
    frames = int(RATE * (milliseconds / 1000.0))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b"\x00\x00" * frames)


def normalize(source: Path, target: Path) -> None:
    """Convert any engine output into 24 kHz mono 16-bit WAV."""
    _run(
        [
            ffmpeg_path(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ar",
            str(RATE),
            "-ac",
            str(CHANNELS),
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )


def concat(inputs: Sequence[Path], target: Path) -> None:
    if not inputs:
        raise AudioError("Nothing to join.")
    listing = target.parent / (target.stem + ".txt")
    lines = []
    for item in inputs:
        escaped = str(Path(item).resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        _run(
            [
                ffmpeg_path(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-ar",
                str(RATE),
                "-ac",
                str(CHANNELS),
                "-c:a",
                "pcm_s16le",
                str(target),
            ]
        )
    finally:
        listing.unlink(missing_ok=True)


def build_chapter(parts: Sequence[Path], target: Path, workdir: Path) -> float:
    """Join chunk audio into one chapter file, with a pause at the start."""
    lead = workdir / "silence-lead.wav"
    if not lead.exists():
        write_silence(lead, LEAD_MS)
    gap = workdir / "silence-gap.wav"
    if not gap.exists():
        write_silence(gap, GAP_MS)

    pieces: List[Path] = [lead]
    for index, part in enumerate(parts):
        pieces.append(part)
        if index != len(parts) - 1:
            pieces.append(gap)
    concat(pieces, target)
    return wav_duration(target)


def _escape(value: str) -> str:
    for char in ("\\", "=", ";", "#", "\n"):
        value = value.replace(char, "\\" + char if char != "\n" else " ")
    return value


def export(
    chapters: Sequence[Tuple[str, Path]],
    title: str,
    out_dir: Path,
    workdir: Path,
    formats: Sequence[str] = ("m4b", "mp3"),
) -> Dict[str, Path]:
    """Join chapter audio and write a chaptered M4B and/or a single MP3."""
    if not chapters:
        raise AudioError("No chapters to export.")

    out_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    full = workdir / "full.wav"
    concat([path for _title, path in chapters], full)

    timeline: List[Tuple[str, int, int]] = []
    cursor = 0.0
    for label, path in chapters:
        duration = wav_duration(path)
        start = int(round(cursor * 1000))
        cursor += duration
        end = int(round(cursor * 1000))
        timeline.append((label or "Chapter", start, max(end, start + 1000)))

    meta = workdir / "chapters.ffmeta"
    lines = [";FFMETADATA1", f"title={_escape(title)}", "artist=papervoice", f"album={_escape(title)}"]
    for label, start, end in timeline:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={_escape(label)}"]
    meta.write_text("\n".join(lines) + "\n", encoding="utf-8")

    written: Dict[str, Path] = {}
    for fmt in formats:
        target = out_dir / f"book.{fmt}"
        if fmt == "m4b":
            _run(
                [
                    ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(full), "-i", str(meta),
                    "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                    "-c:a", "aac", "-b:a", BITRATE, "-ac", str(CHANNELS),
                    "-movflags", "+faststart", "-f", "ipod", str(target),
                ]
            )
        elif fmt == "mp3":
            _run(
                [
                    ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(full),
                    "-c:a", "libmp3lame", "-b:a", BITRATE, "-ac", str(CHANNELS),
                    "-metadata", f"title={title}", "-metadata", "artist=papervoice",
                    "-metadata", f"album={title}", str(target),
                ]
            )
        else:
            continue
        if target.exists() and target.stat().st_size > 0:
            written[fmt] = target

    full.unlink(missing_ok=True)
    if not written:
        raise AudioError("ffmpeg produced no output file.")
    return written


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="papervoice-audio-"))
