"""Text-to-speech engines.

Each engine turns a short string into an audio file. The pipeline normalises
whatever comes out into 24 kHz mono WAV, so an engine only has to be *correct*,
not consistent about format.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Dict, List, Type

from .base import Engine, TTSError
from .kokoro import KokoroEngine
from .say import SayEngine
from .silence import SilenceEngine

_REGISTRY: Dict[str, Type[Engine]] = {
    "kokoro": KokoroEngine,
    "say": SayEngine,
    "silence": SilenceEngine,
}


def installed(name: str) -> bool:
    engine = _REGISTRY.get(name)
    if engine is None:
        return False
    try:
        return engine.available()
    except Exception:
        return False


def default_engine_name() -> str:
    """Prefer the best engine that is actually usable right now."""
    if importlib.util.find_spec("kokoro") is not None and KokoroEngine.available():
        return "kokoro"
    if SayEngine.available():
        return "say"
    if sys.platform == "darwin":
        return "say"
    if KokoroEngine.available():
        return "kokoro"
    return "silence"


def get_engine(name: str = "", voice: str = "", speed: float = 1.0) -> Engine:
    key = (name or "").strip().lower() or default_engine_name()
    engine = _REGISTRY.get(key)
    if engine is None:
        raise TTSError(f"Unknown voice engine '{name}'.")
    if not engine.available():
        hint = engine.hint()
        raise TTSError(f"{engine.label} is not available here. {hint}".strip())
    return engine(voice=voice, speed=speed)


def describe() -> List[dict]:
    out = []
    default = default_engine_name()
    for key, engine in _REGISTRY.items():
        try:
            is_available = engine.available()
            voices = engine.voices() if is_available else []
            device = engine.device_note() if is_available else ""
        except Exception:
            is_available, voices, device = False, [], ""
        out.append(
            {
                "id": key,
                "label": engine.label,
                "available": is_available,
                "hint": engine.hint(),
                "default": key == default,
                "default_voice": engine.default_voice() if is_available else "",
                "device": device,
                "voices": voices,
            }
        )
    return out
