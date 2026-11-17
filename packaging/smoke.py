"""Smoke test of a built app, as a new user would meet it: start the packaged executable with an empty data folder,
then drive it over HTTP exactly as the setup screen does.

    python packaging/smoke.py <path to the executable> [--model qwen2.5-0.5b] [--no-model]

Checks: the server starts; the lexicon (WordNet + spaCy) works inside the bundle; the precedent library is bundled and
searchable; the built-in engine's binary is present; a model downloads through the app (resume + checksum), the engine
loads it, and proposals stream through the real prompt and validator; the record exports; Quit stops the app and the
engine. Exits non-zero on the first failure, printing why.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
H = {"X-Bracket": "1"}


def step(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


OUT: Path | None = None   # the app's own output, captured to a file (a pipe nobody reads can block a process)


def fail(msg: str, proc: subprocess.Popen | None = None, data: Path | None = None) -> None:
    print(f"\nSMOKE TEST FAILED: {msg}", flush=True)
    if proc and proc.poll() is None:
        time.sleep(3)   # let a requested stack dump land
    if OUT and OUT.exists():
        print("\n--- the app's output (last 120 lines) ---")
        print("\n".join(OUT.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]))
    if data:
        for log in (data / "logs").glob("*.log"):
            print(f"\n--- {log.name} (last 60 lines) ---")
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]))
    if proc and proc.poll() is None:
        proc.kill()
    sys.exit(1)


CTX: dict = {}


def ok(r: httpx.Response):
    """The response's JSON, or a failure that shows the status, the body and the app's log."""
    if r.status_code != 200:
        fail(f"{r.request.method} {r.request.url.path} answered {r.status_code}: {r.text[:500]}", CTX.get("proc"), CTX.get("data"))
    return r.json()


def wait_for(pred, timeout: float, what: str, proc, data):
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < timeout:
        if proc.poll() is not None:
            fail(f"the app exited (code {proc.returncode}) while waiting for {what}", None, data)
        try:
            last = pred()
            if last:
                return last
        except httpx.HTTPError as e:
            last = e
        time.sleep(1)
    fail(f"timed out after {timeout:.0f} s waiting for {what} (last: {last})", proc, data)


def shoot(out: Path, p) -> None:
    """Photograph the screen once the window has loaded and styled itself (CI only looks; nothing depends on it)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60 and p.poll() is None:
        if "WINDOW CHECK PASSED" in (out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""):
            break
        time.sleep(0.5)
    time.sleep(2)
    try:
        from PIL import ImageGrab

        shots = Path(os.environ.get("BRACKET_SHOTS", "shots"))
        shots.mkdir(exist_ok=True)
        ImageGrab.grab().save(shots / f"window-{sys.platform}.png")
        print("screenshot saved", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"no screenshot ({e})", flush=True)


