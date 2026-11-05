"""Builds the agreed-language library: downloads the documents in library/sources.json (or takes your own files),
keeps their paragraphs, and writes each document to <folder>/<id>.json for review. The folder is the data folder's
library/ unless --out says otherwise (the release build uses --out library/texts to ship the library in the app).

    python -m backend.library_cli fetch [ids…] [--force] [--topic REGEX] [--out DIR]
    python -m backend.library_cli add FILE --body EU --title "…" --date 2026-06-19 [--url …] [--topic REGEX]
    python -m backend.library_cli list
    python -m backend.library_cli search "words"

The setup screen's "Download" button runs the same fetch. --topic keeps only paragraphs that match a regular
expression (case-insensitive), for a library on one subject.

The text kept is the document's own wording, unedited apart from joining lines broken by the PDF layout; nothing is
summarised or rewritten. Check a document against its source before relying on it in the room.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from . import config

SOURCES = config.ROOT / "library" / "sources.json"
NUM = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+")


# ---------- extraction ----------

class _Blocks(HTMLParser):
    """Text of the block elements a declaration is written in (paragraphs, list items, headings), in order; scripts,
    navigation, headers and footers skipped. An item of a numbered list gets its number."""
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "blockquote", "td"}
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "form", "button", "select"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.buf: list[str] | None = None
        self.depth = 0          # nesting of block elements, so a <p> inside an <li> joins it
        self.skip = 0
        self.lists: list[list] = []   # [ordered, counter]

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("ol", "ul"):
            start = dict(attrs).get("start")
            self.lists.append([tag == "ol", int(start) - 1 if start and start.isdigit() else 0])
        elif tag in self.BLOCK:
            if self.depth == 0:
                self.buf = []
                if tag == "li" and self.lists and self.lists[-1][0]:
                    self.lists[-1][1] += 1
                    self.buf.append(f"{self.lists[-1][1]}. ")
            self.depth += 1
        elif tag == "br" and self.buf is not None:
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("ol", "ul"):
            if self.lists:
                self.lists.pop()
        elif tag in self.BLOCK and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.buf is not None:
                t = " ".join("".join(self.buf).split())
                if t:
                    self.out.append(t)
                self.buf = None

    def handle_data(self, data):
        if self.buf is not None and not self.skip:
            self.buf.append(data)


def html_paragraphs(html: str) -> list[str]:
    p = _Blocks()
    p.feed(html)
    return p.out


_FURNITURE = re.compile(r"^(\s*\d{1,3}\s*|\s*(EUCO|ST|CO EUR|CONCL)\s+[\d/ .A-Z]+.*|\s*EN\s*|\s*-\s*\d+\s*-\s*|\s*Page \d+.*)$")


def pdf_paragraphs(text: str) -> list[str]:
    """Paragraphs from a PDF's text layer: page furniture dropped (page numbers, "EUCO 18/22 … EN" running heads),
    words hyphenated across lines rejoined, and lines joined until a numbered paragraph, a bullet, or a short line
    that ends a sentence."""
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    # running heads and feet repeat on most pages: drop lines seen four times or more, and the usual furniture
    counts: dict[str, int] = {}
    for ln in lines:
        k = ln.strip()
        if k:
            counts[k] = counts.get(k, 0) + 1
    width = max((len(ln) for ln in lines), default=80)
    paras: list[str] = []
    cur = ""
    for ln in lines:
        s = ln.strip()
        if not s:
            if cur:
                paras.append(cur)
                cur = ""
            continue
        if _FURNITURE.match(s) or (counts[s] >= 4 and len(s) < 80):
            continue
        starts = bool(NUM.match(s) or re.match(r"^([•\-–—▪●]|[a-z]\)|\([a-z]\))\s", s))
        if cur and starts:
            paras.append(cur)
            cur = ""
        if cur.endswith("-") and s[:1].islower():
            cur = cur[:-1] + s
        else:
            cur = f"{cur} {s}".strip()
        if re.search(r"[.;:]$", s) and len(ln) < width * 0.75:
            paras.append(cur)
            cur = ""
    if cur:
        paras.append(cur)
    return [" ".join(p.split()) for p in paras if p.strip()]


def number_paragraphs(blocks: list[str]) -> list[dict]:
    """[{n, text}]: n is the document's own paragraph number where it has one, else the number of the last numbered
    paragraph before it with a letter (12a, 12b) or, before any number, its position (p3)."""
    out, last, sub = [], None, 0
    for i, b in enumerate(blocks, 1):
        m = NUM.match(b)
        if m:
            last, sub = m.group(1), 0
            out.append({"n": last, "text": b[m.end():].strip()})
        else:
            sub += 1
            n = f"{last}{chr(96 + min(sub, 26))}" if last else f"p{i}"
            out.append({"n": n, "text": b})
    return out


def keep(paras: list[dict], topic: str | None = None) -> list[dict]:
    """Paragraphs worth quoting: very short blocks are headings, captions or furniture, not language anyone agreed to.
    topic, a regular expression, keeps only the paragraphs that match it."""
    pat = re.compile(topic, re.I) if topic else None
    return [p for p in paras if len(p["text"]) >= 40 and (pat is None or pat.search(p["text"]))]


def extract(data: bytes, kind: str) -> list[str]:
    if kind == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return pdf_paragraphs("\n\n".join(page.extract_text() or "" for page in reader.pages))
    text = data.decode("utf-8", errors="replace")
    if kind == "html":
        return html_paragraphs(text)
    # plain text or Markdown: blank lines separate paragraphs; Markdown emphasis and heading marks dropped
    return [" ".join(re.sub(r"[*_#>]+", " ", b).split()) for b in re.split(r"\n\s*\n", text) if b.strip()]


def kind_of(name: str, data: bytes, content_type: str = "") -> str:
    if data[:5] == b"%PDF-" or "pdf" in content_type or name.lower().endswith(".pdf"):
        return "pdf"
    if "html" in content_type or name.lower().endswith((".htm", ".html")) or data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        return "html"
    return "text"


# ---------- commands ----------

def _write(meta: dict, paras: list[dict], out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{meta['id']}.json"
    path.write_text(json.dumps({**meta, "fetched": date.today().isoformat(), "paragraphs": paras}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def fetch(ids: list[str], force: bool = False, topic: str | None = None, out: Path | None = None, progress=print) -> int:
    """Download the sources into out (default: the data folder's library). Returns the number that failed."""
    import httpx

    out = out or config.USER_LIBRARY
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    if ids:
        sources = [s for s in sources if s["id"] in ids]
    failed = 0
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Bracket agreed-language library", "Accept-Language": "en"}
    with httpx.Client(follow_redirects=True, timeout=40, headers=headers) as client:
        for s in sources:
            path = out / f"{s['id']}.json"
            if (path.exists() or (config.BUNDLED_LIBRARY / path.name).exists()) and not force:
                progress(f"  have     {s['id']}")
                continue
            # publishers move documents: an entry may list fallbacks in "urls"; the first that answers is used
            r, errors = None, []
            for url in [s["url"], *s.get("urls", [])]:
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    s = {**s, "url": url}
                    break
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{url}: {str(e).splitlines()[0][:120]}")
                    r = None
            if r is None:   # report and carry on: one moved document should not stop the rest
                failed += 1
                progress(f"  FAILED   {s['id']}: " + " | ".join(errors))
                continue
            try:
                kind = kind_of(s["url"], r.content, r.headers.get("content-type", ""))
                paras = keep(number_paragraphs(extract(r.content, kind)), topic or s.get("topic"))
            except Exception as e:  # noqa: BLE001
                failed += 1
                progress(f"  FAILED   {s['id']}: could not read {s['url']}: {e}")
                continue
            if not paras:
                failed += 1
                progress(f"  EMPTY    {s['id']}: no paragraph kept ({kind}); check the url in library/sources.json")
                continue
            _write({k: s[k] for k in ("id", "body", "title", "date", "url")}, paras, out)
            progress(f"  fetched  {s['id']}: {len(paras)} paragraphs")
            time.sleep(0.5)
    progress(f"\n{len(sources) - failed} of {len(sources)} documents in {out}.")
    return failed


def add_bytes(data: bytes, name: str, body: str, title: str, when: str, url: str = "", topic: str | None = None, out: Path | None = None) -> dict:
    paras = keep(number_paragraphs(extract(data, kind_of(name, data))), topic)
    if not paras:
        return {"ok": False, "error": f"no paragraph of 40 characters or more{' matching the topic' if topic else ''} in {name}"}
    slug = re.sub(r"[^a-z0-9]+", "-", f"{body}-{when}-{title}".lower()).strip("-")[:60]
    path = _write({"id": slug, "body": body, "title": title, "date": when, "url": url or name}, paras, out or config.USER_LIBRARY)
    return {"ok": True, "id": slug, "paragraphs": len(paras), "path": str(path)}


def add(file: str, body: str, title: str, when: str, url: str, topic: str | None) -> int:
    src = Path(file).expanduser()
    res = add_bytes(src.read_bytes(), src.name, body, title, when, url or str(src), topic)
    print(f"{res['paragraphs']} paragraphs from {src.name} → {res['path']}." if res["ok"] else res["error"])
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.library_cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("ids", nargs="*")
    f.add_argument("--force", action="store_true")
    f.add_argument("--topic", help="keep only paragraphs matching this regular expression")
    f.add_argument("--out", type=Path, help="write here instead of the data folder (the release build: library/texts)")
    f.add_argument("--strict", action="store_true", help="exit non-zero if any source fails")
    a = sub.add_parser("add")
    a.add_argument("file")
    a.add_argument("--body", required=True, help="NATO, EU, G7, G20, or your own label")
    a.add_argument("--title", required=True)
    a.add_argument("--date", required=True, help="YYYY-MM-DD")
    a.add_argument("--url", default="")
    a.add_argument("--topic", help="keep only paragraphs matching this regular expression")
    sub.add_parser("list")
    s = sub.add_parser("search")
    s.add_argument("text")
    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        failed = fetch(args.ids, args.force, args.topic, args.out)
        return 1 if (failed and args.strict) else 0
    if args.cmd == "add":
        return add(args.file, args.body, args.title, args.date, args.url, args.topic)
    from . import library

    lib = library.get()
    if args.cmd == "list":
        for d in sorted(lib.docs.values(), key=lambda d: (d["body"], d["date"])):
            print(f"  {d['body']:<5} {d['date']}  {d['title']}  ({len(d['paragraphs'])} paragraphs)")
        print(f"\n{len(lib.docs)} documents, {lib.size} sentences.")
        return 0
    res = lib.search(args.text)
    for h in res:
        print(f"\n  {h['text']}\n    — {h['cites'][0]['cite']}" + (f" (and {len(h['cites']) - 1} more)" if len(h["cites"]) > 1 else ""))
    if not res:
        print("No precedent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
