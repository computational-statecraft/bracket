"""Apple's on-device model: the system foundation model behind Apple Intelligence, through Apple's Foundation Models
SDK for Python (``apple-fm-sdk``, github.com/apple/python-apple-fm-sdk, Apache-2.0).

It needs macOS 26 or later on a Mac that supports Apple Intelligence, with Apple Intelligence turned on. Everywhere
else ``status()`` says why it is unavailable and the setup screen shows that reason. The model runs on the Mac; no
text leaves it.

The SDK streams cumulative snapshots (the whole answer so far), not pieces; ``stream`` turns them into the
``{'delta': …}`` events the rest of bracket expects.
"""
from __future__ import annotations

import asyncio
import platform
import sys
import time
from typing import AsyncIterator

LABEL = "Apple on-device model"
_cache: dict = {"t": 0.0, "v": None}

_REASONS = {
    "APPLE_INTELLIGENCE_NOT_ENABLED": "Apple Intelligence is turned off: turn it on in System Settings → Apple Intelligence & Siri",
    "DEVICE_NOT_ELIGIBLE": "this Mac cannot run Apple Intelligence",
    "MODEL_NOT_READY": "Apple's model is still downloading or preparing; try again in a while",
}


def _macos_major() -> int:
    try:
        return int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return 0


def _sdk():
    import apple_fm_sdk as fm  # noqa: PLC0415 — optional, macOS only

    return fm


def status(max_age: float = 30.0) -> dict:
    """{'available': bool, 'reason': str}. Cached briefly: the setup screen asks often."""
    if _cache["v"] is not None and time.monotonic() - _cache["t"] < max_age:
        return _cache["v"]
    v = _status()
    _cache.update(t=time.monotonic(), v=v)
    return v


def _status() -> dict:
    if sys.platform != "darwin":
        return {"available": False, "reason": "only on a Mac"}
    if 0 < _macos_major() < 26:
        return {"available": False, "reason": f"needs macOS 26 or later (this Mac runs macOS {platform.mac_ver()[0]})"}
    try:
        fm = _sdk()
    except ImportError:
        return {"available": False, "reason": "not included in this copy of bracket"}
    except OSError as e:   # the SDK's library could not load: usually an older macOS
        return {"available": False, "reason": f"Apple's framework could not be loaded ({str(e)[:80]})"}
    try:
        ok, reason = fm.SystemLanguageModel().is_available()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"could not check ({str(e)[:100]})"}
    if ok:
        return {"available": True, "reason": ""}
    name = getattr(reason, "name", str(reason))
    return {"available": False, "reason": _REASONS.get(name, f"unavailable ({name})")}


def _message(e: Exception) -> str:
    kind = type(e).__name__
    if kind in ("GuardrailViolationError", "RefusalError"):
        return "Apple's model declined this text (its built-in content filter)"
    if kind == "AssetsUnavailableError":
        return _REASONS["MODEL_NOT_READY"]
    if kind == "RateLimitedError":
        return "Apple's model is busy; try again in a moment"
    return f"Apple's model: {str(e)[:140] or kind}"


async def stream(msgs: list[dict], max_tokens: int, limit: float) -> AsyncIterator[dict]:
    """Yield {'delta': str} pieces, or {'replace': str} if the model revised what it had written, or {'error': str}.
    The caller adds {'done': True}. limit bounds the wait for each new piece of text."""
    st = status()
    if not st["available"]:
        yield {"error": f"{LABEL}: {st['reason']}"}
        return
    fm = _sdk()
    instructions = "\n".join(m["content"] for m in msgs if m["role"] == "system") or None
    prompt = "\n".join(m["content"] for m in msgs if m["role"] != "system")
    try:
        # the permissive setting is Apple's own for content transformations, which rewording is
        model = fm.SystemLanguageModel(guardrails=fm.SystemLanguageModelGuardrails.PERMISSIVE_CONTENT_TRANSFORMATIONS)
        session = fm.LanguageModelSession(instructions=instructions, model=model)   # one per request: no shared state
        options = fm.GenerationOptions(temperature=0.6, maximum_response_tokens=max_tokens)
        snapshots = session.stream_response(prompt, options=options).__aiter__()
        sent = ""
        while True:
            try:
                snap = await asyncio.wait_for(snapshots.__anext__(), timeout=limit)
            except StopAsyncIteration:
                return
            snap = str(snap)
            if snap.startswith(sent):
                if len(snap) > len(sent):
                    yield {"delta": snap[len(sent):]}
            else:
                yield {"replace": snap}
            sent = snap
    except asyncio.TimeoutError:
        yield {"error": f"{LABEL} took longer than {limit:.0f} s"}
    except Exception as e:  # noqa: BLE001 — the room sees a sentence, not a traceback
        yield {"error": _message(e)}
