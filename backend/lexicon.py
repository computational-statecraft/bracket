"""Tier 0: the lexical tier. WordNet synonyms filtered by part of speech and inflected to match the
source word's form, plus hand-built strength ladders for the verbs that carry force in institutional prose.

Everything here answers in well under 20 ms once WordNet is warm.
"""
from __future__ import annotations

from functools import lru_cache

import nltk
from lemminflect import getInflection, getLemma
from nltk.corpus import wordnet as wn

from . import config
from .nlp import LOCK, nlp

for _d in config.NLTK_DIRS:
    if str(_d) not in nltk.data.path:
        nltk.data.path.insert(0, str(_d))


def ensure_wordnet() -> None:
    """WordNet ships inside the packaged app. Running from source, it is fetched once into the data folder."""
    try:
        wn.ensure_loaded()
    except LookupError:
        target = config.DATA_DIR / "nltk_data"
        try:
            nltk.download("wordnet", download_dir=str(target), quiet=True, raise_on_error=True)
        except ValueError as e:
            if "proxied" in str(e).lower():   # NLTK will not download through a proxy unless told the proxy is trusted
                raise RuntimeError("WordNet could not be downloaded through this network's proxy. If you trust the proxy, "
                                   "set NLTK_ALLOW_PROXIED_URLOPEN=1 and start again (or use the packaged app, which includes WordNet).") from e
            raise
        wn.ensure_loaded()


ensure_wordnet()

_POS_MAP = {"VERB": wn.VERB, "AUX": wn.VERB, "NOUN": wn.NOUN, "PROPN": wn.NOUN, "ADJ": wn.ADJ, "ADV": wn.ADV}
_UPOS_FOR_LEMMA = {"VERB": "VERB", "AUX": "AUX", "NOUN": "NOUN", "PROPN": "PROPN", "ADJ": "ADJ", "ADV": "ADV"}

# Strength ladders, weakest to strongest. Drawn from practice: the operative verbs of UN resolutions and the
# recommendation verbs of clinical-guideline methodology (GRADE/NICE), edited for institutional prose. There is no
# official ranked list; these are the project's own and meant to be argued with.
# Each ladder is a list of rungs; a rung may hold several near-equivalent forms, the first canonical.
LADDERS: list[list[list[str]]] = [
    [["note"], ["take note of"], ["acknowledge"], ["recognize"], ["affirm"], ["reaffirm"], ["declare"]],
    [["invite"], ["encourage"], ["urge"], ["call on", "call upon"], ["request"], ["require"], ["instruct"], ["direct"]],
    [["welcome"], ["appreciate"], ["commend"], ["endorse"]],
    [["regret"], ["deplore"], ["condemn"], ["strongly condemn"]],
    [["suggest"], ["recommend"], ["strongly recommend"], ["expect"], ["commit to"]],
    [["may"], ["can"], ["should"], ["shall"], ["must"], ["will"]],
    [["consider"], ["intend"], ["aim"], ["undertake"], ["commit"], ["guarantee"]],
    [["hope"], ["seek"], ["pursue"], ["ensure"]],
    [["support"], ["advance"], ["promote"], ["champion"]],
    [["improve"], ["strengthen"], ["transform"]],
    [["allow"], ["enable"], ["empower"]],
    [["widen"], ["expand"], ["maximize"]],
    [["reduce"], ["limit"], ["prevent"], ["prohibit"]],
    [["contribute to"], ["lead"], ["set the standard for"]],
]


def _index_ladders():
    idx: dict[str, tuple[int, int]] = {}
    for li, ladder in enumerate(LADDERS):
        for ri, rung in enumerate(ladder):
            for form in rung:
                idx[form] = (li, ri)
    return idx


_LADDER_INDEX = _index_ladders()


def ladder_for(phrase: str) -> dict | None:
    """Return the strength ladder a phrase sits on, with its current rung, or None."""
    key = " ".join(phrase.lower().split())
    hit = _LADDER_INDEX.get(key)
    if hit is None:
        # try the lemma of a single verb ("encourages" -> "encourage")
        toks = key.split()
        if len(toks) == 1:
            lem = getLemma(toks[0], upos="VERB")
            if lem:
                hit = _LADDER_INDEX.get(lem[0])
    if hit is None:
        return None
    li, ri = hit
    return {"rungs": [r[0] for r in LADDERS[li]], "current": ri}


