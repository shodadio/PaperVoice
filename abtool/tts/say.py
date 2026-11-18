"""macOS `say`: zero setup, no model download, roughly 190x realtime."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import List

from .base import Engine, TTSError

_LINE = re.compile(r"^(.+?)\s{2,}([a-z]{2}[-_][A-Za-z]{2,4})(?:\s|$)")
_cache: List[dict] = []


class SayEngine(Engine):
    name = "say"
    label = "macOS voices"
    suffix = ".aiff"

    @classmethod
    def available(cls) -> bool:
        return sys.platform == "darwin" and bool(shutil.which("say"))

    @classmethod
    def hint(cls) -> str:
        if sys.platform != "darwin":
            return "Only available on macOS."
        return "Built into macOS. Instant, no download, robotic but usable."

    @classmethod
    def voices(cls) -> List[dict]:
        global _cache
        if _cache:
            return _cache
        if not cls.available():
            return []
        try:
            result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return []
        voices: List[dict] = []
        for line in result.stdout.splitlines():
            match = _LINE.match(line.strip())
            if not match:
                continue
            name, locale = match.group(1).strip(), match.group(2).replace("_", "-")
            voices.append({"id": name, "label": f"{name} · {locale}", "locale": locale})
        voices.sort(key=lambda v: (0 if v["locale"].lower().startswith("en") else 1, v["id"]))
        _cache = voices
        return voices

    @classmethod
    def default_voice(cls) -> str:
        for candidate in ("Samantha", "Ava", "Allison", "Alex", "Daniel", "Karen"):
            if any(v["id"] == candidate for v in cls.voices()):
                return candidate
        voices = cls.voices()
        return voices[0]["id"] if voices else ""

    def synth(self, text: str, out_path: str) -> None:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            with handle as fh:
                fh.write(text)
            command = [
                "say",
                "-f",
                handle.name,
                "-o",
                out_path,
                "-r",
                str(max(90, int(180 * self.speed))),
            ]
            if self.voice:
                command += ["-v", self.voice]
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
            if result.returncode != 0 or not os.path.exists(out_path):
                raise TTSError(
                    (result.stderr or "").strip()[:300] or "macOS say could not synthesise that text."
                )
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
