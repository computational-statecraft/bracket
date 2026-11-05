"""Tests never touch the real data folder: BRACKET_DATA points at a temporary one unless the caller set it."""
import os
import tempfile

os.environ.setdefault("BRACKET_DATA", tempfile.mkdtemp(prefix="bracket-test-"))
for var in ("BRACKET_LOCAL_ENGINE", "BRACKET_LOCAL_MODEL", "BRACKET_LOCAL_MODEL_PATH", "BRACKET_LOCAL_URL", "OLLAMA_URL",
            "BRACKET_CLOUD_API", "BRACKET_CLOUD_KEY", "ANTHROPIC_API_KEY", "BRACKET_CLOUD_BASE_URL", "BRACKET_SESSION"):
    os.environ.pop(var, None)
