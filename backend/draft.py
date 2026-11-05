"""The shape of a pasted draft. Drafts arrive as Markdown-ish text: headings, bold lead-ins ("**Purpose:** The
commission ..."), numbered or bulleted items. Bracket edits sentence by sentence, so each block is split into sentences and
the first sentence of a block carries the block's kind and label; the structure is rebuilt on export.

Sentence fields added here: kind ("h" heading, "p" paragraph, "li" list item), label (list marker or lead-in, or None),
brk (True on the first sentence of a block).
"""
from __future__ import annotations

import re
import uuid

from .nlp import split_sentences

_HEADING = re.compile(r"^#{1,6}\s+(.+)$")
_BOLD_LINE = re.compile(r"^(\*\*|__)(.+?)(\*\*|__)\s*$")
_BOLD_LEAD = re.compile(r"^(\*\*|__)(.+?)(\*\*|__)\s*(.+)$")
_NUMBERED = re.compile(r"^(\d{1,3}|[a-zA-Z])[.)]\s+(.+)$")
_BULLET = re.compile(r"^[-*•]\s+(.+)$")


def _plain(text: str) -> str:
    """Drop inline Markdown emphasis and code marks; the room sees words, not syntax."""
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])[*_](?!\s)(.+?)(?<!\s)[*_](?![\w*])", r"\1", text)
    return " ".join(text.replace("`", "").split())


def _block(line: str) -> tuple[str, str | None, str]:
    """(kind, label, text) for one non-empty line."""
    if m := _HEADING.match(line):
        return "h", None, _plain(m.group(1))
    if m := _BOLD_LINE.match(line):
        return "h", None, _plain(m.group(2))
    if m := _NUMBERED.match(line):
        return "li", m.group(1) + ".", _plain(m.group(2))
    if m := _BULLET.match(line):
        return "li", "•", _plain(m.group(1))
    if (m := _BOLD_LEAD.match(line)) and len(m.group(2)) <= 60:
        return "p", _plain(m.group(2)).rstrip(":").strip(), _plain(m.group(4))
    return "p", None, _plain(line)


def parse(text: str) -> list[dict]:
    """Sentences of a pasted draft, one block per non-empty line, with kind/label/brk."""
    out: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind, label, body = _block(line)
        if not body:
            continue
        parts = [body] if kind == "h" else (split_sentences(body) or [body])
        for i, sent in enumerate(parts):
            out.append({"id": uuid.uuid4().hex[:10], "text": sent, "state": "draft", "version": 1,
                        "kind": kind, "label": label if i == 0 else None, "brk": i == 0})
    return out


def to_markdown(sentences: list[dict]) -> str:
    """The statement rebuilt with its structure: headings bold, lead-ins bold, list items numbered."""
    blocks: list[tuple[str, str]] = []  # (kind, text)
    for s in sentences:
        text = s.get("text", "").strip()
        if not text:
            continue
        if s.get("brk", True) or not blocks:
            kind, label = s.get("kind", "p"), s.get("label")
            if kind == "h":
                text = f"**{text}**"
            elif kind == "li":
                text = f"{'-' if label in (None, '•') else label} {text}"
            elif label:
                text = f"**{label}:** {text}"
            blocks.append((kind, text))
        else:
            kind, prev = blocks[-1]
            blocks[-1] = (kind, prev + " " + text)
    out = ""
    for i, (kind, text) in enumerate(blocks):
        if i:
            out += "\n" if kind == "li" and blocks[i - 1][0] == "li" else "\n\n"
        out += text
    return out
