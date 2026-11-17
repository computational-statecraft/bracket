"""Opening drafts and saving statements as files, with no extra dependencies.

Import: a draft arrives as Word (.docx), Markdown or text, PDF or HTML, and leaves as the Markdown-ish text the paste
box understands (headings, bold lead-ins, numbered and bulleted items), so its structure survives. A bracket session
file (.json, as saved by "export") restores a session exactly: sentences, versions, states, brackets and dissents.

Export: the statement as a Word document, with its structure. Brackets stay in the text as written: an open
bracket is part of the record of where the room stands.

A .docx file is a zip of XML parts; Python's standard library reads and writes it.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
SESSION_FORMAT = "bracket-session"


# ---------- the statement's blocks (shared by Markdown and Word) ----------

def blocks(sentences: list[dict]) -> list[dict]:
    """Sentences grouped back into the blocks they were pasted as: {kind: h|p|li, label, text}."""
    out: list[dict] = []
    for s in sentences:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        if s.get("brk", True) or not out:
            out.append({"kind": s.get("kind", "p"), "label": s.get("label"), "text": text})
        else:
            out[-1]["text"] += " " + text
    return out


# ---------- export: Word ----------

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
_STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia" w:cs="Georgia"/><w:sz w:val="24"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="80"/></w:pPr><w:rPr><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="360"/></w:pPr><w:rPr><w:color w:val="767676"/><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListItem"><w:name w:val="List Item"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="567" w:hanging="567"/></w:pPr></w:style>
</w:styles>"""


def _run(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(runs: str, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def to_docx(title: str, sentences: list[dict], note: str = "") -> bytes:
    """The statement as a Word document: title, a one-line note, then each block with its structure."""
    body = [_para(_run(title or "Untitled session"), "Title")]
    if note:
        body.append(_para(_run(note), "Subtitle"))
    for b in blocks(sentences):
        if b["kind"] == "h":
            body.append(_para(_run(b["text"]), "Heading1"))
        elif b["kind"] == "li":
            marker = "•" if b["label"] in (None, "•") else b["label"]
            body.append(_para(_run(f"{marker}\t") + _run(b["text"]), "ListItem"))
        elif b["label"]:
            body.append(_para(_run(f"{b['label']}: ", bold=True) + _run(b["text"])))
        else:
            body.append(_para(_run(b["text"])))
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>'
                + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
                'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body></w:document>')
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(title or "Untitled session")}</dc:title><dc:creator>bracket</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{date.today().isoformat()}T00:00:00Z</dcterms:created></cp:coreProperties>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("docProps/core.xml", core)
    return buf.getvalue()


# ---------- import ----------

def docx_text(data: bytes) -> str:
    """A Word document's text as Markdown-ish lines (see docx_parts)."""
    return docx_parts(data)[1]


DOCX_PART_MAX = 32 * 1024 * 1024   # unpacked size of one part: a real statement is a few hundred KB


def _part(z: zipfile.ZipFile, name: str) -> bytes:
    """One part of a Word file, refusing a part that unpacks to an absurd size (a "zip bomb")."""
    if z.getinfo(name).file_size > DOCX_PART_MAX:
        raise ValueError(f"{name} is too large to be a statement")
    return z.read(name)


def docx_parts(data: bytes) -> tuple[str, str]:
    """(title, text) of a Word document. The first paragraph in Word's Title style is the title; the text has
    headings as "## ", numbered and bulleted paragraphs as "1. " and "- ", and a bold opening phrase ending in a
    colon as a lead-in ("**Purpose:** ...")."""
    title = ""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(_part(z, "word/document.xml"))
        numfmt = _numbering_formats(z)
    lines: list[str] = []
    counters: dict[tuple[str, str], int] = {}
    for p in root.iter(f"{{{W}}}p"):
        runs = []
        for r in p.iter(f"{{{W}}}r"):
            t = ""
            for x in r:
                if x.tag == f"{{{W}}}t":
                    t += x.text or ""
                elif x.tag in (f"{{{W}}}tab", f"{{{W}}}br"):
                    t += " "
            b = r.find("w:rPr/w:b", NS)
            bold = b is not None and b.get(f"{{{W}}}val", "true") not in ("0", "false")
            runs.append((t, bold))
        text = "".join(t for t, _ in runs).replace("\t", " ")
        text = " ".join(text.split())
        if not text:
            continue
        style = p.find("w:pPr/w:pStyle", NS)
        style = (style.get(f"{{{W}}}val") if style is not None else "") or ""
        num = p.find("w:pPr/w:numPr", NS)
        if re.match(r"(?i)^title$", style) and not title and not lines:
            title = text
        elif re.match(r"(?i)^subtitle$", style) and title and not lines:
            continue   # the line under the title (bracket's own export puts the session's state there)
        elif re.match(r"(?i)^(heading|title|subtitle)", style):
            lines.append(f"## {text}")
        elif num is not None:
            nid = num.find("w:numId", NS); lvl = num.find("w:ilvl", NS)
            key = (nid.get(f"{{{W}}}val") if nid is not None else "0", lvl.get(f"{{{W}}}val") if lvl is not None else "0")
            if numfmt.get(key, "decimal") == "bullet":
                lines.append(f"- {text}")
            else:
                counters[key] = counters.get(key, 0) + 1
                lines.append(f"{counters[key]}. {text}")
        else:
            lead = ""
            for t, bold in runs:
                if not bold:
                    break
                lead += t
            lead = " ".join(lead.split())
            if lead.endswith(":") and 1 < len(lead) < 80 and len(lead) < len(text):
                lines.append(f"**{lead}** {text[len(lead):].strip()}")
            else:
                lines.append(text)
    return title, "\n\n".join(lines)


