"""Print exactly what each model is sent, for a sample span:  uv run python -m backend.show_prompts"""
from __future__ import annotations

import json

from . import config, prompts

SENTENCE = "Each year, the commission reviewed as a standing body the allocation rules for every dry season."
SPAN = "reviewed"


def show(title: str, text: str) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}\n{text}")


def main() -> None:
    span = SENTENCE.index(SPAN)
    show("BOTH MODELS — the system message", prompts.RULES)
    show(f"LOCAL ({config.LOCAL_ENGINE}) — double-click a word: the user message (answer capped at {prompts.max_tokens(3, False)} tokens)",
         prompts.span_body(SENTENCE, SPAN, 3, 0, "institutional", "same", start=span))
    show(f"CLAUDE ({config.CLOUD_MODEL}) — C: the user message (C again asks for 9)",
         prompts.span_body(SENTENCE, SPAN, 6, 0, "institutional", "same", start=span))
    show("EITHER — ⌘↵ on a whole sentence: the user message",
         prompts.sentence_body(SENTENCE, ["(the sentence before)", "(the sentence after)"], 3, 0, "institutional", "same"))
    print(f"\n(as JSON for Ollama: {json.dumps(prompts.messages('…'), ensure_ascii=False)})")


if __name__ == "__main__":
    main()
