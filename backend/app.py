"""Bracket — a drafting table for a room. FastAPI backend; the HTTP API is documented in docs/API.md.

The desktop app (launcher.py) starts this server on 127.0.0.1 and opens it in the browser. From source:
    uv run uvicorn backend.app:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import asyncio
import difflib
import json
import time
from contextlib import asynccontextmanager
from typing import Optional

import os
import sys
import threading

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import cloud_llm, config, draft, engine, lexicon, library, local_llm, models, prompts, store, validate
from .nlp import Sentence, align, split_sentences

FRONT = config.ROOT / "frontend"

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    warm = asyncio.create_task(local_llm.warm())
    # the first lexicon lookup loads spaCy and WordNet (seconds); do it now, not on the room's first hover
    # one after the other, on one thread: the agreed-language index takes a second or two to split and index
    asyncio.get_running_loop().run_in_executor(None, lambda: (lexicon.synonyms("We strengthen ties.", 3, 12), _lexicon_size(), library.get()))
    store.log("session.start", {"version": config.VERSION, "local_engine": config.LOCAL_ENGINE, "local_model": local_llm.model_name(),
                                "cloud": config.CLOUD_ENABLED, "cloud_model": config.CLOUD_MODEL})
    yield
    warm.cancel()
    await engine.stop()


app = FastAPI(title="Bracket", version=config.VERSION, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=FRONT), name="static")

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


@app.middleware("http")
async def _local_only(request: Request, call_next):
    """The server listens on this machine only, but any web page open in the same browser can still send it requests.
    Three checks keep them out: the Host header must name this machine (defeats DNS rebinding); a request the browser
    marks as coming from another site is refused; and every request that changes something must carry the X-Bracket
    header, which a page on another site cannot add without permission this server never grants."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in _LOCAL_HOSTS and os.environ.get("BRACKET_ALLOW_ANY_HOST") != "1":
        return JSONResponse({"error": "bracket only answers requests addressed to this machine"}, status_code=403)
    # browsers label every request with where it came from; a page on another site may not even read-only ask
    # (an EventSource to the Claude tier would spend the user's credit)
    if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
        return JSONResponse({"error": "requests from other websites are refused"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-bracket") != "1":
        return JSONResponse({"error": "missing X-Bracket header"}, status_code=403)
    return await call_next(request)


_LEX_SIZE: int | None = None


def _lexicon_size() -> int:
    global _LEX_SIZE
    if _LEX_SIZE is None:
        _LEX_SIZE = lexicon.lemma_count()
    return _LEX_SIZE


@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


@app.get("/api/status")
async def status():
    snap = store.load_snapshot()
    return {
        "version": config.VERSION,
        "platform": sys.platform,
        "packaged": config.FROZEN,
        "data_dir": str(config.DATA_DIR),
        "org": config.ORG,
        "session": store.SESSION,
        "title": (snap or {}).get("title") or config.DOC_TITLE,   # the saved session's title, else the title setting
        "resumable": len(snap.get("sentences", [])) if snap else 0,
        "prefetch": config.CLAUDE_PREFETCH,
        "lexicon": {"ok": True, "entries": _lexicon_size()},
        "library": library.status(),
        "local": await local_llm.status(),
        "cloud": cloud_llm.status(),
        "time": time.time(),
    }


# ---------- settings, models, library (the setup screen) ----------

@app.get("/api/settings")
def get_settings():
    return {"settings": config.public(), "file": str(config.SETTINGS_FILE)}


@app.post("/api/settings")
async def put_settings(changes: dict):
    """Change settings (only the names in config.SPEC); "" or null removes one. A setting fixed by an environment
    variable keeps the environment's value. The local engine restarts if its settings changed."""
    unknown = [k for k in changes if k not in config.SPEC]
    if unknown:
        return JSONResponse({"error": f"unknown settings: {', '.join(unknown)}"}, status_code=400)
    before = (config.LOCAL_ENGINE, config.LOCAL_MODEL, config.LOCAL_MODEL_PATH)
    config.write_file(changes)
    if (config.LOCAL_ENGINE, config.LOCAL_MODEL, config.LOCAL_MODEL_PATH) != before:
        if config.LOCAL_ENGINE == "builtin":
            asyncio.create_task(engine.ensure())
        else:
            await engine.stop()
    store.log("settings", {k: ("(set)" if k in config.SECRET and v else v) for k, v in changes.items()})
    return {"settings": config.public()}


@app.get("/api/models")
def list_models():
    return {**models.listing(), "engine": engine.status(), "local_engine": config.LOCAL_ENGINE}


@app.post("/api/models/{model_id}/download")
async def download_model(model_id: str):
    res = models.start_download(model_id)
    store.log("model.download", {"model": model_id, **res})
    return JSONResponse(res, status_code=200 if res["ok"] else 400)


@app.post("/api/models/{model_id}/cancel")
def cancel_model(model_id: str):
    return models.cancel_download(model_id)


@app.post("/api/models/{model_id}/use")
async def use_model(model_id: str):
    e = models.BY_ID.get(model_id)
    if not e or not models.installed(e):
        return JSONResponse({"ok": False, "error": "not downloaded"}, status_code=400)
    config.write_file({"local_model": model_id, "local_model_path": None, "local_engine": "builtin"})
    asyncio.create_task(engine.ensure())
    return {"ok": True}


@app.delete("/api/models/{model_id}")
async def delete_model(model_id: str):
    if models.BY_ID.get(model_id) and engine.status()["model"] == models.BY_ID[model_id]["file"]:
        await engine.stop()
    res = models.delete(model_id)
    if config.LOCAL_ENGINE == "builtin":
        asyncio.create_task(engine.ensure())
    return res


_library_job: dict = {"state": "idle", "log": []}


@app.get("/api/library")
def library_status():
    return {**library.status(), "job": _library_job}


@app.post("/api/library/fetch")
def library_fetch(force: bool = False):
    """Download the starter library's documents into the data folder (those the app already ships are skipped)."""
    if _library_job["state"] == "running":
        return _library_job

    def run():
        from . import library_cli

        try:
            failed = library_cli.fetch([], force=force, progress=lambda m: _library_job["log"].append(m.strip()))
            _library_job.update(state="done", failed=failed)
        except Exception as e:  # noqa: BLE001
            _library_job.update(state="failed", error=str(e)[:200])
        library.reset()
        threading.Thread(target=library.get, daemon=True).start()

    _library_job.clear()
    _library_job.update(state="running", log=[])
    threading.Thread(target=run, daemon=True).start()
    return _library_job


@app.post("/api/library/add")
async def library_add(request: Request, name: str, body: str, title: str, date: str, url: str = "", topic: str = ""):
    """Add a document (PDF, HTML, text or Markdown, sent as the raw request body) to this machine's library."""
    from . import library_cli

    data = await request.body()
    if not data:
        return JSONResponse({"ok": False, "error": "empty file"}, status_code=400)
    res = await asyncio.to_thread(library_cli.add_bytes, data, name, body, title, date, url, topic or None)
    if res["ok"]:
        library.reset()
        await asyncio.to_thread(library.get)
    store.log("library.add", {"name": name, "body": body, "title": title, "date": date, **res})
    return JSONResponse(res, status_code=200 if res["ok"] else 400)


_shutdown_hook = None   # set by the launcher, so Quit in the page closes the app


@app.post("/api/shutdown")
async def shutdown():
    store.log("app.quit", {})
    await engine.stop()
    if _shutdown_hook:
        asyncio.get_running_loop().call_later(0.3, _shutdown_hook)
    return {"ok": True, "closing": bool(_shutdown_hook)}


@app.get("/api/local/check")
async def local_check():
    res = await local_llm.check()
    store.log("local.check", res)
    return res


@app.get("/api/cloud/check")
async def cloud_check():
    if not cloud_llm.status()["ok"]:
        return cloud_llm.status()
    res = await cloud_llm.check()
    store.log("cloud.check", res)
    return res


# ---------- document ----------

class SentenceIn(BaseModel):
    id: str
    text: str
    state: str = "draft"
    version: int = 1


class SegmentIn(BaseModel):
    text: str
    sentences: list[SentenceIn] = Field(default_factory=list)
    structured: bool = False  # a pasted draft: keep headings, lead-ins and list items


@app.post("/api/segment")
def segment(body: SegmentIn):
    if body.structured:
        return {"sentences": draft.parse(body.text)}
    old = [Sentence(s.id, s.text, s.state, s.version) for s in body.sentences]
    new = align(split_sentences(body.text), old)
    return {"sentences": [s.__dict__ for s in new]}


class SnapshotIn(BaseModel):
    doc: dict


@app.post("/api/snapshot")
def put_snapshot(body: SnapshotIn):
    store.snapshot(body.doc)
    return {"ok": True}


@app.get("/api/snapshot")
def get_snapshot():
    return {"doc": store.load_snapshot()}


# ---------- tier 0 ----------

class SpanIn(BaseModel):
    sentence: str
    start: int
    end: int


@app.post("/api/synonyms")
def synonyms(body: SpanIn):
    t0 = time.perf_counter()
    res = lexicon.synonyms(body.sentence, body.start, body.end)
    res["ms"] = int((time.perf_counter() - t0) * 1000)
    res["tier"] = "lexical"
    return res


# ---------- tier 1 ----------

class ProposeIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sentence: str
    start: Optional[int] = None  # None = whole sentence
    end: Optional[int] = None
    strength: int = 0
    register_: str = Field("institutional", alias="register")  # "register" shadows a BaseModel attribute
    length: str = "same"
    n: int = 3
    context: list[str] = Field(default_factory=list)
    sentence_id: Optional[str] = None
    target: Optional[str] = None  # the ladder rung the strength dial points at, if any


def _build_body(body: ProposeIn, n: int) -> tuple[str, str]:
    """(request text without the rules, source text being reworded)"""
    if body.start is None or body.end is None:
        return prompts.sentence_body(body.sentence, body.context, n, body.strength, body.register_, body.length, body.target), body.sentence
    span = body.sentence[body.start:body.end]
    return prompts.span_body(body.sentence, span, n, body.strength, body.register_, body.length, body.target, start=body.start), span


def _echoes_sentence(sentence: str, source: str, line: str) -> bool:
    """A small model asked for a span often returns the whole rewritten sentence, which cannot be spliced in."""
    if len(source) > 0.6 * len(sentence):
        return False
    return difflib.SequenceMatcher(None, line.lower(), sentence.lower()).ratio() > 0.7


def _trim_overlap(sentence: str, source: str, line: str, start: int | None = None) -> str:
    """A span proposal that runs into the words around the span ("examined in" for "reviewed" before "in full")
    would repeat them when spliced in; cut the overlap off. Words the span itself contains are kept."""
    start = sentence.find(source) if start is None else start
    if start < 0:
        return line
    before, after = sentence[:start].split(), sentence[start + len(source):].split()
    words, own = line.split(), {w.lower().strip(".,;:") for w in source.split()}
    norm = lambda w: w.lower().strip(".,;:")  # noqa: E731
    for k in range(min(3, len(after), len(words) - 1), 0, -1):
        if [norm(w) for w in words[-k:]] == [norm(w) for w in after[:k]] and norm(words[-1]) not in own:
            words = words[:-k]
            break
    for k in range(min(3, len(before), len(words) - 1), 0, -1):
        if [norm(w) for w in words[:k]] == [norm(w) for w in before[-k:]] and norm(words[0]) not in own:
            words = words[k:]
            break
    return " ".join(words)


def _validated(source: str, lines: list[str], sentence: str, start: int | None = None) -> list[dict]:
    span = source != sentence
    out, seen = [], set()
    for line in lines:
        if span:
            line = _trim_overlap(sentence, source, line, start)
        if not line.strip() or line.strip() == source.strip() or line.lower() in seen:
            continue
        seen.add(line.lower())
        if span and _echoes_sentence(sentence, source, line):
            continue
        v = validate.check(source, line, sentence if span else None)
        if v["ok"]:
            out.append({"text": line, "flags": v["flags"]})
    return out


# ---------- proposals (both tiers, streamed) ----------

@app.get("/api/propose/stream")
async def propose_stream(request: Request, tier: str, sentence: str, strength: int = 0, register: str = "institutional", length: str = "same", start: Optional[int] = None, end: Optional[int] = None, context: str = "", sentence_id: Optional[str] = None, n: int = 3, target: Optional[str] = None, prefetch: bool = False):
    """n proposals from one tier ("local" or "cloud") at the dials, streamed as the model writes: event delta carries
    the text so far, event final the validated options, event error a message the room can read. Both tiers get the
    same short prompt: the rules as the system message, the request as the user message. prefetch=1 marks Claude
    proposals fetched in the background before C was pressed (logged, shown only on C)."""
    body = ProposeIn(sentence=sentence, start=start, end=end, strength=strength, register=register, length=length, n=n, context=[c for c in context.split("\n") if c], sentence_id=sentence_id, target=target)
    req, source = _build_body(body, n)
    cap = prompts.max_tokens(n, start is None)
    kind = "proposal.local" if tier == "local" else "proposal.cloud"
    events = local_llm.stream(prompts.messages(req), cap) if tier == "local" else cloud_llm.stream(req, max_tokens=cap)

    async def gen():
        acc = ""
        try:
            async for ev in events:
                if await request.is_disconnected():
                    break
                if "delta" in ev:
                    acc += ev["delta"]
                    yield f"event: delta\ndata: {json.dumps({'text': acc})}\n\n"
                elif "error" in ev:
                    store.log(kind, {"source": source, "error": ev["error"], "ms": ev.get("ms")}, sentence_id)
                    yield f"event: error\ndata: {json.dumps(ev)}\n\n"
                elif ev.get("done"):
                    raw = prompts.parse_lines(acc, n)
                    options = _validated(source, raw, sentence, start)
                    dials = {"strength": strength, "register": register, "length": length, "target": target}
                    store.log(kind, {"source": source, "whole": start is None, "n": n, "prefetch": prefetch, "dials": dials, "options": options, "raw": raw, "ms": ev["ms"]}, sentence_id)
                    yield f"event: final\ndata: {json.dumps({'options': options, 'ms': ev['ms']})}\n\n"
        except Exception as e:  # noqa: BLE001 — the room sees a message, never a dead stream
            store.log(kind, {"source": source, "error": f"server: {e}"[:300]}, sentence_id)
            yield f"event: error\ndata: {json.dumps({'error': f'server error: {str(e)[:160]}'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------- log ----------

class EventIn(BaseModel):
    kind: str
    sentence_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)


@app.get("/api/precedents")
def precedents(sentence: str, start: Optional[int] = None, end: Optional[int] = None, sentence_id: Optional[str] = None):
    """Agreed language for a sentence or a span of it: precedent sentences from the library, quoted exactly, with sources."""
    t0 = time.perf_counter()
    hits = library.get().search(sentence, start, end) if library.status()["ok"] else []
    ms = int((time.perf_counter() - t0) * 1000)
    store.log("proposal.agreed", {"sentence": sentence, "start": start, "end": end, "ms": ms,
                                  "shown": [{"text": h["text"], "phrase": h["phrase"], "same": h["same"], "cite": h["cites"][0]["cite"]} for h in hits]},
              sentence_id)
    return {"hits": hits, "ms": ms}


@app.post("/api/event")
def event(body: EventIn):
    store.log(body.kind, body.payload, body.sentence_id)
    return {"ok": True}


@app.get("/api/export")
def export(fmt: str = "json"):
    if fmt == "md":
        doc = store.load_snapshot() or {"sentences": []}
        sents = doc.get("sentences", [])
        agreed = sum(1 for s in sents if s.get("state") == "agreed")
        lines = [f"# {doc.get('title') or config.DOC_TITLE or 'Untitled session'}", "", f"Session {store.SESSION} · {len(sents)} sentences · {agreed} agreed", ""]
        lines.append(draft.to_markdown(sents))
        lines += ["", "---", "", "## Record", ""]
        for i, s in enumerate(sents, 1):
            lines.append(f"{i:02d}. [{s.get('state','draft').upper()} · v{s.get('version',1)}] {s['text']}")
            for h in s.get("history", []):
                lines.append(f"    - v{h.get('version')} {h.get('at','')}: {h.get('text','')}")
            for d in s.get("dissents", []):
                lines.append(f"    - DISSENT (v{d.get('version')}, {d.get('who','')}): {d.get('note','')}")
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")
    text, mt = store.export(fmt)
    return PlainTextResponse(text, media_type=mt)
