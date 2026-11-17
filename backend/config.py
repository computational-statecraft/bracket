"""Runtime configuration.

Every setting has three layers, highest first:

1. an environment variable (``BRACKET_*``), for scripts and power users;
2. ``settings.json`` in the user's data folder, written by the setup screen;
3. a default that works on a fresh machine.

``reload()`` re-reads the layers, so the setup screen can change the model or the API key without a restart. Other
modules read the module attributes (``config.LOCAL_MODEL``) at call time, never at import time.

Paths: ``ROOT`` holds the app's own files (the frontend, the bundled precedent library, WordNet). From source it is
the repository; in the packaged app it is PyInstaller's resource folder. ``DATA_DIR`` holds everything the app writes:
settings, downloaded models, session logs. It lives in the platform's per-user application-data folder unless
``BRACKET_DATA`` says otherwise.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
VERSION = "0.4.0"


def _default_data_dir() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir("bracket", appauthor=False, roaming=False))


DATA_DIR = Path(os.environ.get("BRACKET_DATA") or _default_data_dir()).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR = DATA_DIR / "models"
LOG_DIR = DATA_DIR / "logs"
USER_LIBRARY = DATA_DIR / "library"          # documents fetched or added on this machine
BUNDLED_LIBRARY = ROOT / "library" / "texts"  # documents shipped with the app
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_PATH = DATA_DIR / "bracket.sqlite"

# WordNet: shipped inside the packaged app; downloaded into the data folder on first use when running from source
NLTK_DIRS = [ROOT / "nltk_data", DATA_DIR / "nltk_data"]
os.environ.setdefault("NLTK_DATA", os.pathsep.join(str(p) for p in NLTK_DIRS))


# ---------- the settings themselves ----------
# name: (environment variables, in order of preference; default)
SPEC: dict[str, tuple[tuple[str, ...], object]] = {
    # local tier: "builtin" runs llama.cpp inside the app; "ollama" and "openai" talk to a server you run yourself;
    # "apple" is Apple's on-device model (Apple Intelligence). Unset until the user chooses on the setup screen.
    "local_engine": (("BRACKET_LOCAL_ENGINE",), ""),
    "local_model": (("BRACKET_LOCAL_MODEL",), ""),            # a catalog id (builtin) or the server's model name
    "local_model_path": (("BRACKET_LOCAL_MODEL_PATH",), ""),  # builtin only: any GGUF file on disk
    "local_url": (("BRACKET_LOCAL_URL", "OLLAMA_URL"), ""),   # ollama/openai: the server's address
    "local_timeout": (("BRACKET_LOCAL_TIMEOUT",), 8.0),
    # cloud tier: off unless a key is set
    "cloud_api": (("BRACKET_CLOUD_API",), "anthropic"),       # anthropic | bedrock-gateway | off
    "cloud_key": (("BRACKET_CLOUD_KEY", "ANTHROPIC_API_KEY"), ""),
    "cloud_model": (("BRACKET_CLOUD_MODEL",), "claude-sonnet-5-5"),
    "cloud_base_url": (("BRACKET_CLOUD_BASE_URL",), ""),
    "cloud_auth": (("BRACKET_CLOUD_AUTH",), "key"),           # key (x-api-key) | bearer
    "cloud_key_header": (("BRACKET_CLOUD_KEY_HEADER",), ""),
    "cloud_timeout": (("BRACKET_CLOUD_TIMEOUT",), 20.0),
    "bedrock_version": (("BRACKET_BEDROCK_VERSION",), "bedrock-2023-05-31"),
    "claude_prefetch": (("BRACKET_CLAUDE_PREFETCH",), False),
    # the room
    "title": (("BRACKET_TITLE",), ""),       # pre-fills the session title
    "org": (("BRACKET_ORG",), ""),           # a small label under the mark, e.g. your organization's name
    "theme": (("BRACKET_THEME",), "dark"),   # dark (default) | light | system
    "session": (("BRACKET_SESSION",), ""),   # a session name; "new" forces a fresh one
}
SECRET = {"cloud_key"}
_TRUE = ("on", "1", "true", "yes")


def _coerce(name: str, value):
    default = SPEC[name][1]
    if isinstance(default, bool):
        return value if isinstance(value, bool) else str(value).strip().lower() in _TRUE
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return "" if value is None else str(value).strip()


def read_file() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if k in SPEC}
    except (OSError, ValueError):
        return {}


def write_file(changes: dict) -> dict:
    """Merge changes into settings.json (only known names; None or "" removes a setting) and reload."""
    data = read_file()
    for k, v in changes.items():
        if k not in SPEC:
            continue
        if v is None or v == "":
            data.pop(k, None)
        else:
            data[k] = _coerce(k, v)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)  # it may hold an API key
    except OSError:
        pass
    os.replace(tmp, SETTINGS_FILE)
    reload()
    return data


def source_of(name: str) -> str:
    """Where a setting's value comes from: "env:<NAME>", "file" or "default"."""
    for var in SPEC[name][0]:
        if os.environ.get(var):
            return f"env:{var}"
    return "file" if name in read_file() else "default"


