"""Compare the local model with Claude on the same rewording tasks, so the choice of model (or a case for fine-tuning)
rests on outputs side by side rather than impressions.

    uv run python -m backend.compare                               # the configured local model vs Claude
    uv run python -m backend.compare gemma4:e4b qwen3:8b           # several models (Ollama or OpenAI-compatible engines)
    uv run python -m backend.compare --draft my-draft.md           # whole-sentence rewrites of your own sentences
    uv run python -m backend.compare --no-claude

Every model gets the room's prompt (the short rules as a system message, then the request). Writes
compare-<time>.md in the data folder and prints a summary: median time, and how often at least one proposal survived
validation. With the built-in engine, the model is the one chosen on the setup screen.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from pathlib import Path

from . import cloud_llm, config, draft, local_llm, prompts

# (sentence, span or None for the whole sentence, strength, ladder target)
CASES: list[tuple[str, str | None, int, str | None]] = [
    ("We encourage all member states to share hydrological data with the commission.", "encourage", 1, "urge"),
    ("The commission should consider additional measures to reduce upstream pollution.", "should consider", 1, None),
    ("Member states must ensure that allocation rules are applied in full.", "must ensure", -1, None),
    ("Within ten years, every riparian community has reliable access to clean water.", "has reliable access to", 0, None),
    ("We support a fair and lasting settlement of disputes under the basin agreement.", "support", 1, "promote"),
    ("Water allocation in dry years is shared fairly and agreed in advance.", None, 0, None),
    ("The basin is managed as a single ecosystem across national borders.", None, 0, None),
    ("Our aim is to reduce the risk of conflict while keeping channels of cooperation open.", None, -1, None),
]


def _task(sentence: str, span: str | None, strength: int, target: str | None) -> tuple[str, str, int]:
    """(request body, source text, number of alternatives)"""
    if span:
        return prompts.span_body(sentence, span, 3, strength, "institutional", "same", target), span, 3
    return prompts.sentence_body(sentence, [], 3, strength, "institutional", "same", target), sentence, 3


async def _local(model: str, body: str, n: int, whole: bool) -> tuple[int, list[str], str | None]:
    res = await local_llm.complete(prompts.messages(body), n, timeout=60, model=model, max_tokens=prompts.max_tokens(n, whole))
    return res["ms"], res["lines"], res.get("error")


async def _claude(body: str, n: int, whole: bool) -> tuple[int, list[str], str | None]:
    t0, acc, err = time.perf_counter(), "", None
    async for ev in cloud_llm.stream(body, max_tokens=prompts.max_tokens(n, whole)):
        acc += ev.get("delta", "")
        err = ev.get("error", err)
    return int((time.perf_counter() - t0) * 1000), prompts.parse_lines(acc, n), err


async def main() -> None:
    from .app import _validated

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", default=[""])
    ap.add_argument("--draft", help="a draft file: compare whole-sentence rewrites of its sentences (up to 10)")
    ap.add_argument("--no-claude", action="store_true")
    a = ap.parse_args()

    cases = CASES
    if a.draft:
        sents = [s["text"] for s in draft.parse(Path(a.draft).read_text(encoding="utf-8")) if s["kind"] != "h"][:10]
        cases = [(s, None, 0, None) for s in sents]

    tiers = [(m or local_llm.model_name(), m or None) for m in a.models]
    use_claude = not a.no_claude and cloud_llm.status()["ok"]
    stats: dict[str, list[tuple[int, int]]] = {t[0]: [] for t in tiers}
    if use_claude:
        stats[f"Claude · {config.CLOUD_MODEL}"] = []

    # Run one model through every case before the next, as the room would: Ollama keeps the prompt it last read, and
    # switching models between cases would reload them. Each model gets one unmeasured call first, which loads it.
    if config.LOCAL_ENGINE == "builtin":
        from . import engine

        await engine.ensure()
    tasks = [_task(*c) for c in cases]
    whole = [c[1] is None for c in cases]
    results: dict[tuple[str, int], tuple[int, list[str], str | None]] = {}
    for name, m in tiers:
        print(f"{name}: warming up …", flush=True)
        await _local(m, tasks[0][0], tasks[0][2], whole[0])
        for i, (body, _, n) in enumerate(tasks):
            results[(name, i)] = await _local(m, body, n, whole[i])
            print(f"  [{i + 1}/{len(tasks)}] {results[(name, i)][0] / 1000:.1f} s", flush=True)
    if use_claude:
        name = f"Claude · {config.CLOUD_MODEL}"
        print(f"{name} …", flush=True)
        for i, (body, _, n) in enumerate(tasks):
            results[(name, i)] = await _claude(body, n, whole[i])

    out = [f"# Local models vs Claude · {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for i, (sentence, span, strength, target) in enumerate(cases):
        _, source, _ = tasks[i]
        what = f'span "{span}"' if span else "whole sentence"
        dial = {-1: "weaker", 0: "same strength", 1: "stronger"}.get(strength, str(strength)) + (f" (toward *{target}*)" if target else "")
        out += [f"## {i + 1}. {what}, {dial}", "", f"> {sentence}", ""]
        for name in stats:
            ms, lines, err = results[(name, i)]
            kept = {k["text"]: k["flags"] for k in _validated(source, lines, sentence)}
            stats[name].append((ms, 1 if kept else 0))
            out.append(f"**{name}** · {ms / 1000:.1f} s" + (f" · error: {err}" if err else ""))
            for ln in lines:
                if ln in kept:
                    out.append(f"- {ln}" + (f"  *▲ {', '.join(kept[ln])}*" if kept[ln] else ""))
                else:
                    out.append(f"- ~~{ln}~~ *(dropped by validation)*")
            out.append("")

    out += ["## Summary", "", "| | median time | cases with a usable proposal |", "|---|---|---|"]
    print("\n" + f"{'':44}{'median':>9}  usable")
    for name, rows in stats.items():
        med = statistics.median(r[0] for r in rows) / 1000 if rows else 0
        ok = sum(r[1] for r in rows)
        out.append(f"| {name} | {med:.1f} s | {ok} of {len(rows)} |")
        print(f"  {name:<42}{med:>7.1f} s  {ok} of {len(rows)}")

    path = config.DATA_DIR / f"compare-{time.strftime('%Y%m%d-%H%M%S')}.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nFull outputs, side by side: {path}\n")
    if config.LOCAL_ENGINE == "builtin":
        from . import engine

        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
