# PyInstaller spec for the desktop app. Built by .github/workflows/build.yml; locally:
#   uv sync --group build && uv run pyinstaller packaging/bracket.spec --noconfirm
# Expects, if present: build/nltk_data (WordNet), build/llama (llama.cpp's llama-server and its libraries),
# build/icon.png, and library/texts/*.json (the precedent library).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT))
from backend.config import VERSION  # noqa: E402

datas = [(str(ROOT / "frontend"), "frontend"), (str(ROOT / "library"), "library"), (str(ROOT / "LICENSE"), "."),
         (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]
if (BUILD / "nltk_data").is_dir():
    datas.append((str(BUILD / "nltk_data"), "nltk_data"))
if (BUILD / "llama").is_dir():
    # kept as data, untouched: llama.cpp's binaries load their own libraries from their folder
    datas.append((str(BUILD / "llama"), "llama"))
binaries, hidden = [], collect_submodules("uvicorn") + ["backend.app"]
for pkg in ("spacy", "thinc", "en_core_web_sm", "srsly", "catalogue", "confection", "weasel", "blis", "cymem", "preshed",
            "murmurhash", "spacy_legacy", "spacy_loggers", "lemminflect", "nltk", "pypdf", "anthropic", "wasabi"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:  # a package missing on this platform
        continue
    datas += d
    binaries += b
    hidden += h

# spaCy ships its test suite and ~70 languages; bracket needs English only (and "xx", the multi-language base)
def _needed(path: str) -> bool:
    p = path.replace("\\", "/")
    if "/spacy/tests/" in p or p.endswith("/spacy/tests") or "/thinc/tests/" in p:
        return False
    if "/spacy/lang/" in p:
        lang = p.split("/spacy/lang/")[1].split("/")[0]
        return lang in ("en", "xx") or "." in lang   # keep spacy/lang/*.py (shared modules)
    return True


datas = [d for d in datas if _needed(d[0])]
binaries = [b for b in binaries if _needed(b[0])]
hidden = [h for h in hidden if not h.startswith(("spacy.tests", "thinc.tests")) and
          not (h.startswith("spacy.lang.") and h.split(".")[2] not in ("en", "xx", "char_classes", "lex_attrs", "norm_exceptions", "punctuation", "tokenizer_exceptions"))]

_icon = BUILD / {"darwin": "icon.icns", "win32": "icon.ico"}.get(sys.platform, "icon.png")
icon = str(_icon) if _icon.exists() else None
a = Analysis([str(ROOT / "launcher.py")], pathex=[str(ROOT)], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["torch", "tensorflow", "matplotlib", "pytest", "IPython", "PIL", "tkinter.test"], noarchive=False)
pyz = PYZ(a.pure)
windowed = sys.platform in ("darwin", "win32")
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="bracket", console=not windowed, icon=icon,
          argv_emulation=False, target_arch=None)
coll = COLLECT(exe, a.binaries, a.datas, name="bracket")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="bracket.app", icon=icon, bundle_identifier="io.github.computational-statecraft.bracket",
                 version=VERSION, info_plist={
                     "CFBundleDisplayName": "bracket", "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                     "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
                     "NSHumanReadableCopyright": "Apache-2.0"})