def value(name: str):
    envs, default = SPEC[name]
    for var in envs:
        if os.environ.get(var):
            return _coerce(name, os.environ[var])
    file = read_file()
    if name in file:
        return _coerce(name, file[name])
    return default


def public() -> dict:
    """Every setting with its value and source, for the setup screen. A key is never sent back, only its last four."""
    out = {}
    for name in SPEC:
        v = value(name)
        if name in SECRET:
            v = {"set": bool(v), "hint": f"…{v[-4:]}" if len(v) > 8 else ""}
        out[name] = {"value": v, "source": source_of(name)}
    return out


def reload() -> None:
    g = globals()
    eng = value("local_engine").lower()
    if not eng and (value("local_model_path") or any(MODELS_DIR.glob("*.gguf"))):
        eng = "builtin"   # a model downloaded before choosing was a thing (or by hand): keep using it
    g["LOCAL_ENGINE"] = eng
    g["LOCAL_MODEL"] = value("local_model")
    g["LOCAL_MODEL_PATH"] = value("local_model_path")
    url = value("local_url")
    if not url:
        url = "http://127.0.0.1:11434" if g["LOCAL_ENGINE"] == "ollama" else ""
    g["LOCAL_URL"] = url.rstrip("/")
    g["LOCAL_TIMEOUT_S"] = value("local_timeout")

    g["CLOUD_API"] = value("cloud_api").lower()
    g["CLOUD_KEY"] = value("cloud_key")
    g["CLOUD_MODEL"] = value("cloud_model")
    g["CLOUD_BASE_URL"] = value("cloud_base_url") or None
    g["CLOUD_AUTH"] = value("cloud_auth").lower()
    g["CLOUD_KEY_HEADER"] = value("cloud_key_header")
    g["CLOUD_TIMEOUT_S"] = value("cloud_timeout")
    g["BEDROCK_API_VERSION"] = value("bedrock_version")
    g["CLOUD_ENABLED"] = bool(g["CLOUD_KEY"]) and g["CLOUD_API"] != "off" and (g["CLOUD_API"] != "bedrock-gateway" or bool(g["CLOUD_BASE_URL"]))
    g["CLAUDE_PREFETCH"] = value("claude_prefetch")

    g["DOC_TITLE"] = value("title")
    g["ORG"] = value("org")
    g["THEME"] = value("theme").lower() if value("theme").lower() in ("system", "light", "dark") else "dark"
    g["SESSION_ID"] = value("session")


# declared for readers and type checkers; reload() fills them in
LOCAL_ENGINE = LOCAL_MODEL = LOCAL_MODEL_PATH = LOCAL_URL = ""
LOCAL_TIMEOUT_S = 8.0
CLOUD_API = CLOUD_KEY = CLOUD_MODEL = CLOUD_AUTH = CLOUD_KEY_HEADER = BEDROCK_API_VERSION = ""
CLOUD_BASE_URL: str | None = None
CLOUD_TIMEOUT_S = 20.0
CLOUD_ENABLED = CLAUDE_PREFETCH = False
DOC_TITLE = ORG = SESSION_ID = THEME = ""
reload()
