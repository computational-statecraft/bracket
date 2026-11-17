"""Opening drafts and saving statements as files."""
import io
import json
import zipfile

from backend import docfiles

SENTS = [
    {"text": "Purpose", "kind": "h", "label": None, "brk": True},
    {"text": "We note the progress made.", "kind": "p", "label": "Aim", "brk": True},
    {"text": "We act.", "kind": "p", "label": None, "brk": False},
    {"text": "Members will [encourage / urge] cooperation.", "kind": "li", "label": "1.", "brk": True},
    {"text": "A bullet point.", "kind": "li", "label": "•", "brk": True},
]


def test_word_export_is_a_valid_document_with_the_statement():
    data = docfiles.to_docx("Joint statement", SENTS, "2 of 5 agreed")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        xml = z.read("word/document.xml").decode()
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"} <= names
    assert "Joint statement" in xml and "We note the progress made. We act." in xml
    assert "[encourage / urge]" in xml   # brackets stay in the text


def test_word_round_trip_keeps_the_structure_and_the_title():
    r = docfiles.import_file("draft.docx", docfiles.to_docx("Joint statement", SENTS, "a note"))
    assert r["title"] == "Joint statement" and "Joint statement" not in r["text"] and "a note" not in r["text"]
    text = r["text"]
    assert "## Purpose" in text
    assert "**Aim:** We note the progress made. We act." in text
    assert "Members will [encourage / urge] cooperation." in text


def test_word_numbered_and_bulleted_lists_are_recognized():
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    para = lambda num, t: f'<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr></w:pPr><w:r><w:t>{t}</w:t></w:r></w:p>'
    doc = f'<w:document xmlns:w="{W}"><w:body>{para(1, "First.")}{para(1, "Second.")}{para(2, "A bullet.")}</w:body></w:document>'
    numbering = (f'<w:numbering xmlns:w="{W}">'
                 '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>'
                 '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num><w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num></w:numbering>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
        z.writestr("word/numbering.xml", numbering)
    assert docfiles.docx_text(buf.getvalue()).split("\n\n") == ["1. First.", "2. Second.", "- A bullet."]


def test_a_saved_session_reopens_whole():
    saved = json.dumps({"format": "bracket-session", "doc": {"title": "T", "sentences": [{"id": "a", "text": "One.", "state": "agreed"}]}})
    r = docfiles.import_file("bracket-t.json", saved.encode())
    assert r["ok"] and r["kind"] == "session" and r["doc"]["sentences"][0]["state"] == "agreed" and r["title"] == "T"


def test_files_that_cannot_be_opened_say_why():
    assert "not a saved bracket session" in docfiles.import_file("x.json", b'{"a": 1}')["error"]
    assert ".docx" in docfiles.import_file("old.doc", b"\xd0\xcf\x11\xe0")["error"]
    assert "Word" in docfiles.import_file("broken.docx", b"PK\x03\x04 not really a zip")["error"]


def test_markdown_and_text_open_as_they_are():
    r = docfiles.import_file("my-draft_v2.md", "## Heading\n\n1. First.\r\n".encode())
    assert r["ok"] and r["text"].startswith("## Heading") and "\r" not in r["text"] and r["title"] == "my draft v2"