def _numbering_formats(z: zipfile.ZipFile) -> dict[tuple[str, str], str]:
    """(numId, level) → number format ("bullet", "decimal", ...), from word/numbering.xml if there is one."""
    try:
        root = ET.fromstring(_part(z, "word/numbering.xml"))
    except KeyError:
        return {}
    abstract: dict[str, dict[str, str]] = {}
    for a in root.findall("w:abstractNum", NS):
        aid = a.get(f"{{{W}}}abstractNumId")
        abstract[aid] = {}
        for lvl in a.findall("w:lvl", NS):
            fmt = lvl.find("w:numFmt", NS)
            abstract[aid][lvl.get(f"{{{W}}}ilvl")] = fmt.get(f"{{{W}}}val") if fmt is not None else "decimal"
    out = {}
    for n in root.findall("w:num", NS):
        nid = n.get(f"{{{W}}}numId")
        aref = n.find("w:abstractNumId", NS)
        for lvl, fmt in abstract.get(aref.get(f"{{{W}}}val") if aref is not None else "", {}).items():
            out[(nid, lvl)] = fmt
    return out


def _int(v, default: int = 1) -> int:
    try:
        return max(0, min(int(v), 10_000))
    except (TypeError, ValueError):
        return default


def _str(v, limit: int = 20_000) -> str:
    return (v if isinstance(v, str) else "" if v is None else str(v))[:limit]


def clean_session(doc: dict) -> dict:
    """A saved session is a file anyone could have written: keep only the fields the app uses, each with the type it
    expects (numbers as numbers, states and kinds from the known sets, ids as plain tokens), so nothing in the file
    can reach the page as markup or break it."""
    out = {"title": _str(doc.get("title"), 300), "sentences": []}
    seen = set()
    for i, s in enumerate(doc.get("sentences") or []):
        if not isinstance(s, dict):
            continue
        sid = re.sub(r"[^A-Za-z0-9_-]", "", _str(s.get("id"), 40)) or f"s{i + 1}"
        while sid in seen:
            sid += "x"
        seen.add(sid)
        hist = [{"version": _int(h.get("version")), "at": _str(h.get("at"), 40), "via": _str(h.get("via"), 40),
                 "text": _str(h.get("text"))} for h in (s.get("history") or []) if isinstance(h, dict)][:500]
        dis = [{"version": _int(d.get("version")), "who": _str(d.get("who"), 200), "note": _str(d.get("note"), 2000)}
               for d in (s.get("dissents") or []) if isinstance(d, dict)][:200]
        out["sentences"].append({
            "id": sid, "text": _str(s.get("text")), "label": _str(s.get("label"), 200) or None,
            "kind": s.get("kind") if s.get("kind") in ("p", "h", "li") else "p",
            "brk": bool(s.get("brk", True)),
            "state": s.get("state") if s.get("state") in ("draft", "open", "agreed") else "draft",
            "version": _int(s.get("version")), "history": hist, "dissents": dis,
        })
    return out


def import_file(name: str, data: bytes) -> dict:
    """{'ok', 'kind': 'text'|'session', 'text'|'doc', 'title', 'detail'} for a file someone opened."""
    lower = name.lower()
    if lower.endswith(".json"):
        try:
            j = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return {"ok": False, "error": "this .json file could not be read"}
        doc = j.get("doc") if isinstance(j, dict) else None
        if j.get("format") != SESSION_FORMAT or not isinstance(doc, dict) or not isinstance(doc.get("sentences"), list):
            return {"ok": False, "error": "this .json file is not a saved bracket session"}
        doc = clean_session(doc)
        return {"ok": True, "kind": "session", "doc": doc, "title": doc.get("title") or j.get("title") or "",
                "detail": f"saved session · {len(doc['sentences'])} sentences"}
    if lower.endswith(".docx") or data[:2] == b"PK":
        try:
            title, text = docx_parts(data)
        except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError):
            return {"ok": False, "error": "this file could not be read as a Word document (.docx)"}
        return {"ok": True, "kind": "text", "text": text, "title": title or _stem(name), "detail": "Word document"}
    if lower.endswith(".doc"):
        return {"ok": False, "error": "older Word files (.doc) cannot be read: save it as .docx in Word, then open it"}
    from .library_cli import extract, kind_of   # PDF, HTML, text and Markdown

    kind = kind_of(name, data)
    try:
        if kind == "text":
            text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
        else:
            text = "\n\n".join(extract(data, kind))
    except Exception as e:  # noqa: BLE001 — a damaged file is a message, not a crash
        return {"ok": False, "error": f"this file could not be read ({str(e)[:80]})"}
    if not text.strip():
        return {"ok": False, "error": "no text found in this file"}
    return {"ok": True, "kind": "text", "text": text, "title": _stem(name), "detail": {"pdf": "PDF", "html": "web page"}.get(kind, "text")}


def _stem(name: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    return " ".join(stem.replace("_", " ").replace("-", " ").split())[:80]
