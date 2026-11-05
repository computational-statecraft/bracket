"""Backend checks for the behaviour the room depends on. Run: uv run pytest -q"""
import importlib

import pytest

from backend import cloud_llm, lexicon, prompts, validate
from backend.nlp import Sentence, align, split_sentences


# ---------- validation ----------

def test_contraction_is_not_a_negation_change():
    assert validate.check("We do not accept this.", "We don't accept this.")["flags"] == []
    assert validate.check("We will not accept this.", "We won't accept this.")["flags"] == []


def test_dropped_negation_is_flagged():
    assert "negation changed" in validate.check("We do not accept this.", "We accept this.")["flags"]


def test_modal_shift_is_flagged():
    assert "modal shifted" in validate.check("Members should report.", "Members must report.")["flags"]


def test_new_entity_is_dropped():
    assert validate.check("expand its work", "expand the World Bank's work")["ok"] is False


def test_entity_named_elsewhere_in_sentence_is_not_new():
    sentence = "The Commission will expand its work across Europe."
    assert validate.check("expand its work", "widen the Commission's work", context=sentence)["ok"] is True


def test_entity_check_matches_whole_words():
    # "us" inside "must" is not the entity "US"
    assert validate.check("Members must act.", "The US must act.")["ok"] is False


# ---------- prompts ----------

def test_strength_beyond_two_is_not_described_as_same():
    assert prompts.strength_text(4) == "much stronger"
    assert prompts.strength_text(-3) == "much weaker"
    assert prompts.strength_text(0) == "unchanged"


def test_ladder_target_reaches_the_prompt():
    p = prompts.span_body("We invite members to act.", "invite", 2, 3, "institutional", "same", target="request")
    assert 'much stronger (the force of "request")' in p


def test_parse_lines_keeps_leading_years():
    assert prompts.parse_lines("1. By 2030 we act\n2) 2030 targets matter\n- third", 3) == ["By 2030 we act", "2030 targets matter", "third"]


# ---------- lexicon ----------

def test_ladder_found_from_inflected_verb():
    lad = lexicon.ladder_for("encourages")
    assert lad and lad["rungs"][lad["current"]] == "encourage"


def test_synonyms_drop_unused_senses():
    s = "The council strengthened its commitments."
    i = s.index("strengthened")
    out = lexicon.synonyms(s, i, i + len("strengthened"))["synonyms"]
    assert "fortified" in out and "toned" not in out


# ---------- segmentation ----------

def test_split_and_align_keep_ids():
    old = [Sentence("a", "We act now.", "agreed", 2)]
    new = align(split_sentences("We act now. Then we report."), old)
    assert new[0].id == "a" and new[0].state == "agreed" and new[0].version == 2
    assert new[1].id != "a" and new[1].version == 1


def test_edited_agreed_sentence_returns_to_draft():
    new = align(["We act today."], [Sentence("a", "We act now.", "agreed", 2)])
    assert new[0].id == "a" and new[0].state == "draft" and new[0].version == 3


# ---------- cloud request shape ----------

def test_cloud_options_never_send_sampling_params():
    for m in ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5", "claude-sonnet-4-5"):
        opts = cloud_llm._speed_options(m)
        assert "temperature" not in opts and "top_p" not in opts
    assert cloud_llm._speed_options("claude-sonnet-5-5")["thinking"] == {"type": "between_tools"}
    assert "thinking" not in cloud_llm._speed_options("claude-opus-5-5")


# ---------- session resume ----------

@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    from backend import config, store

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")

    def load(session_env=""):
        monkeypatch.setattr(config, "SESSION_ID", session_env)
        return importlib.reload(store)

    yield load
    monkeypatch.undo()
    importlib.reload(store)


def test_restart_resumes_todays_session(fresh_store):
    s1 = fresh_store()
    s1.snapshot({"sentences": [{"id": "x", "text": "Hello."}]})
    first = s1.SESSION
    s2 = fresh_store()  # a restart
    assert s2.SESSION == first and s2.load_snapshot()["sentences"][0]["text"] == "Hello."


def test_new_forces_a_fresh_session(fresh_store):
    s1 = fresh_store()
    s1.snapshot({"sentences": []})
    first = s1.SESSION
    assert fresh_store("new").SESSION != first
    assert fresh_store("spring-meeting").SESSION == "spring-meeting"


def test_bedrock_model_ids_get_the_same_speed_options():
    assert cloud_llm._speed_options("us.anthropic.claude-sonnet-5-5") == cloud_llm._speed_options("claude-sonnet-5-5")
    assert cloud_llm._speed_options("us.anthropic.claude-sonnet-4-6") == {}


