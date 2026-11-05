"""One short prompt for both models: the rules as a system message, the request as the user message. Short because the
local model reads every token of it before it writes a word (on an M1, worked examples doubled Gemma's time:
1.8 s against 0.8 s)."""
from __future__ import annotations

import re

REGISTERS = ["plain", "institutional", "formal"]
LENGTHS = ["shorter", "same", "longer"]

RULES = (
    "You reword text for a committee drafting a shared statement. Keep the meaning, subject and polarity; add no claims, "
    "facts, names, numbers or commitments. Leave [bracketed] text exactly as it is. US English. "
    "Reply with the alternatives only, one per line: no numbering, quotes or comments."
)


def strength_text(strength: int, target: str | None = None) -> str:
    """The strength dial runs -1..2 without a ladder, but across a ladder's full length (e.g. -3..+6) with one."""
    if strength <= -2:
        s = "much weaker"
    else:
        s = {-1: "slightly weaker", 0: "unchanged", 1: "slightly stronger"}.get(strength, "much stronger")
    if target and strength:
        s += f' (the force of "{target}")'
    return s


def dial_text(strength: int, register: str, length: str, target: str | None = None) -> str:
    r = {"plain": "plain", "institutional": "institutional", "formal": "formal diplomatic"}[register]
    return f"Strength: {strength_text(strength, target)}. Register: {r}. Length: {length}."


def span_body(sentence: str, span: str, n: int, strength: int, register: str, length: str, target: str | None = None,
              start: int | None = None) -> str:
    """The span is marked where it sits and its neighbours are named, so a model cannot mistake where it ends
    ("reviewed in" for "reviewed") and repeat the word that follows."""
    start = sentence.find(span) if start is None else start
    end = start + len(span)
    before, after = sentence[:start].split(), sentence[end:].split()
    edges = " and ".join(([f'after "{before[-1]}"'] if before else []) + ([f'before "{after[0]}"'] if after else []))
    return (
        f"{sentence[:start]}⟦{span}⟧{sentence[end:]}\n"
        f"Replace only ⟦{span}⟧" + (f"; it sits {edges}, which stay: do not repeat them" if edges else "") + ".\n"
        f"{dial_text(strength, register, length, target)}\n"
        f"{n} alternatives."
    )


def sentence_body(sentence: str, context: list[str], n: int, strength: int, register: str, length: str, target: str | None = None) -> str:
    ctx = f"Context (do not reword): {' … '.join(context)}\n" if context else ""
    return f"{ctx}Rewrite: {sentence}\n{dial_text(strength, register, length, target)}\n{n} alternatives, varied in structure."


def messages(body: str) -> list[dict]:
    """The local model's chat: the rules as a system message, then the request. Claude gets the same two parts."""
    return [{"role": "system", "content": RULES}, {"role": "user", "content": body}]


def max_tokens(n: int, whole: bool) -> int:
    """A ceiling on the answer, so a runaway reply cannot hold the room: a few words per span alternative, a sentence
    per whole-sentence one, with room to spare."""
    return n * (70 if whole else 16) + 48


_THINK = re.compile(r"<think>.*?(</think>|$)", re.S)


def strip_thinking(text: str) -> str:
    """Reasoning models (DeepSeek-R1, Qwen 3) may write <think>…</think> before answering; it is never a proposal."""
    return _THINK.sub("", text)


def parse_lines(text: str, n: int) -> list[str]:
    out = []
    for line in strip_thinking(text).splitlines():
        t = line.strip().strip('"').strip("•-–* ").strip()
        t = re.sub(r"^\d{1,2}[.)]\s+", "", t).strip().strip('"').strip()  # list numbering, not "2030 targets"
        if t and t not in out:
            out.append(t)
    return out[:n]
