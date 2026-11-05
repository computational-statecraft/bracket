"""Local models for the built-in engine: a short catalog of GGUF files on Hugging Face, a downloader with progress,
resume and checksum, and the choice of which one to run.

Every entry is pinned to a repository commit and a SHA-256, so a download is the exact file listed here or it is
rejected. All entries are Apache-2.0 and ungated: no account or token is needed.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

import httpx

from . import config

GB = 1_000_000_000

# min_ram_gb: the smallest machine the entry is recommended on (the file plus working memory, leaving room for the OS
# and a browser). These are rules of thumb, not measurements: speed and fit vary by machine.
CATALOG: list[dict] = [
    {"id": "gemma-4-e2b", "label": "Gemma 4 E2B", "note": "fastest, lightest; for 8 GB machines",
     "repo": "unsloth/gemma-4-E2B-it-GGUF", "rev": "0314792d7f1f7e229411f620751375812bb9faf2",
     "file": "gemma-4-E2B-it-Q4_K_M.gguf", "bytes": 3106738272,
     "sha256": "740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8", "min_ram_gb": 8},
    {"id": "gemma-4-e4b", "label": "Gemma 4 E4B", "note": "fast, better wording; for 16 GB machines",
     "repo": "unsloth/gemma-4-E4B-it-GGUF", "rev": "bfc15c382204943c3a8fff0c750b94ae2364d7a3",
     "file": "gemma-4-E4B-it-Q4_K_M.gguf", "bytes": 4977171584,
     "sha256": "85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87", "min_ram_gb": 14},
    {"id": "gemma-4-12b", "label": "Gemma 4 12B", "note": "dense; stronger wording, slower than E4B",
     "repo": "unsloth/gemma-4-12b-it-GGUF", "rev": "fc034cfff751157913579611efad8462ac1be606",
     "file": "gemma-4-12b-it-Q4_K_M.gguf", "bytes": 7121861440,
     "sha256": "0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42", "min_ram_gb": 16},
    {"id": "gemma-4-26b-a4b", "label": "Gemma 4 26B A4B", "note": "best wording; mixture of experts, quick for its size; for 32 GB machines",
     "repo": "unsloth/gemma-4-26B-A4B-it-GGUF", "rev": "c099eb48e663fd284577b04978a94ffccb261841",
     "file": "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf", "bytes": 16947541728,
     "sha256": "f2c28b3dc4776931ac6f879e11f203dec637ea0f14267a86ec8f6165f63f293f", "min_ram_gb": 28},
    # tiny, for automated tests of the download and the engine; too weak for a room, so hidden from the setup screen
    {"id": "qwen2.5-0.5b", "label": "Qwen 2.5 0.5B (test)", "note": "for automated tests only", "hidden": True,
     "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "rev": "9217f5db79a29953eb74d5343926648285ec7e67",
     "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf", "bytes": 491400032,
     "sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db", "min_ram_gb": 2},
]
BY_ID = {m["id"]: m for m in CATALOG}
HF = os.environ.get("BRACKET_HF_ENDPOINT", "https://huggingface.co").rstrip("/")


def ram_gb() -> float:
    """Physical memory in GB, or 0 if it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return ms.ullTotalPhys / GB
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GB
    except (ValueError, OSError, AttributeError):
        return 0.0


def recommended(ram: float | None = None) -> str:
    """The largest visible entry the machine is recommended for (the smallest if memory cannot be read)."""
    ram = ram_gb() if ram is None else ram
    fits = [m for m in CATALOG if not m.get("hidden") and m["min_ram_gb"] <= ram + 0.5]
    # between E4B and 26B, prefer E4B on 16–24 GB: the room waits on speed more than on polish
    fits = [m for m in fits if m["id"] != "gemma-4-12b"] or fits
    return (fits[-1] if fits else CATALOG[0])["id"]


def path_of(entry: dict) -> Path:
    return config.MODELS_DIR / entry["file"]


def installed(entry: dict) -> bool:
    p = path_of(entry)
    return p.exists() and p.stat().st_size == entry["bytes"]


def chosen_path() -> Path | None:
    """The GGUF the built-in engine should run: an explicit path, else the chosen catalog entry, else any installed
    entry (largest first). None if nothing is on disk."""
    if config.LOCAL_MODEL_PATH:
        p = Path(config.LOCAL_MODEL_PATH).expanduser()
        return p if p.exists() else None
    e = BY_ID.get(config.LOCAL_MODEL)
    if e and installed(e):
        return path_of(e)
    for e in reversed(CATALOG):
        if not e.get("hidden") and installed(e):
            return path_of(e)
    hidden = [e for e in CATALOG if e.get("hidden") and installed(e)]
    return path_of(hidden[0]) if hidden else None


