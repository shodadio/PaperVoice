"""Kokoro-82M: open weights, 24 kHz, natural voice, runs on the Apple GPU.

Optional by design. Install it by double-clicking "Install Kokoro Voices.command"
in the tool folder - no terminal needed. The pipeline falls back to macOS `say`
whenever the package is missing, so the tool works before and without it.
"""

from __future__ import annotations

import os
import sys
import wave
from typing import Dict, List

from .base import Engine, TTSError

# Voice id prefix -> Kokoro language code.
_LANG = {
    "a": "a",  # American English
    "b": "b",  # British English
    "e": "e",  # Spanish
    "f": "f",  # French
    "h": "h",  # Hindi
    "i": "i",  # Italian
    "j": "j",  # Japanese
    "p": "p",  # Brazilian Portuguese
    "z": "z",  # Mandarin
}

_VOICES = [
    ("af_heart", "Heart · US female"),
    ("af_bella", "Bella · US female"),
    ("af_nicole", "Nicole · US female (soft)"),
    ("af_sarah", "Sarah · US female"),
    ("af_sky", "Sky · US female"),
    ("am_michael", "Michael · US male"),
    ("am_fenrir", "Fenrir · US male"),
    ("am_puck", "Puck · US male"),
    ("bf_emma", "Emma · UK female"),
    ("bf_isabella", "Isabella · UK female"),
    ("bm_george", "George · UK male"),
    ("bm_fable", "Fable · UK male"),
]


class KokoroEngine(Engine):
    name = "kokoro"
    label = "Kokoro (neural, on-device)"
    suffix = ".wav"
    _pipelines: Dict[str, object] = {}

    @classmethod
    def available(cls) -> bool:
        try:
            import kokoro  # noqa: F401
        except Exception:
            return False
        return True

    @classmethod
    def hint(cls) -> str:
        return (
            "Not installed yet. Double-click \"Install Kokoro Voices.command\" in the tool "
            "folder: free weights, one-time download, runs on the Apple GPU. Until then the "
            "macOS voices are used - slower to set up but instantly available."
        )

    @classmethod
    def voices(cls) -> List[dict]:
        return [{"id": vid, "label": label, "locale": vid[0]} for vid, label in _VOICES]

    @classmethod
    def default_voice(cls) -> str:
        return "af_heart"

    @classmethod
    def _pipeline(cls, lang: str):
        if lang in cls._pipelines:
            return cls._pipelines[lang]
        from kokoro import KPipeline

        device = os.environ.get("ABTOOL_KOKORO_DEVICE")
        if not device:
            device = "mps" if sys.platform == "darwin" else "cpu"
        try:
            pipeline = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device=device)
        except TypeError:
            # Older releases do not take a device argument.
            pipeline = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        cls._pipelines[lang] = pipeline
        return pipeline

    def synth(self, text: str, out_path: str) -> None:
        try:
            import numpy as np

            lang = _LANG.get(self.voice[:1], "a")
            pipeline = self._pipeline(lang)
            pieces = []
            for _graphemes, _phonemes, audio in pipeline(text, voice=self.voice, speed=self.speed):
                if audio is None:
                    continue
                pieces.append(np.asarray(audio, dtype="float32").reshape(-1))
            if not pieces:
                raise TTSError("Kokoro returned no audio for that chunk.")
            samples = np.concatenate(pieces)
            pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
            with wave.open(out_path, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24000)
                handle.writeframes(pcm.tobytes())
        except TTSError:
            raise
        except Exception as exc:  # model download, device, memory
            raise TTSError(f"Kokoro failed: {exc}") from exc