def _inflect_like(candidate: str, tag: str, upos: str) -> str:
    """Inflect a WordNet lemma (possibly multi-word, underscore-joined) to the source token's tag."""
    words = candidate.split("_")
    # verbs inflect their first word ("let out" -> "lets out"); nouns and adjectives their last
    hi = 0 if upos in ("VERB", "AUX") else len(words) - 1
    head = words[hi]
    if (upos in ("VERB", "AUX") and tag in ("VBD", "VBG", "VBN", "VBZ", "VBP")) or (upos == "NOUN" and tag == "NNS") or (upos == "ADJ" and tag in ("JJR", "JJS")):
        inf = getInflection(head, tag=tag)
        if inf:
            head = inf[0]
    words[hi] = head
    return " ".join(words)


@lru_cache(maxsize=4096)
def _wordnet_candidates(lemma: str, wn_pos: str) -> list[tuple[str, int]]:
    """Synonyms from the senses the word is actually used in. WordNet has no notion of context, so an
    unfiltered list mixes every sense ("strengthen" -> "tone"); keeping only senses where the source word
    has a nonzero corpus count, and candidates with one too, drops most of the noise the room would see."""
    seen: dict[str, int] = {}
    for syn in wn.synsets(lemma, pos=wn_pos):
        own = [lem.count() for lem in syn.lemmas() if lem.name().lower() == lemma.lower()]
        if own and own[0] == 0:
            continue
        for lem in syn.lemmas():
            name = lem.name().lower()
            if name == lemma.lower() or lem.count() == 0:
                continue
            seen[name] = max(seen.get(name, 0), lem.count())
    return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))


def synonyms(sentence: str, start: int, end: int, limit: int = 6) -> dict:
    with LOCK:   # WordNet and spaCy, one thread at a time (see nlp.LOCK)
        return _synonyms(sentence, start, end, limit)


def lemma_count() -> int:
    with LOCK:
        return sum(1 for _ in wn.all_lemma_names())


def _synonyms(sentence: str, start: int, end: int, limit: int = 6) -> dict:
    """Synonyms for the span sentence[start:end]. Single content words get WordNet candidates in the
    right part of speech and inflection; multi-word spans get WordNet multiword entries if any exist.
    """
    span_text = sentence[start:end]
    doc = nlp(sentence)
    span = doc.char_span(start, end, alignment_mode="expand")
    if span is None or len(span) == 0:
        return {"span": span_text, "synonyms": [], "ladder": ladder_for(span_text)}

    if len(span) == 1:
        tok = span[0]
        upos = tok.pos_
        wn_pos = _POS_MAP.get(upos)
        if wn_pos is None or tok.is_stop:
            return {"span": span_text, "synonyms": [], "ladder": ladder_for(span_text), "pos": upos}
        lemma = tok.lemma_.lower()
        cands = _wordnet_candidates(lemma, wn_pos)
        # single words first, then multiword; drop possessives and hyphenated oddities
        cands = [c for c in cands if "'" not in c[0] and "-" not in c[0]]
        cands = sorted(cands, key=lambda kv: ("_" in kv[0], -kv[1]))
        out = []
        for name, _cnt in cands:
            form = _inflect_like(name, tok.tag_, upos)
            if tok.text[:1].isupper():
                form = form[:1].upper() + form[1:]
            if form.lower() != tok.text.lower() and form not in out:
                out.append(form)
            if len(out) >= limit:
                break
        return {"span": span_text, "synonyms": out, "ladder": ladder_for(span_text), "pos": upos}

    # multi-word span: WordNet multiword lemmas, no inflection
    key = "_".join(t.lemma_.lower() for t in span)
    out = []
    for wn_pos in (wn.VERB, wn.NOUN, wn.ADJ, wn.ADV):
        for name, _ in _wordnet_candidates(key, wn_pos):
            form = name.replace("_", " ")
            if form not in out:
                out.append(form)
            if len(out) >= limit:
                break
    # a span's strength lives in its first verb ("encourage every party" -> encourage)
    ladder = ladder_for(span_text)
    if ladder is None:
        for t in span:
            if t.pos_ in ("VERB", "AUX"):
                ladder = ladder_for(t.text)
                break
    return {"span": span_text, "synonyms": out[:limit], "ladder": ladder, "pos": "SPAN"}
