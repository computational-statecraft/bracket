"""The built-in local engine: llama.cpp's ``llama-server``, started by Bracket as a child process on a free local port
and stopped with it. It speaks the OpenAI chat API, which ``local_llm`` uses.

The packaged app carries the binary in ``<resources>/llama/``. From source, Bracket uses ``BRACKET_LLAMA_SERVER`` or a
``llama-server`` on the PATH; without one, use the Ollama engine instead (see the README).
"""
from __future__ import annotations

import asyncio
import atexit
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from . import config, models

EXE = "llama-server.exe" if os.name == "nt" else "llama-server"
CONTEXT = 4096     # two slots of 2,048 tokens; a request is ~150
SLOTS = 2          # the local tier and a warm-up or check can run side by side

_proc: subprocess.Popen | None = None
_url = ""
_model: Path | None = None
_state = {"state": "off", "detail": ""}
_lock = asyncio.Lock()


def binary() -> Path | None:
    if os.environ.get("BRACKET_LLAMA_SERVER"):
        p = Path(os.environ["BRACKET_LLAMA_SERVER"]).expanduser()
        return p if p.exists() else None
    bundled = config.ROOT / "llama" / EXE
    if bundled.exists():
        return bundled
    found = shutil.which("llama-server")
    return Path(found) if found else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def command(exe: Path, model: Path, port: int) -> list[str]:
    return [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
            "-c", str(CONTEXT), "-np", str(SLOTS), "-ngl", "999"]


def url() -> str:
    return _url


def status() -> dict:
    alive = _proc is not None and _proc.poll() is None
    st = dict(_state)
    if st["state"] == "ready" and not alive:
        st = {"state": "failed", "detail": "the local engine stopped unexpectedly (see logs/llama-server.log)"}
    st.update(binary=str(binary() or ""), model=_model.name if _model else "", url=_url)
    return st


async def ensure() -> dict:
    """Start the engine with the chosen model if it is not already running it. Idempotent."""
    global _proc, _url, _model
    async with _lock:
        want = models.chosen_path()
        exe = binary()
        if exe is None:
            _state.update(state="no-binary", detail="the built-in engine is not part of this install (use the packaged app, or choose Ollama in Settings)")
            return status()
        if want is None:
            _state.update(state="no-model", detail="no model downloaded yet")
            return status()
        if _proc is not None and _proc.poll() is None and _model == want and _state["state"] == "ready":
            return status()
        _stop()
        port = _free_port()
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(config.LOG_DIR / "llama-server.log", "ab")
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}   # CREATE_NO_WINDOW: no console flashes up
        _state.update(state="starting", detail=f"loading {want.name}")
        _url, _model = f"http://127.0.0.1:{port}", want
        for attempt in (0, 1):
            _proc = subprocess.Popen(command(exe, want, port), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(exe.parent), **kw)
            ok = await _wait_healthy(timeout=300)
            # macOS: an app downloaded from the internet and approved with "Open Anyway" may still have its bundled
            # engine refused by Gatekeeper (killed at launch). Clear the download quarantine on bracket's own
            # llama/ folder, and nothing else, then try once more.
            if ok or attempt or sys.platform != "darwin" or _proc.poll() is None or not _unquarantine(exe.parent):
                break
        if ok:
            _state.update(state="ready", detail="")
        else:
            code = _proc.poll()
            _state.update(state="failed", detail=f"llama-server {'exited with code ' + str(code) if code is not None else 'did not become ready'}; see {config.LOG_DIR / 'llama-server.log'}")
            _stop()
        return status()


def _unquarantine(folder: Path) -> bool:
    if folder != config.ROOT / "llama":   # only the engine shipped inside the app
        return False
    try:
        r = subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(folder)], capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


async def _wait_healthy(timeout: float) -> bool:
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=3) as c:
        while time.monotonic() - t0 < timeout:
            if _proc is None or _proc.poll() is not None:
                return False
            try:
                r = await c.get(f"{_url}/health")
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.4)
    return False


def _stop() -> None:
    global _proc
    p, _proc = _proc, None
    if p is None or p.poll() is not None:
        return
    p.terminate()
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()


async def stop() -> None:
    async with _lock:
        _stop()
        _state.update(state="off", detail="")


atexit.register(_stop)
if sys.platform != "win32":
    import signal

    for _sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            _prev = signal.getsignal(_sig)

            def _on_signal(signum, frame, _prev=_prev):
                _stop()
                if callable(_prev):
                    _prev(signum, frame)
                else:
                    raise SystemExit(0)

            signal.signal(_sig, _on_signal)
        except (ValueError, OSError):   # not the main thread: atexit still covers a normal exit
            pass
