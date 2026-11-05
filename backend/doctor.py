"""Check the whole setup with real calls: settings, the lexicon, the precedent library, the local model, and Claude.

    uv run python -m backend.doctor        (from source)
    Bracket --doctor                        (the packaged app, from a terminal)

Exits non-zero if the lexicon or the local model is not working. Claude is optional: a missing key is a warning.
The key is never printed, only its last four characters.
"""
from __future__ import annotations

import asyncio
import sys
import time

from . import config, cloud_llm, local_llm, prompts

SAMPLE = "We encourage every member state to strengthen its commitments."
OK, BAD, WARN = "\033[32mok\033[0m", "\033[31mFAIL\033[0m", "\033[33mwarn\033[0m"


def row(name: str, verdict: str, detail: str) -> None:
    print(f"  {name:<14}{verdict:<15}{detail}")


async def reword(tier: str) -> tuple[int, int, list[str]]:
    """Whole-sentence rewording through the same prompt and validation the room uses: (ms, kept, raw lines)."""
    from .app import _validated

    body = prompts.sentence_body(SAMPLE, [], 3, 0, "institutional", "same")
    t0 = time.perf_counter()
    if tier == "local":
        res = await local_llm.complete(prompts.messages(body), 3, max_tokens=prompts.max_tokens(3, True))
        lines = res["lines"]
    else:
        acc = ""
        async for ev in cloud_llm.stream(body, max_tokens=prompts.max_tokens(3, True)):
            acc += ev.get("delta", "")
            if "error" in ev:
                raise RuntimeError(ev["error"])
        lines = prompts.parse_lines(acc, 3)
    return int((time.perf_counter() - t0) * 1000), len(_validated(SAMPLE, lines, SAMPLE)), lines


async def main() -> int:
    failed = False
    print("\nBracket doctor\n")

    row("Data folder", OK, str(config.DATA_DIR))
    row("Settings", OK, str(config.SETTINGS_FILE) + ("" if config.SETTINGS_FILE.exists() else " (none yet: defaults)"))
    key = config.CLOUD_KEY
    row("Claude key", OK if key else WARN, f"set, ends …{key[-4:]}" if len(key) > 8 else ("set (short)" if key else "none (optional)"))

    t0 = time.perf_counter()
    from . import lexicon

    syn = lexicon.synonyms("We strengthen the commitments.", 3, 13)["synonyms"]
    row("Lexicon", OK if syn else BAD, f"{int((time.perf_counter() - t0) * 1000)} ms cold · strengthen → {', '.join(syn[:3])}")
    failed |= not syn

    from . import library

    if library.status()["ok"]:
        t0 = time.perf_counter()
        lib = library.get()
        hits = lib.search("We reaffirm our commitment to the principles of the United Nations Charter.")
        row("Agreed lang.", OK if hits else WARN, f"{len(lib.docs)} documents, {lib.size} sentences, indexed in {time.perf_counter() - t0:.1f} s"
            + (f" · e.g. {hits[0]['cites'][0]['cite']}" if hits else " · no precedent for a test sentence"))
    else:
        row("Agreed lang.", WARN, "library empty: Download it from the setup screen")

    print(f"  {'':14}engine: {config.LOCAL_ENGINE}" + (f" · {config.LOCAL_URL}" if config.LOCAL_ENGINE != "builtin" else ""))
    loc = await local_llm.check()
    if loc["ok"]:
        row("Local model", OK, f"{loc['model']} · {loc['ms'] / 1000:.1f} s · begin → {', '.join(loc['sample'])}")
        ms, kept, lines = await reword("local")
        row("  rewording", OK if kept else WARN, f"{ms / 1000:.1f} s · {kept} of {len(lines)} proposals passed validation")
        for ln in lines:
            print(f"{'':18}· {ln}")
    else:
        row("Local model", BAD, f"{loc['model']} · {loc['error']}{' · ' + loc['detail'] if loc.get('detail') else ''}")
        failed = True

    st = cloud_llm.status()
    if not st["ok"]:
        row("Claude", WARN, st.get("detail") or st.get("error", ""))
    else:
        print(f"  {'':14}{config.CLOUD_API} · {config.CLOUD_MODEL} · {config.CLOUD_BASE_URL or 'api.anthropic.com'}")
        chk = await cloud_llm.check()
        if chk["ok"]:
            row("Claude", OK, f"{chk['ms'] / 1000:.1f} s round trip{' · gateway ignores the speed settings' if chk['plain'] else ''}")
            try:
                ms, kept, lines = await reword("cloud")
                row("  rewording", OK if kept else WARN, f"{ms / 1000:.1f} s · {kept} of {len(lines)} proposals passed validation")
                for ln in lines:
                    print(f"{'':18}· {ln}")
            except RuntimeError as e:
                row("  rewording", BAD, str(e)[:160])
                failed = True
        else:
            row("Claude", BAD, chk["error"] or "empty reply")
            failed = True

    print("\n" + ("Something needs fixing before the session." if failed else "Ready.") + "\n")
    from . import engine

    await engine.stop()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