def chosen_label() -> str:
    p = chosen_path()
    if p is None:
        return ""
    for e in CATALOG:
        if e["file"] == p.name:
            return e["label"]
    return p.stem


# ---------- download ----------

_jobs: dict[str, dict] = {}
_tasks: dict[str, asyncio.Task] = {}


def listing() -> dict:
    ram = ram_gb()
    free = shutil.disk_usage(config.DATA_DIR).free / GB
    rec = recommended(ram)
    out = []
    for e in CATALOG:
        job = _jobs.get(e["id"], {})
        out.append({k: e[k] for k in ("id", "label", "note", "bytes", "min_ram_gb")} | {
            "hidden": bool(e.get("hidden")), "installed": installed(e), "recommended": e["id"] == rec,
            "download": job or None, "license": "Apache-2.0", "source": f"{HF}/{e['repo']}"})
    return {"models": out, "ram_gb": round(ram, 1), "free_gb": round(free, 1), "dir": str(config.MODELS_DIR),
            "chosen": chosen_label(), "custom_path": config.LOCAL_MODEL_PATH}


def start_download(model_id: str) -> dict:
    e = BY_ID.get(model_id)
    if e is None:
        return {"ok": False, "error": f"unknown model {model_id}"}
    if installed(e):
        return {"ok": True, "state": "done"}
    if model_id in _tasks and not _tasks[model_id].done():
        return {"ok": True, "state": "running"}
    have = (path_of(e).with_suffix(".part").stat().st_size if path_of(e).with_suffix(".part").exists() else 0)
    need = (e["bytes"] - have) / GB + 0.2
    free = shutil.disk_usage(config.DATA_DIR).free / GB
    if free < need:
        return {"ok": False, "error": f"not enough disk space: {e['label']} needs {need:.1f} GB more, {free:.1f} GB free"}
    _jobs[model_id] = {"state": "running", "done": have, "total": e["bytes"], "rate": 0, "error": None}
    _tasks[model_id] = asyncio.get_running_loop().create_task(_download(e))
    return {"ok": True, "state": "running"}


def cancel_download(model_id: str) -> dict:
    t = _tasks.get(model_id)
    if t and not t.done():
        t.cancel()
    return {"ok": True}


async def _download(e: dict) -> None:
    job = _jobs[e["id"]]
    dest = path_of(e)
    part = dest.with_suffix(".part")
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{HF}/{e['repo']}/resolve/{e['rev']}/{e['file']}"
    try:
        for attempt in range(6):   # a dropped connection resumes where it stopped
            try:
                await _fetch(url, part, job)
                break
            except (httpx.TransportError, httpx.RemoteProtocolError) as err:
                if attempt == 5:
                    raise
                job["error"] = f"connection dropped ({type(err).__name__}); resuming"
                await asyncio.sleep(2 * (attempt + 1))
        job.update(state="verifying", error=None)
        digest = await asyncio.to_thread(_sha256, part)
        if digest != e["sha256"]:
            part.unlink(missing_ok=True)
            raise ValueError("checksum mismatch: the file was corrupted in transit and has been deleted; try again")
        os.replace(part, dest)
        job.update(state="done", done=e["bytes"])
        if not config.LOCAL_MODEL or not BY_ID.get(config.LOCAL_MODEL) or not installed(BY_ID[config.LOCAL_MODEL]):
            config.write_file({"local_model": e["id"]})   # the first model downloaded becomes the one in use
        if config.LOCAL_ENGINE == "builtin":
            from . import engine

            asyncio.get_running_loop().create_task(engine.ensure())
    except asyncio.CancelledError:
        job.update(state="cancelled", error=None)
        raise
    except Exception as err:  # noqa: BLE001 — shown on the setup screen
        job.update(state="failed", error=str(err)[:240])


async def _fetch(url: str, part: Path, job: dict) -> None:
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, connect=15)) as c:
        async with c.stream("GET", url, headers=headers) as r:
            if r.status_code == 416:   # already complete
                return
            r.raise_for_status()
            mode = "ab" if have and r.status_code == 206 else "wb"
            if mode == "wb":
                have = 0
            job["error"] = None
            t0, base = time.monotonic(), have
            with open(part, mode) as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
                    have += len(chunk)
                    job["done"] = have
                    dt = time.monotonic() - t0
                    if dt > 0.5:
                        job["rate"] = int((have - base) / dt)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def delete(model_id: str) -> dict:
    e = BY_ID.get(model_id)
    if e is None:
        return {"ok": False, "error": f"unknown model {model_id}"}
    cancel_download(model_id)
    for p in (path_of(e), path_of(e).with_suffix(".part")):
        p.unlink(missing_ok=True)
    _jobs.pop(model_id, None)
    return {"ok": True}
