"""Tier 1: the local model, streamed so the first proposal shows while the rest are written.

Three engines, chosen in Settings (``local_engine``):

- ``builtin``: llama.cpp inside the app (``engine.py``), running a model downloaded from the setup screen;
- ``ollama``: an Ollama server you run yourself (``local_url``, default http://127.0.0.1:11434; ``local_model`` is
  the Ollama tag, e.g. ``gemma4:e4b``);
- ``openai``: any server that speaks the OpenAI chat API (LM Studio, llama.cpp, vLLM): ``local_url`` up to ``/v1``,
  ``local_model`` the server's model name;
- ``apple``: Apple's on-device model (Apple Intelligence, macOS 26+), see ``apple_llm``.

Until one is chosen (``local_engine`` unset), the setup screen offers what is already on the computer first.

Speed settings, all aimed at the time between a double-click and the first word on screen: one HTTP client for the
life of the server; the model kept loaded; a small context window; a tight ceiling on the answer; no "thinking".
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import httpx

from . import config
from .prompts import messages as chat, parse_lines, span_body

SAMPLING = {"temperature": 0.6, "top_p": 0.9}
OLLAMA_OPTIONS = {**SAMPLING, "num_ctx": 2048}

_clients: dict = {}


def _http() -> httpx.AsyncClient:
    """One client per event loop (the server has one; doctor and compare make their own)."""
    loop = asyncio.get_running_loop()
    c = _clients.get(loop)
    if c is None or c.is_closed:
        _clients.clear()
        c = _clients[loop] = httpx.AsyncClient(timeout=None)
    return c


OLLAMA_DEFAULT = "http://127.0.0.1:11434"
ENGINE_LABELS = {"builtin": "built in", "ollama": "Ollama", "openai": "local server", "apple": "Apple Intelligence"}


def model_name() -> str:
    if config.LOCAL_ENGINE == "builtin":
        from . import models

        return models.chosen_label() or "no model"
    if config.LOCAL_ENGINE == "apple":
        from . import apple_llm

        return apple_llm.LABEL
    if not config.LOCAL_ENGINE:
        return ""
    return config.LOCAL_MODEL or "(default)"


# Ollama models that cannot write text (embedding models) are not offered
_NOT_CHAT = ("embed", "bge-", "minilm", "rerank")
# when the setup screen preselects one of Ollama's models, these families first: good at instruction-following prose
_PREFER = ("gemma", "qwen", "llama", "mistral", "phi")


async def ollama_models(url: str | None = None) -> dict:
    """What Ollama has on this computer: {'running', 'url', 'models': [{'name', 'size_gb'}]}. Never raises."""
    url = (url or (config.LOCAL_URL if config.LOCAL_ENGINE == "ollama" else "") or OLLAMA_DEFAULT).rstrip("/")
    try:
        r = await _http().get(f"{url}/api/tags", timeout=3)
        r.raise_for_status()
        models = [{"name": m.get("name"), "size_gb": round(m.get("size", 0) / 1e9, 1)}
                  for m in r.json().get("models", []) if m.get("name") and not any(k in m["name"].lower() for k in _NOT_CHAT)]
        return {"running": True, "url": url, "models": models}
    except Exception as e:  # noqa: BLE001 — not installed or not running: an answer, not an error
        return {"running": False, "url": url, "models": [], "error": str(e)[:100]}


def preferred_ollama(models: list[dict]) -> str | None:
    for fam in _PREFER:
        for m in models:
            if fam in m["name"].lower():
                return m["name"]
    return models[0]["name"] if models else None


def _base() -> str:
    if config.LOCAL_ENGINE == "builtin":
        from . import engine

        return engine.url()
    return config.LOCAL_URL


async def status() -> dict:
    eng = config.LOCAL_ENGINE
    if not eng:
        return {"ok": False, "engine": "", "model": "", "state": "unchosen", "error": "not chosen", "detail": "Choose a model on the setup screen."}
    if eng == "apple":
        from . import apple_llm

        st = await asyncio.to_thread(apple_llm.status)
        return {"ok": st["available"], "engine": eng, "model": apple_llm.LABEL, "error": None if st["available"] else "unavailable", "detail": st["reason"]}
    if eng == "off":
        return {"ok": False, "engine": eng, "model": "", "error": "off", "detail": "The local tier is turned off in Settings."}
    if eng == "builtin":
        from . import engine

        st = engine.status()
        return {"ok": st["state"] == "ready", "engine": eng, "model": model_name(), "state": st["state"], "error": None if st["state"] == "ready" else st["state"], "detail": st["detail"]}
    try:
        if eng == "ollama":
            r = await _http().get(f"{config.LOCAL_URL}/api/tags", timeout=4)
            r.raise_for_status()
            names = [m.get("name") for m in r.json().get("models", [])]
        else:
            r = await _http().get(f"{config.LOCAL_URL}/models", timeout=4)
            r.raise_for_status()
            names = [m.get("id") for m in r.json().get("data", [])]
        loaded = (config.LOCAL_MODEL in names) if config.LOCAL_MODEL else bool(names)
        return {"ok": loaded, "engine": eng, "model": model_name(), "available": names,
                "error": None if loaded else "model not installed",
                "detail": "" if loaded else (f"ollama pull {config.LOCAL_MODEL}" if eng == "ollama" else f"the server lists: {', '.join(names) or 'nothing'}")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "engine": eng, "model": model_name(), "error": "not running", "detail": f"No server at {config.LOCAL_URL} ({str(e)[:80]})"}


async def warm() -> None:
    """Start the engine (built-in) and answer one throwaway request with the real rules, so the room's first
    double-click finds the model in memory. Fire-and-forget at startup."""
    try:
        if config.LOCAL_ENGINE == "builtin":
            from . import engine

            st = await engine.ensure()
            if st["state"] != "ready":
                return
        await complete(chat(span_body("We note the progress made.", "note", 3, 0, "institutional", "same")), 1, timeout=180)
    except Exception:  # noqa: BLE001
        pass


_think_field = True   # Ollama: older builds refuse "think": false; then send without it


def _ollama_error(status: int, body: str, model: str) -> str:
    try:
        msg = json.loads(body).get("error", "")
    except ValueError:
        msg = body
    if status == 404 or "not found" in msg:
        return f"{model} is not installed (ollama pull {model})"
    return f"Ollama {status}: {msg[:140]}"


async def stream(msgs: list[dict], max_tokens: int = 200, timeout: float | None = None, model: str | None = None) -> AsyncIterator[dict]:
    """Yield {'delta': str} as the model writes, then {'done': True, 'ms': int}; on failure {'error': str, 'ms': int}.
    timeout bounds the wait for each piece of the answer, so a model that stalls is reported, not waited on."""
    t0 = time.perf_counter()
    ms = lambda: int((time.perf_counter() - t0) * 1000)  # noqa: E731
    limit = timeout or config.LOCAL_TIMEOUT_S
    eng = config.LOCAL_ENGINE
    if eng == "off":
        yield {"error": "the local tier is off", "ms": 0}
        return
    if not eng:
        yield {"error": "no local model chosen yet: choose one on the setup screen", "ms": 0}
        return
    if eng == "builtin":
        from . import engine

        if engine.status()["state"] != "ready":
            st = engine.status()
            yield {"error": {"no-model": "no local model yet: download one on the setup screen",
                             "starting": "the local model is still loading", "no-binary": "the built-in engine is missing from this install"}.get(st["state"], st["detail"] or "the local engine is not running"), "ms": ms()}
            return
    try:
        if eng == "apple":
            from . import apple_llm

            gen = apple_llm.stream(msgs, max_tokens, limit)
        else:
            gen = _ollama(msgs, max_tokens, limit, model) if eng == "ollama" else _openai(msgs, max_tokens, limit, model)
        async for ev in gen:
            if "error" in ev:
                yield {"error": ev["error"], "ms": ms()}
                return
            yield ev
        yield {"done": True, "ms": ms()}
    except httpx.TimeoutException:
        yield {"error": f"the local model took longer than {limit:.0f} s", "ms": ms()}
    except httpx.ConnectError:
        yield {"error": "Ollama is not running (open the Ollama app)" if eng == "ollama" else f"no local server at {_base()}", "ms": ms()}
    except Exception as e:  # noqa: BLE001
        yield {"error": str(e)[:160], "ms": ms()}


async def _ollama(msgs, max_tokens, limit, model) -> AsyncIterator[dict]:
    global _think_field
    model = model or config.LOCAL_MODEL
    for attempt in (0, 1):
        body = {"model": model, "messages": msgs, "stream": True, "keep_alive": -1, "options": {**OLLAMA_OPTIONS, "num_predict": max_tokens}}
        if _think_field:
            body["think"] = False
        async with _http().stream("POST", f"{config.LOCAL_URL}/api/chat", json=body, timeout=httpx.Timeout(limit, connect=4)) as r:
            if r.status_code >= 400:
                text = (await r.aread()).decode(errors="replace")
                if r.status_code == 400 and _think_field and "think" in text.lower() and attempt == 0:
                    _think_field = False
                    continue
                yield {"error": _ollama_error(r.status_code, text, model)}
                return
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("error"):
                    yield {"error": f"Ollama: {ev['error'][:140]}"}
                    return
                piece = ev.get("message", {}).get("content", "")
                if piece:
                    yield {"delta": piece}
                if ev.get("done"):
                    return
        return


async def _openai(msgs, max_tokens, limit, model) -> AsyncIterator[dict]:
    """The OpenAI chat-completions stream: the built-in llama-server, or a server the user runs."""
    builtin = config.LOCAL_ENGINE == "builtin"
    base = _base() + ("/v1" if builtin else "")
    body = {"messages": msgs, "stream": True, "max_tokens": max_tokens, **SAMPLING}
    name = model or ("" if builtin else config.LOCAL_MODEL)
    if name:
        body["model"] = name
    if builtin:
        body["chat_template_kwargs"] = {"enable_thinking": False}   # rewording needs no reasoning
    async with _http().stream("POST", f"{base}/chat/completions", json=body, timeout=httpx.Timeout(limit, connect=4)) as r:
        if r.status_code >= 400:
            text = (await r.aread()).decode(errors="replace")
            yield {"error": f"local server {r.status_code}: {text[:140]}"}
            return
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            ev = json.loads(data)
            if ev.get("error"):
                yield {"error": str(ev["error"])[:160]}
                return
            for ch in ev.get("choices", []):
                piece = (ch.get("delta") or {}).get("content") or ""
                if piece:
                    yield {"delta": piece}


async def complete(msgs: list[dict] | str, n: int, timeout: float | None = None, model: str | None = None, max_tokens: int = 200) -> dict:
    """The whole answer at once, parsed into lines (for checks, doctor and compare)."""
    if isinstance(msgs, str):
        msgs = [{"role": "user", "content": msgs}]
    text, res = "", {"ok": False, "lines": [], "ms": 0, "error": "no answer"}
    async for ev in stream(msgs, max_tokens, timeout, model):
        text = ev["replace"] if "replace" in ev else text + ev.get("delta", "")
        if "error" in ev:
            return {"ok": False, "lines": [], "ms": ev["ms"], "error": ev["error"]}
        if ev.get("done"):
            res = {"ok": True, "lines": parse_lines(text, n), "ms": ev["ms"]}
    return res


async def check() -> dict:
    """A real generation, timed, so "ready" means the model answers, not only that it is configured."""
    if config.LOCAL_ENGINE == "builtin":
        from . import engine

        await engine.ensure()
    st = await status()
    if not st["ok"]:
        return {"ok": False, "engine": st["engine"], "model": st["model"], "state": st.get("state") or st.get("error"), "error": st.get("error"), "detail": st.get("detail")}
    # a generous timeout: the first call after startup may still be loading the model into memory
    res = await complete("Give two other words for: begin\nOne per line, nothing else.", 2, timeout=90, max_tokens=24)
    ok = res["ok"] and bool(res["lines"])
    return {"ok": ok, "engine": st["engine"], "model": st["model"], "ms": res["ms"], "sample": res["lines"], "error": None if ok else (res.get("error") or "empty reply")}