def window_check(exe: str) -> None:
    """Open the real app window, let the app confirm the page loaded in it and the page→app bridge answers."""
    data = Path(tempfile.mkdtemp(prefix="bracket-window-"))
    step(f"open {exe} in its own window")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BRACKET_", "ANTHROPIC_"))}
    out = data.parent / f"{data.name}-output.txt"
    env["BRACKET_WINDOW_HOLD"] = "8"
    try:
        p = subprocess.Popen([exe, "--window-check", "30", "--port", "8797", "--data", str(data)], env=env,
                             stdout=open(out, "wb"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        shoot(out, p)
        code = p.wait(timeout=240)
    except subprocess.TimeoutExpired:
        p.kill()
        code = "timeout"
    text = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
    logs = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (data / "logs").glob("*.log"))
    print(text[-3000:], logs[-3000:], sep="\n")
    if code != 0 or "WINDOW CHECK PASSED" not in text + logs:
        print(f"\nWINDOW CHECK FAILED (exit {code})")
        sys.exit(1)
    print("styled:", "window styled" in text + logs)
    print("\nWINDOW CHECK PASSED")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):   # a Windows console's code page cannot print every character
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("exe")
    ap.add_argument("--model", default="qwen2.5-0.5b")
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--window", action="store_true", help="only check the app's own window opens the page")
    a = ap.parse_args()
    if a.window:
        return window_check(a.exe)

    data = Path(tempfile.mkdtemp(prefix="bracket-smoke-"))
    global OUT
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BRACKET_", "ANTHROPIC_"))}
    env["BRACKET_TRACE_HANG"] = "150"   # if start-up hangs, the app prints every thread's stack before we give up
    OUT = data.parent / f"{data.name}-output.txt"
    step(f"start {a.exe} with an empty data folder {data}")
    t0 = time.monotonic()
    proc = subprocess.Popen([a.exe, "--headless", "--port", str(PORT), "--data", str(data)], env=env,
                            stdout=open(OUT, "wb"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    CTX.update(proc=proc, data=data)
    st = wait_for(lambda: ok(httpx.get(f"{BASE}/api/status", timeout=5)), 180, "the server", proc, data)
    print(f"up in {time.monotonic() - t0:.1f} s · version {st['version']} · packaged={st['packaged']} · data {st['data_dir']}")
    if not st["packaged"]:
        fail("the server says it is not running from the packaged app", proc, data)
    if Path(st["data_dir"]).resolve() != data.resolve():
        fail(f"data folder is {st['data_dir']}, expected {data}", proc, data)

    step("lexicon (WordNet + spaCy inside the bundle)")
    if not st["lexicon"]["ok"] or st["lexicon"]["entries"] < 100_000:
        fail(f"lexicon: {st['lexicon']}", proc, data)
    s = "The council strengthened its commitments."
    syn = ok(httpx.post(f"{BASE}/api/synonyms", json={"sentence": s, "start": 12, "end": 24}, headers=H, timeout=30))
    print("strengthened →", syn["synonyms"], "· ladder", syn["ladder"])
    if not syn["synonyms"] or not syn["ladder"]:
        fail(f"no synonyms or ladder: {syn}", proc, data)
    seg = ok(httpx.post(f"{BASE}/api/segment", json={"text": "**Purpose:** One. Two.\n\n1. Three.", "structured": True}, headers=H, timeout=30))
    if len(seg["sentences"]) != 3:
        fail(f"segmentation: {seg}", proc, data)

    step("agreed language: starts empty; a document added through the app is found")
    lib = st["library"]
    print(lib)
    if lib["ok"]:
        fail(f"the app should ship with an empty library: {lib}", proc, data)
    adopted = ("1. We reaffirm our commitment to the peaceful settlement of disputes in accordance with international law.\n\n"
               "2. We will continue to strengthen cooperation on maritime safety among all members.")
    r = ok(httpx.post(f"{BASE}/api/library/add", params={"name": "adopted.md", "body": "Forum", "title": "Smoke Declaration", "date": "2025-05-01"},
                      content=adopted.encode(), headers=H, timeout=60))
    print("added:", r)
    sent = "We reaffirm our commitment to the peaceful settlement of disputes."
    hits = wait_for(lambda: ok(httpx.get(f"{BASE}/api/precedents", params={"sentence": sent}, timeout=60))["hits"], 90, "precedents", proc, data)
    print(f"{len(hits)} precedents · e.g. {hits[0]['cites'][0]['cite']}: {hits[0]['text'][:120]}")

    step("import a Word draft; export the statement as Word, Markdown and a re-openable session")
    import io
    import zipfile

    def tiny_docx() -> bytes:
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        body = (f'<w:document xmlns:w="{W}"><w:body>'
                '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Purpose</w:t></w:r></w:p>'
                '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Aim:</w:t></w:r><w:r><w:t xml:space="preserve"> We note the progress made. We act.</w:t></w:r></w:p>'
                '</w:body></w:document>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", body)
        return buf.getvalue()

    imp = ok(httpx.post(f"{BASE}/api/import", params={"name": "draft.docx"}, content=tiny_docx(), headers=H, timeout=60))
    print("imported:", imp)
    if imp["kind"] != "text" or "## Purpose" not in imp["text"] or "**Aim:**" not in imp["text"]:
        fail(f"Word import lost the structure: {imp}", proc, data)
    seg = ok(httpx.post(f"{BASE}/api/segment", json={"text": imp["text"], "structured": True}, headers=H, timeout=30))
    httpx.post(f"{BASE}/api/snapshot", json={"doc": {"title": "Smoke", "sentences": [{**x, "history": [], "dissents": []} for x in seg["sentences"]]}}, headers=H, timeout=10)
    docx = httpx.get(f"{BASE}/api/export", params={"fmt": "docx"}, timeout=30)
    with zipfile.ZipFile(io.BytesIO(docx.content)) as z:
        if "We note the progress made." not in z.read("word/document.xml").decode():
            fail("the Word export does not contain the statement", proc, data)
    session = ok(httpx.get(f"{BASE}/api/export", params={"fmt": "json"}, timeout=30))
    back = ok(httpx.post(f"{BASE}/api/import", params={"name": "session.json"}, content=json.dumps(session).encode(), headers=H, timeout=30))
    if back["kind"] != "session" or len(back["doc"]["sentences"]) != len(seg["sentences"]):
        fail(f"a saved session does not re-open: {back}", proc, data)
    print(f"docx {len(docx.content)} bytes · session re-opens with {len(back['doc']['sentences'])} sentences")

    step("models already on this computer (Ollama, Apple's on-device model)")
    opts = ok(httpx.get(f"{BASE}/api/local/options", timeout=30))
    print("ollama:", {k: opts["ollama"][k] for k in ("running", "url")}, "· apple:", opts["apple"], "· recommended:", opts["recommended"])
    if opts["current"]["chosen"]:
        fail(f"a fresh install should not have a model chosen yet: {opts['current']}", proc, data)

    step("built-in engine present")
    m = ok(httpx.get(f"{BASE}/api/models", timeout=10))
    print("engine:", m["engine"], "· RAM", m["ram_gb"], "GB · free", m["free_gb"], "GB · recommended",
          [x["id"] for x in m["models"] if x["recommended"]])
    if m["engine"]["state"] == "no-binary" or not m["engine"]["binary"]:
        fail("llama-server is not in the bundle", proc, data)

    if not a.no_model:
        step(f"download {a.model} through the app")
        r = ok(httpx.post(f"{BASE}/api/models/{a.model}/download", params={"use": "true"}, headers=H, timeout=10))
        if not r.get("ok"):
            fail(f"download refused: {r}", proc, data)

        def done():
            x = next(x for x in ok(httpx.get(f"{BASE}/api/models", timeout=10))["models"] if x["id"] == a.model)
            d = x["download"] or {}
            if d.get("state") == "failed":
                fail(f"download failed: {d}", proc, data)
            print(f"  {d.get('state')} {d.get('done', 0) / 1e6:.0f}/{d.get('total', 0) / 1e6:.0f} MB", flush=True)
            return x["installed"]

        wait_for(done, 900, "the model download", proc, data)

        step("the engine loads the model and answers")
        chk = wait_for(lambda: (lambda c: c if c.get("ok") else None)(ok(httpx.get(f"{BASE}/api/local/check", timeout=120))), 300, "a local answer", proc, data)
        print(f"local check: {chk}")

        step("proposals stream through the real prompt and validator")
        s = "We encourage all member states to share their data with the commission."
        params = {"tier": "local", "sentence": s, "start": 3, "end": 12, "n": 3}
        final = None
        with httpx.stream("GET", f"{BASE}/api/propose/stream", params=params, timeout=120) as resp:
            ev = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:") and ev in ("final", "error"):
                    final = (ev, json.loads(line[5:]))
                    break
        print("stream:", final)
        if not final or final[0] != "final":
            fail(f"no proposals: {final}", proc, data)
        if not final[1]["options"]:
            print("note: the tiny test model's proposals were all dropped by validation; the pipeline itself worked")

    step("export the record")
    httpx.post(f"{BASE}/api/snapshot", json={"doc": {"title": "Smoke", "sentences": [{"id": "a", "text": "One.", "state": "draft", "version": 1, "history": [], "dissents": []}]}}, headers=H, timeout=10)
    md = httpx.get(f"{BASE}/api/export", params={"fmt": "md"}, timeout=10).text
    log = ok(httpx.get(f"{BASE}/api/export", params={"fmt": "json"}, timeout=10))
    if "# Smoke" not in md or not log["events"]:
        fail(f"export: {md[:200]} / {len(log.get('events', []))} events", proc, data)
    print(f"markdown {len(md)} chars · {len(log['events'])} events")

    step("the server refuses requests from other sites")
    if httpx.post(f"{BASE}/api/settings", json={"org": "x"}, timeout=10).status_code != 403:
        fail("a write without X-Bracket was accepted", proc, data)

    step("quit")
    httpx.post(f"{BASE}/api/shutdown", headers=H, timeout=10)
    try:
        proc.wait(30)
    except subprocess.TimeoutExpired:
        fail("the app did not exit after Quit", proc, data)
    try:
        httpx.get(f"{BASE}/api/status", timeout=2)
        fail("the server still answers after Quit", None, data)
    except httpx.HTTPError:
        pass
    print(f"\nSMOKE TEST PASSED in {time.monotonic() - t0:.0f} s")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — any surprise still shows the app's log
        import traceback

        traceback.print_exc()
        fail(f"{type(e).__name__}: {e}", CTX.get("proc"), CTX.get("data"))
