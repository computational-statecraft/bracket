"""Reword-only validation. A proposal that introduces a named entity absent from the source is dropped.
Numbers, modals, negation and comparatives that change are flagged, not dropped: the room decides.
"""
from __future__ import annotations

import re

from .nlp import nlp

_MODALS = {"may", "might", "can", "could", "should", "shall", "must", "will", "would", "ought"}
_NEG = {"not", "never", "no", "nor", "neither", "n't", "without"}


def _ents(text: str) -> set[str]:
    doc = nlp(text)
    return {e.text.lower() for e in doc.ents if e.label_ not in ("CARDINAL", "ORDINAL", "QUANTITY", "PERCENT", "MONEY", "DATE", "TIME")}


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d[\d,\.]*\b", text)) | {t.lower() for t in re.findall(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|billion)\b", text, re.I)}


_CONTRACTIONS = [(r"\bwon't\b", "will not"), (r"\bshan't\b", "shall not"), (r"\bcan't\b", "can not"), (r"\bcannot\b", "can not"), (r"n't\b", " not")]


def _expand(text: str) -> str:
    t = text.lower().replace("\u2019", "'")
    for pat, rep in _CONTRACTIONS:
        t = re.sub(pat, rep, t)
    return t


def _words(text: str, vocab: set[str]) -> set[str]:
    return {t for t in re.findall(r"[a-z']+", _expand(text)) if t in vocab}


def check(source: str, proposal: str, context: str | None = None) -> dict:
    """Return {'ok': bool, 'flags': [...]} for a proposal replacing `source`.

    `context` is the whole sentence when `source` is a span of it: an entity already named elsewhere in
    the sentence is not new. ok=False means hard-dropped (new named entity). Flags are soft: shown in the rail.
    """
    flags: list[str] = []
    known = (context or source).lower()
    new_ents = {e for e in _ents(proposal) if not re.search(r"\b" + re.escape(e) + r"\b", known)}
    if new_ents:
        return {"ok": False, "flags": [f"new entity: {', '.join(sorted(new_ents))}"]}

    if _numbers(proposal) != _numbers(source):
        flags.append("numbers changed")
    if _words(proposal, _MODALS) != _words(source, _MODALS):
        flags.append("modal shifted")
    if _words(proposal, _NEG) != _words(source, _NEG):
        flags.append("negation changed")
    if len(proposal.split()) > 1.6 * max(1, len(source.split())) + 3:
        flags.append("much longer")
    return {"ok": True, "flags": flags}
