"""Shared engine interface."""

from __future__ import annotations

from typing import List


class TTSError(Exception):
    """A synthesis problem worth showing the user."""


class Engine:
    name = "base"
    label = "Base engine"
    suffix = ".wav"  # what `synth` writes; the pipeline converts from here

    def __init__(self, voice: str = "", speed: float = 1.0) -> None:
        self.voice = (voice or "").strip() or self.default_voice()
        try:
            self.speed = min(2.5, max(0.5, float(speed or 1.0)))
        except (TypeError, ValueError):
            self.speed = 1.0

    @classmethod
    def available(cls) -> bool:
        return False

    @classmethod
    def hint(cls) -> str:
        return ""

    @classmethod
    def device_note(cls) -> str:
        """Short sentence about the chip this engine uses, or "" if it has none."""
        return ""

    @classmethod
    def default_voice(cls) -> str:
        voices = cls.voices()
        return voices[0]["id"] if voices else ""

    @classmethod
    def voices(cls) -> List[dict]:
        return []

    def synth(self, text: str, out_path: str) -> None:
        raise NotImplementedError
