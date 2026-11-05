"""Agreed language: precedent sentences from adopted texts (``library/texts/*.json`` shipped with the app, plus any fetched
or added on this machine in the data folder's ``library/``), found by
word overlap with the sentence being drafted and shown with their source. Nothing here generates text: every
proposal is a document's own wording, quoted exactly.

Search is lexical (SQLite FTS5, BM25, Porter stems), in memory, a few milliseconds. For a selected span it also tries
to line the precedent up with the draft: the nearest content word on each side of the span is looked for in the
precedent, and the words between them there are offered as the replacement, with the stretch of the draft they
replace ("will look at" → "will carefully consider").
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
import threading
from pathlib import Path

from nltk.stem import PorterStemmer

from . import config

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")
STOP = set("""a an the and or but nor of to in on at by for with from as into onto upon over under than then that this these
those it its is are was were be been being has have had do does did will shall would should can could may might must
we our us ours they their them he she his her i you your who whom which what when where while also all any each
both such so not no very more most other some own same too only just there here about against between through during
before after above below up down out off again further once s""".split())

_porter = PorterStemmer().stem
# a place and its adjective are one term here ("Canada" should meet "Canadian")
KIN = {"russia": "russian", "ukraine": "ukrainian", "belarus": "belarusian", "europe": "european", "georgia": "georgian",
       "moldova": "moldovan", "america": "american", "china": "chinese", "iran": "iranian", "africa": "african",
       "asia": "asian", "india": "indian", "canada": "canadian", "germany": "german", "italy": "italian",
       "japan": "japanese", "france": "french", "brazil": "brazilian", "korea": "korean", "mexico": "mexican",
       "turkey": "turkish", "poland": "polish", "britain": "british", "syria": "syrian", "israel": "israeli",
       "palestine": "palestinian", "arctic": "arctic", "indonesia": "indonesian", "australia": "australian"}
_SAME = {_porter(a): _porter(b) for b, a in KIN.items()}


def _stem(w: str) -> str:
    s = _porter(w)
    return _SAME.get(s, s)


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """(stem, start, end) for each word, possessives dropped: "Allies'" and "Ally's" stem like "ally"."""
    out = []
    for m in WORD.finditer(text):
        w = re.sub(r"['’]s?$", "", m.group().lower())
        out.append((_stem(w), m.start(), m.end()))
    return out


def _content(toks):
    return [t for t in toks if t[0] not in STOP and len(t[0]) > 1]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


class Library:
    def __init__(self, folders: list[Path] | Path | None = None):
        self.docs: dict[str, dict] = {}
        self.groups: list[dict] = []   # one per distinct sentence: {text, toks, stems, cites}
        self.size = 0
        self._lock = threading.Lock()
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("create virtual table u using fts5(text, tokenize='porter unicode61')")
        if folders is None:
            folders = folders_in_use()
        self._load([folders] if isinstance(folders, Path) else folders)

    def _load(self, folders: list[Path]) -> None:
        from .nlp import split_many

        files = _files(folders)
        units = []
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            self.docs[d["id"]] = d
            for p in d["paragraphs"]:
                units.append((d, p))
        seen: dict[str, int] = {}
        for (d, p), sents in zip(units, split_many([p["text"] for _, p in units])):
            for s in sents:
                if len(s) < 25:
                    continue
                self.size += 1
                cite = {"doc": d["id"], "body": d["body"], "title": d["title"], "date": d["date"], "para": p["n"], "url": d.get("url", ""),
                        "cite": f"{d['body']} · {d['title']} ({d['date'][:4]}) ¶{p['n']}"}
                k = _norm(s)
                if k in seen:   # the same words adopted again: one precedent, more citations
                    self.groups[seen[k]]["cites"].append(cite)
                    continue
                seen[k] = len(self.groups)
                toks = _tokens(s)
                self.groups.append({"text": s, "toks": toks, "stems": {t[0] for t in _content(toks)}, "cites": [cite]})
        self.db.executemany("insert into u(rowid, text) values (?, ?)", [(i, g["text"]) for i, g in enumerate(self.groups)])
        for g in self.groups:   # newest first: the latest adoption is the one the room will be asked about
            g["cites"].sort(key=lambda c: c["date"], reverse=True)

    # ---------- search ----------

    def search(self, sentence: str, start: int | None = None, end: int | None = None, k: int = 3) -> list[dict]:
        clean = re.sub(r"[\[\]/]", " ", sentence)   # brackets are the draft's own marks, not words (offsets unchanged)
        toks = _tokens(clean)
        terms = {t[0] for t in _content(toks)}
        words = {re.sub(r"['’]s?$", "", m.group().lower()).strip("-") for m in WORD.finditer(clean)} - STOP
        words = sorted(words | {KIN[w] for w in words if w in KIN} | {w for w, a in KIN.items() if a in words})
        if not terms or not words or not self.groups:
            return []
        q = " OR ".join('"' + w.replace('"', "") + '"' for w in words if w)
        with self._lock:
            rows = self.db.execute("select rowid, bm25(u) from u where u match ? order by bm25(u) limit 80", (q,)).fetchall()
        if not rows:
            return []
        best = -rows[0][1] or 1.0
        span = (start, end) if start is not None and end is not None and end > start else None
        span_stems = [t[0] for t in toks if span and t[1] >= start and t[2] <= end]
        hits = []
        for rowid, score in rows:
            g = self.groups[rowid]
            overlap = len(terms & g["stems"])
            if overlap < min(2, len(terms)):
                continue
            hit = {"text": g["text"], "cites": g["cites"][:6], "also": len(g["cites"]) - 1, "phrase": None, "same": False,
                   "score": round(-score / best + overlap / len(terms), 3)}
            if span:
                if span_stems and _contains(g["toks"], span_stems):
                    hit["same"] = True      # the wording already drafted is agreed language here
                    hit["score"] += 0.8
                else:
                    al = _align(toks, start, end, g["toks"], g["text"])
                    if al:
                        hit.update(al)
                        hit["score"] += 1.0
            hits.append(hit)
        hits.sort(key=lambda h: h["score"], reverse=True)
        out = []
        for h in hits:   # near-identical precedents (one word apart across years) take one place, not three
            if any(difflib.SequenceMatcher(None, h["text"], o["text"]).ratio() > 0.9 for o in out):
                continue
            out.append(h)
            if len(out) == k:
                break
        return out


def _contains(toks, stems: list[str]) -> bool:
    seq = [t[0] for t in toks]
    n = len(stems)
    return any(seq[i:i + n] == stems for i in range(len(seq) - n + 1))


def _align(dtoks, start: int, end: int, ptoks, ptext: str) -> dict | None:
    """The precedent's words between the span's nearest content neighbours, if both are found in it in order."""
    inside = [t for t in dtoks if t[1] >= start and t[2] <= end]
    left = [t for t in _content([t for t in dtoks if t[2] <= start])][-2:][::-1]
    right = [t for t in _content([t for t in dtoks if t[1] >= end])][:2]
    if not left or not right:
        return None
    pst = [t[0] for t in ptoks]
    limit = max(8, 2 * len(inside) + 4)
    for L in left:
        for R in right:
            for i, s in enumerate(pst):
                if s != L[0]:
                    continue
                for j in range(i + 2, min(len(pst), i + 2 + limit)):
                    if pst[j] != R[0]:
                        continue
                    i0 = i   # a name runs on past the anchor ("Russian Federation"): the phrase starts after it
                    while i0 + 1 < j - 1 and ptext[ptoks[i0 + 1][1]].isupper():
                        i0 += 1
                    a, b = ptoks[i0 + 1][1], ptoks[j - 1][2]
                    phrase = ptext[a:b]
                    # what it replaces in the draft: everything between the two anchors there
                    ra, rb = next(t[1] for t in dtoks if t[1] > L[1]), max(t[2] for t in dtoks if t[2] < R[2] and t[1] < R[1])
                    if not phrase.strip() or [t[0] for t in ptoks[i0 + 1:j]] == [t[0] for t in dtoks if ra <= t[1] and t[2] <= rb]:
                        continue
                    return {"phrase": phrase, "pstart": a, "pend": b, "rstart": ra, "rend": rb}
    return None


def folders_in_use() -> list[Path]:
    return [config.BUNDLED_LIBRARY, config.USER_LIBRARY]


def _files(folders: list[Path]) -> list[Path]:
    """Every document once: one fetched or added on this machine wins over the bundled copy with the same id."""
    by_name: dict[str, Path] = {}
    for folder in folders:
        if folder.exists():
            for f in sorted(folder.glob("*.json")):
                by_name[f.name] = f
    return [by_name[k] for k in sorted(by_name)]


_LIB: Library | None = None
_LOADING = threading.Lock()


def get() -> Library:
    global _LIB
    with _LOADING:
        if _LIB is None:
            _LIB = Library()
        return _LIB


def reset() -> None:
    """Drop the index so the next search rebuilds it (after a fetch or an added document)."""
    global _LIB
    with _LOADING:
        _LIB = None


def status() -> dict:
    files = _files(folders_in_use())
    if not files:
        return {"ok": False, "docs": 0, "detail": "empty"}
    lib = _LIB
    bodies = sorted({d["body"] for d in lib.docs.values()}) if lib else []
    return {"ok": True, "docs": len(files), "sentences": lib.size if lib else None, "bodies": bodies, "loaded": lib is not None}
