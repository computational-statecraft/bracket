"""Shared spaCy pipeline, sentence segmentation, and alignment of new text to existing sentence IDs."""
from __future__ import annotations

import difflib
import threading
import uuid
from dataclasses import dataclass
from typing import Optional

import en_core_web_sm  # imported, not loaded by name, so the packaged app's bundler sees it

_nlp = en_core_web_sm.load()

# spaCy pipelines and NLTK's WordNet reader are not documented as safe to use from several threads at once, and the
# server warms them up in the background while the first requests arrive. Every use goes through this lock; each
# call takes milliseconds, so the room never notices.
LOCK = threading.RLock()


def nlp(text: str):
    with LOCK:
        return _nlp(text)


def split_sentences(text: str) -> list[str]:
    """Sentence boundaries from spaCy, with whitespace normalized. Empty input yields no sentences."""
    with LOCK:
        doc = _nlp(text.strip())
    out = []
    for s in doc.sents:
        t = " ".join(s.text.split())
        if t:
            out.append(t)
    return out


def split_many(texts: list[str]) -> list[list[str]]:
    """split_sentences for many texts at once (spaCy's batch pipe: much faster than one call each)."""
    # sentence boundaries need only the parser: skipping the tagger, lemmatizer and entities is several times faster.
    # The lock is taken a chunk at a time, so a synonym lookup is never stuck behind a whole library being indexed.
    skip = [p for p in ("tagger", "attribute_ruler", "lemmatizer", "ner") if p in _nlp.pipe_names]
    texts = [t.strip() for t in texts]
    docs = []
    for i in range(0, len(texts), 64):
        with LOCK:
            docs.extend(_nlp.pipe(texts[i:i + 64], disable=skip))
    return [[" ".join(s.text.split()) for s in doc.sents if s.text.strip()] for doc in docs]


@dataclass
class Sentence:
    id: str
    text: str
    state: str = "draft"  # draft | open | agreed
    version: int = 1


def align(new_texts: list[str], old: list[Sentence], threshold: float = 0.55) -> list[Sentence]:
    """Carry stable IDs, state and version from old sentences onto re-segmented text.

    Greedy in document order: each new sentence takes the best unused old sentence whose
    similarity clears the threshold; otherwise it is a new sentence. An old sentence whose text
    changed keeps its ID, is bumped one version, and drops to draft unless it was open.
    """
    used: set[int] = set()
    out: list[Sentence] = []
    for nt in new_texts:
        best_i: Optional[int] = None
        best_r = 0.0
        for i, o in enumerate(old):
            if i in used:
                continue
            r = difflib.SequenceMatcher(None, nt, o.text).ratio()
            if r > best_r:
                best_r, best_i = r, i
        if best_i is not None and best_r >= threshold:
            used.add(best_i)
            o = old[best_i]
            if nt == o.text:
                out.append(Sentence(o.id, nt, o.state, o.version))
            else:
                state = "open" if o.state == "open" else "draft"
                out.append(Sentence(o.id, nt, state, o.version + 1))
        else:
            out.append(Sentence(uuid.uuid4().hex[:10], nt))
    return out