def test_gateway_bedrock_sends_key_header_not_aws_signature(monkeypatch):
    import asyncio

    import httpx2

    from backend import config

    monkeypatch.setattr(config, "CLOUD_KEY", "k")
    monkeypatch.setattr(config, "CLOUD_KEY_HEADER", "")
    client = cloud_llm._gateway_bedrock(base_url="https://gw.example/bedrock", timeout=5, max_retries=0)
    req = httpx2.Request("POST", "https://gw.example/x")
    asyncio.run(client._prepare_request(req))
    assert req.headers["x-api-key"] == "k" and "authorization" not in req.headers


# ---------- draft structure ----------

DRAFT = """**Purpose:** Within ten years, the basin is managed as one shared system in order to secure water for every community.

**Objectives needed to achieve this purpose.**
1. Reliable data shared among all members.
2. Communities *secure*, consulted and represented. Their rights are respected in full.
- A bullet"""


def test_draft_keeps_lead_ins_headings_and_list_items():
    from backend import draft

    s = draft.parse(DRAFT)
    assert [(x["kind"], x["label"], x["brk"]) for x in s] == [
        ("p", "Purpose", True), ("h", None, True), ("li", "1.", True), ("li", "2.", True), ("li", None, False), ("li", "•", True)]
    assert s[0]["text"].startswith("Within ten years") and "**" not in s[1]["text"] and s[3]["text"] == "Communities secure, consulted and represented."


def test_draft_round_trips_to_markdown():
    from backend import draft

    md = draft.to_markdown(draft.parse(DRAFT))
    assert md.startswith("**Purpose:** Within ten years")
    assert "**Objectives needed to achieve this purpose.**\n\n1. Reliable" in md
    assert "2. Communities secure, consulted and represented. Their rights are respected in full.\n- A bullet" in md


def test_old_snapshots_without_structure_still_export():
    from backend import draft

    assert draft.to_markdown([{"text": "One."}, {"text": "Two."}]) == "One.\n\nTwo."


def test_anthropic_is_the_default_cloud_and_off_without_a_key(monkeypatch):
    from backend import config

    for var in ("BRACKET_CLOUD_API", "BRACKET_CLOUD_KEY", "ANTHROPIC_API_KEY", "BRACKET_CLOUD_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "read_file", lambda: {})
    config.reload()
    try:
        assert config.CLOUD_API == "anthropic" and config.CLOUD_BASE_URL is None and not config.CLOUD_ENABLED
        st = cloud_llm.status()
        assert not st["ok"] and st["error"] == "no key" and "Optional" in st["detail"]
    finally:
        monkeypatch.undo()
        config.reload()


# ---------- local prompt ----------

def test_both_models_get_the_rules_as_system_and_a_short_request():
    body = prompts.span_body("We act now.", "act", 3, 0, "institutional", "same")
    assert prompts.messages(body) == [{"role": "system", "content": prompts.RULES}, {"role": "user", "content": body}]
    assert len(prompts.RULES) + len(body) < 700   # short: the local model reads all of it before writing a word


def test_rules_protect_bracketed_text():
    assert "[bracketed]" in prompts.RULES


def test_answer_ceiling_fits_the_request():
    assert prompts.max_tokens(3, False) < prompts.max_tokens(9, False) < prompts.max_tokens(3, True)


# ---------- thinking models ----------

def test_reasoning_never_becomes_a_proposal():
    assert prompts.parse_lines("<think>hmm, options…\nmaybe x</think>\nurge\ncall upon", 2) == ["urge", "call upon"]
    assert prompts.parse_lines("<think>cut off mid-thought", 2) == []


# ---------- span boundaries ----------

SENT = "By then, the commission reviewed as a standing body every allocation rule."


def test_span_prompt_marks_the_span_and_names_its_neighbours():
    body = prompts.span_body(SENT, "reviewed", 3, 0, "institutional", "same", start=SENT.index("reviewed"))
    assert "commission ⟦reviewed⟧ as a standing" in body and 'after "commission" and before "as"' in body and body.endswith("3 alternatives.")


def test_proposals_that_run_into_the_next_word_are_trimmed():
    from backend.app import _validated

    got = [o["text"] for o in _validated("reviewed", ["examined as", "looked into as", "assessed", "commission audited"], SENT, SENT.index("reviewed"))]
    assert got == ["examined", "looked into", "assessed", "audited"]


def test_trimming_keeps_words_the_span_itself_ends_with():
    from backend.app import _trim_overlap

    s = "We will act as a team as soon as possible."
    assert _trim_overlap(s, "act as", "work as", s.index("act as")) == "work as"


def test_duplicates_are_dropped():
    from backend.app import _validated

    assert [o["text"] for o in _validated("reviewed", ["assessed as", "assessed", "Assessed"], SENT, SENT.index("reviewed"))] == ["assessed"]
