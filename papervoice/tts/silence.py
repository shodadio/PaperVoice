"""Silent engine used by the smoke test and as a last-resort fallback.

It produces real, correctly-timed audio (silence) so the whole pipeline -
chunking, concatenation, chapter markers, muxing - can be verified without a
speech model or a Mac.
"""

from __future__ import annotations

import wave
from typing import List

from .base import Engine

_RATE = 24000


class SilenceEngine(Engine):
    name = "silence"
    label = "Silent test track"
    suffix = ".wav"

    @classmethod
    def available(cls) -> bool:
        return True

    @classmethod
    def hint(cls) -> str:
        return "Produces silence of the right length - for testing the pipeline, not for listening."

    @classmethod
    def voices(cls) -> List[dict]:
        return [{"id": "none", "label": "Silence", "locale": "en"}]

    @classmethod
    def default_voice(cls) -> str:
        return "none"

    def synth(self, text: str, out_path: str) -> None:
        seconds = max(0.6, len(text or "") / 14.0)
        frames = int(seconds * _RATE)
        with wave.open(out_path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(_RATE)
            handle.writeframes(b"\x00\x00" * frames)
