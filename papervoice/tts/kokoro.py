"""Kokoro-82M: open weights, 24 kHz, natural voice, runs on the Apple GPU.

Optional by design. Install it by double-clicking "Install Kokoro Voices.command"
in the tool folder - no terminal needed. The pipeline falls back to macOS `say`
whenever the package is missing, so the tool works before and without it.
"""

from __future__ import annotations

import os
import wave
from typing import Dict, List

from .base import Engine, TTSError

# Metal has no version of a couple of operations Kokoro's vocoder uses. Kokoro's
# own instructions for Apple Silicon are to let those few steps run on the CPU
# and keep everything else on the GPU, which PyTorch only does when this is set
# before torch is imported. Without it the GPU is refused or the run dies on the
# first unsupported step.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def _metal_available() -> bool:
    """True on an Apple Silicon Mac whose PyTorch can drive the GPU."""
    try:
        import torch

        return bool(torch.backends.mps.is_available())
    except Exception:
        return False


def _model_device(pipeline: object) -> str:
    """The device a built pipeline really ended up on ('mps', 'cpu', '')."""
    device = getattr(getattr(pipeline, "model", None), "device", None)
    return getattr(device, "type", "") if device is not None else ""


def _device_note(device: str, settled: bool = True) -> str:
    if device == "mps":
        return "Narrating on the Apple GPU." if settled else "Will narrate on the Apple GPU."
    if settled:
        return "Narrating on the CPU (the GPU is not being used)."
    return "Will narrate on the CPU."

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
    _devices: Dict[str, str] = {}
    _cpu_only = False

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
    def device_note(cls) -> str:
        """A short, true sentence about the chip Kokoro uses, for the page."""
        for device in cls._devices.values():
            return _device_note(device)
        if cls._cpu_only:
            return _device_note("cpu", settled=False)
        return _device_note("mps" if _metal_available() else "cpu", settled=False)

    @classmethod
    def _pipeline(cls, lang: str):
        if lang in cls._pipelines:
            return cls._pipelines[lang]
        from kokoro import KPipeline

        wanted = (os.environ.get("ABTOOL_KOKORO_DEVICE") or "").strip().lower()
        if cls._cpu_only:
            wanted = "cpu"
        elif not wanted:
            wanted = "mps" if _metal_available() else "cpu"
        try:
            pipeline = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device=wanted)
        except TypeError:
            # kokoro older than 0.9.4 has no device choice at all: always the CPU.
            print("  Kokoro: this copy is too old to use the GPU - using the CPU.")
            print("  Kokoro: run \"Install Kokoro Voices.command\" again to update it.")
            pipeline = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        except RuntimeError as exc:
            if wanted != "mps":
                raise
            print(f"  Kokoro: the Apple GPU would not start ({exc}) - using the CPU.")
            pipeline = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device="cpu")
        device = _model_device(pipeline) or wanted
        cls._devices[lang] = device
        print(f"  Kokoro: {_device_note(device)}")
        cls._pipelines[lang] = pipeline
        return pipeline

    @classmethod
    def _fall_back_to_cpu(cls) -> bool:
        """After a GPU failure, rebuild on the CPU instead of failing the book."""
        on_gpu = "mps" in cls._devices.values()
        if not on_gpu or cls._cpu_only:
            return False
        print("  Kokoro: the Apple GPU failed part-way - continuing on the CPU.")
        cls._cpu_only = True
        cls._pipelines.clear()
        cls._devices.clear()
        return True

    def synth(self, text: str, out_path: str) -> None:
        try:
            self._render(text, out_path)
        except TTSError:
            raise
        except Exception as exc:  # model download, device, memory
            if self._fall_back_to_cpu():
                try:
                    self._render(text, out_path)
                    return
                except Exception as retry:  # noqa: BLE001 - surfaced below
                    raise TTSError(f"Kokoro failed: {retry}") from retry
            raise TTSError(f"Kokoro failed: {exc}") from exc

    def _render(self, text: str, out_path: str) -> None:
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
