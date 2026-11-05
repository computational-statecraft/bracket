"""Agreed-language library: extraction from fetched documents, and search. The documents here are invented for the
test; they are not quotations from real texts."""
import json

import pytest

from backend import library, library_cli


DOCS = [
    {"id": "t-un", "body": "UN", "title": "Test Declaration", "date": "2024-07-10", "url": "u1", "paragraphs": [
        {"n": "5", "text": "Climate change is the most significant and direct threat to the security of small island states. We condemn attacks on civilian water infrastructure."},
        {"n": "6", "text": "We will continue to support the reconstruction of the region for as long as it takes, with full respect for its sovereignty."}]},
    {"id": "t-eu", "body": "EU", "title": "Test Conclusions", "date": "2022-02-24", "url": "u2", "paragraphs": [
        {"n": "1", "text": "The European Council condemns in the strongest possible terms the deliberate destruction of civilian infrastructure."},
        {"n": "2", "text": "We will continue to support the reconstruction of the region for as long as it takes, with full respect for its sovereignty."}]},
]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    d = tmp_path_factory.mktemp("texts")
    for doc in DOCS:
        (d / f"{doc['id']}.json").write_text(json.dumps(doc), encoding="utf-8")
    return library.Library([d])


def test_identical_sentences_are_one_precedent_with_both_sources(lib):
    h = lib.search("We will support the reconstruction of the region for as long as it takes.")[0]
    assert h["text"].startswith("We will continue to support the reconstruction")
    assert [c["body"] for c in h["cites"]] == ["UN", "EU"] and h["also"] == 1   # newest first
    assert h["cites"][0]["cite"] == "UN · Test Declaration (2024) ¶6"


def test_span_is_lined_up_with_the_precedent_and_says_what_it_replaces(lib):
    s = "Within a decade, climate change framed as a threat to island states."
    h = lib.search(s, s.index("framed"), s.index("framed") + 6)[0]
    assert h["phrase"] == "is the most significant and direct"
    assert s[h["rstart"]:h["rend"]] == "framed as a"
    assert h["text"][h["pstart"]:h["pend"]] == h["phrase"]   # the precedent's own words, exactly


def test_wording_already_agreed_is_marked_same(lib):
    s = "We condemn the deliberate destruction of civilian infrastructure."
    i = s.index("deliberate")
    h = lib.search(s, i, i + len("deliberate destruction"))[0]
    assert h["same"] and "strongest possible terms" in h["text"]


def test_unrelated_sentence_finds_nothing(lib):
    assert lib.search("Fisheries quotas for the Baltic herring season.") == []


def test_brackets_in_the_draft_are_not_words(lib):
    assert lib.search("We [condemn / deplore] the destruction of civilian infrastructure.")


def test_a_document_on_this_machine_replaces_the_bundled_copy(tmp_path):
    bundled, user = tmp_path / "b", tmp_path / "u"
    bundled.mkdir(), user.mkdir()
    (bundled / "x.json").write_text(json.dumps({**DOCS[0], "id": "x", "title": "Old"}))
    (user / "x.json").write_text(json.dumps({**DOCS[0], "id": "x", "title": "New"}))
    assert [d["title"] for d in library.Library([bundled, user]).docs.values()] == ["New"]


# ---------- extraction ----------

def test_html_keeps_block_text_and_numbers_ordered_lists():
    html = """<html><nav><p>Menu</p></nav><h1>Declaration</h1><ol><li>We, the Heads of State, met in Geneva.</li>
    <li><p>Water is a shared resource.</p></li></ol><p>A closing <b>paragraph</b> here.</p><script>x()</script></html>"""
    assert library_cli.html_paragraphs(html) == ["Declaration", "1. We, the Heads of State, met in Geneva.", "2. Water is a shared resource.", "A closing paragraph here."]


def test_pdf_lines_are_rejoined_and_page_furniture_dropped():
    page = ("EUCO 18/22 1\nEN\n1. The European Council condemns in the strongest possible terms the deliberate de-\n"
            "struction of civilian infrastructure in the region.\n2. Those responsible will be held to account for this and for all the\n"
            "damage and loss of life it has caused.\n")
    paras = library_cli.number_paragraphs(library_cli.pdf_paragraphs(page))
    assert paras == [
        {"n": "1", "text": "The European Council condemns in the strongest possible terms the deliberate destruction of civilian infrastructure in the region."},
        {"n": "2", "text": "Those responsible will be held to account for this and for all the damage and loss of life it has caused."}]


def test_every_paragraph_is_kept_unless_a_topic_is_given():
    paras = [{"n": "1", "text": "We welcome progress on the climate finance goal agreed last year in full."},
             {"n": "2", "text": "We reaffirm our commitment to the shared management of transboundary water."},
             {"n": "3", "text": "Too short."}]
    assert [p["n"] for p in library_cli.keep(paras)] == ["1", "2"]
    assert [p["n"] for p in library_cli.keep(paras, topic=r"\bwater\b")] == ["2"]


def test_unnumbered_paragraphs_take_the_last_number_with_a_letter():
    assert [p["n"] for p in library_cli.number_paragraphs(["Preamble text.", "3. Three.", "More of three.", "4. Four."])] == ["p1", "3", "3a", "4"]


def test_a_document_can_be_added_from_bytes(tmp_path):
    text = b"First paragraph of an adopted text, long enough to be kept as precedent.\n\nShort."
    res = library_cli.add_bytes(text, "notes.md", "OWN", "My statement", "2026-01-01", out=tmp_path)
    assert res["ok"] and res["paragraphs"] == 1 and (tmp_path / f"{res['id']}.json").exists()


def test_library_files_are_read_as_utf8_on_every_platform(tmp_path, monkeypatch):
    """Windows defaults to a legacy code page; a curly quote or an accent in a precedent must not break loading."""
    import locale

    doc = {**DOCS[0], "id": "u", "paragraphs": [{"n": "1", "text": "We welcome the “Pact for the Future” and the Côte d’Ivoire initiative on water security."}]}
    (tmp_path / "u.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **k: "cp1252")   # what Windows would use
    lib = library.Library([tmp_path])
    assert "Côte d’Ivoire" in lib.groups[0]["text"]
