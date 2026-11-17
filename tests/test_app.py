"""Settings, the model catalog and downloader, the built-in engine's command line, the local model's OpenAI-compatible
stream, and the server's protections. No network: HTTP is mocked."""
import asyncio
import hashlib
import json

import httpx
import pytest

from backend import config, engine, local_llm, models


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.reload()
    yield tmp_path / "settings.json"
    monkeypatch.undo()
    config.reload()


# ---------- settings ----------

def test_settings_layers_env_over_file_over_default(settings_file, monkeypatch):
    assert config.value("cloud_model") == "claude-sonnet-5-5" and config.source_of("cloud_model") == "default"
    config.write_file({"cloud_model": "claude-haiku-5-5"})
    assert config.CLOUD_MODEL == "claude-haiku-5-5" and config.source_of("cloud_model") == "file"
    monkeypatch.setenv("BRACKET_CLOUD_MODEL", "from-env")
    config.reload()
    assert config.CLOUD_MODEL == "from-env" and config.source_of("cloud_model") == "env:BRACKET_CLOUD_MODEL"


def test_a_key_is_never_sent_back_whole(settings_file):
    config.write_file({"cloud_key": "sk-ant-secret-abcd"})
    pub = config.public()["cloud_key"]["value"]
    assert pub == {"set": True, "hint": "…abcd"} and config.CLOUD_ENABLED
    config.write_file({"cloud_key": ""})
    assert not config.CLOUD_ENABLED and "cloud_key" not in json.loads(settings_file.read_text())


def test_unknown_settings_are_ignored_and_types_coerced(settings_file):
    config.write_file({"nope": 1, "claude_prefetch": "yes", "local_timeout": "3"})
    assert config.CLAUDE_PREFETCH is True and config.LOCAL_TIMEOUT_S == 3.0
    assert "nope" not in json.loads(settings_file.read_text())


def test_gateway_route_needs_a_base_url(settings_file):
    config.write_file({"cloud_key": "k" * 20, "cloud_api": "bedrock-gateway"})
    assert not config.CLOUD_ENABLED
    config.write_file({"cloud_base_url": "https://gateway.example/bedrock"})
    assert config.CLOUD_ENABLED


# ---------- models ----------

def test_catalog_entries_are_pinned_and_complete():
    for m in models.CATALOG:
        assert len(m["rev"]) == 40 and len(m["sha256"]) == 64 and m["file"].endswith(".gguf") and m["bytes"] > 0


def test_recommendation_follows_memory():
    assert models.recommended(8) == "gemma-4-e2b"
    assert models.recommended(16) == "gemma-4-e4b"
    assert models.recommended(64) == "gemma-4-26b-a4b"
    assert models.recommended(0) == "gemma-4-e2b"   # unknown memory: the lightest


def test_download_resumes_verifies_and_selects(tmp_path, monkeypatch, settings_file):
    payload = b"GGUF" + bytes(range(256)) * 40
    entry = {"id": "fake", "label": "Fake", "note": "", "repo": "o/r", "rev": "0" * 40, "file": "fake.gguf",
             "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "min_ram_gb": 1}
    monkeypatch.setattr(models, "CATALOG", [entry])
    monkeypatch.setattr(models, "BY_ID", {"fake": entry})
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "fake.part").write_bytes(payload[:100])   # an interrupted earlier attempt
    seen = []

    def handler(request):
        seen.append(request.headers.get("range"))
        start = int(request.headers["range"].split("=")[1].rstrip("-")) if "range" in request.headers else 0
        return httpx.Response(206 if start else 200, content=payload[start:])

    real = httpx.AsyncClient
    monkeypatch.setattr(models.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    monkeypatch.setattr("backend.engine.binary", lambda: None)   # no real engine to start

    async def run():
        assert models.start_download("fake", use=True)["ok"]
        await models._tasks["fake"]
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert seen == ["bytes=100-"]
    assert models.installed(entry) and models._jobs["fake"]["state"] == "done"
    assert config.LOCAL_ENGINE == "builtin" and config.LOCAL_MODEL == "fake" and models.chosen_path().name == "fake.gguf"


def test_a_corrupt_download_is_deleted(tmp_path, monkeypatch, settings_file):
    entry = {"id": "bad", "label": "Bad", "note": "", "repo": "o/r", "rev": "0" * 40, "file": "bad.gguf",
             "bytes": 10, "sha256": "0" * 64, "min_ram_gb": 1}
    monkeypatch.setattr(models, "BY_ID", {"bad": entry})
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    real = httpx.AsyncClient
    monkeypatch.setattr(models.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 10)), **kw))

    async def run():
        models.start_download("bad")
        await models._tasks["bad"]

    asyncio.run(run())
    assert models._jobs["bad"]["state"] == "failed" and "checksum" in models._jobs["bad"]["error"]
    assert not list(tmp_path.glob("bad*"))


def test_not_enough_disk_is_refused_before_downloading(monkeypatch):
    entry = {**models.CATALOG[0], "id": "huge", "bytes": 10 ** 15}
    monkeypatch.setattr(models, "BY_ID", {"huge": entry})
    res = models.start_download("huge")
    assert not res["ok"] and "disk space" in res["error"]


# ---------- the built-in engine ----------

def test_engine_command_binds_to_this_machine_only(tmp_path):
    cmd = engine.command(tmp_path / "llama-server", tmp_path / "m.gguf", 4321)
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1" and cmd[cmd.index("--port") + 1] == "4321" and "-m" in cmd


def test_engine_reports_a_missing_binary(monkeypatch):
    monkeypatch.setattr(engine, "binary", lambda: None)
    st = asyncio.run(engine.ensure())
    assert st["state"] == "no-binary"


# ---------- the local model's OpenAI-compatible stream ----------

def test_openai_compatible_stream_is_parsed(monkeypatch):
    sse = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n" for t in ["urge\n", "call ", "upon\n"]) + "data: [DONE]\n\n"
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(config, "LOCAL_ENGINE", "openai")
    monkeypatch.setattr(config, "LOCAL_URL", "http://local.test/v1")
    monkeypatch.setattr(config, "LOCAL_MODEL", "some-model")

    async def run():
        local_llm._clients.clear()
        loop = asyncio.get_running_loop()
        local_llm._clients[loop] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return await local_llm.complete([{"role": "user", "content": "x"}], 3)

    res = asyncio.run(run())
    assert res["ok"] and res["lines"] == ["urge", "call upon"]
    assert sent["model"] == "some-model" and sent["stream"] is True


# ---------- the server's protections ----------

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from backend.app import app

    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_writes_need_the_bracket_header(client):
    assert client.post("/api/event", json={"kind": "x"}).status_code == 403
    assert client.post("/api/event", json={"kind": "x"}, headers={"X-Bracket": "1"}).status_code == 200


def test_requests_for_another_host_are_refused(client):
    assert client.get("/api/settings", headers={"Host": "attacker.example"}).status_code == 403
    assert client.get("/api/settings").status_code == 200


def test_requests_a_browser_marks_cross_site_are_refused(client):
    assert client.get("/api/status", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/status", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_settings_api_rejects_unknown_names(client, settings_file):
    r = client.post("/api/settings", json={"bogus": 1}, headers={"X-Bracket": "1"})
    assert r.status_code == 400


def test_builtin_engine_starts_answers_and_stops(tmp_path, monkeypatch):
    """The real process management, with a fake llama-server: start, wait for health, stream proposals, stop."""
    import sys
    from pathlib import Path

    fake = Path(__file__).with_name("fake_llama_server.py")
    model = tmp_path / "m.gguf"
    model.write_bytes(b"GGUF")
    monkeypatch.setattr(engine, "binary", lambda: Path(sys.executable))
    monkeypatch.setattr(engine, "command", lambda exe, m, port: [sys.executable, str(fake), "--port", str(port)])
    monkeypatch.setattr(models, "chosen_path", lambda: model)
    monkeypatch.setattr(config, "LOCAL_ENGINE", "builtin")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")

    async def run():
        local_llm._clients.clear()
        st = await engine.ensure()
        assert st["state"] == "ready", st
        proc = engine._proc
        again = await engine.ensure()            # idempotent: the same process
        assert again["state"] == "ready" and engine._proc is proc
        chk = await local_llm.check()
        await engine.stop()
        return chk, proc

    chk, proc = asyncio.run(run())
    assert chk["ok"] and chk["sample"] == ["urge", "call upon"], chk
    assert proc.poll() is not None and engine.status()["state"] == "off"



# ---------- choosing the local model: what is on this computer first ----------

def _ollama_tags(models_):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": n, "size": 3_000_000_000} for n in models_]})
    return handler


def _patch_http(monkeypatch, handler):
    real = httpx.AsyncClient

    def client():
        return real(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(local_llm, "_http", client)


def test_a_fresh_install_has_no_model_chosen(settings_file):
    assert config.LOCAL_ENGINE == ""
    st = asyncio.run(local_llm.status())
    assert not st["ok"] and st["state"] == "unchosen"


def test_ollama_models_are_found_and_preferred(monkeypatch, settings_file, client):
    _patch_http(monkeypatch, _ollama_tags(["nomic-embed-text:latest", "llama3.2:3b", "gemma3:4b"]))
    o = client.get("/api/local/options").json()
    assert o["ollama"]["running"] and [m["name"] for m in o["ollama"]["models"]] == ["llama3.2:3b", "gemma3:4b"]   # no embedding models
    assert o["recommended"] == {"engine": "ollama", "model": "gemma3:4b"} and not o["current"]["chosen"]


def test_without_ollama_the_recommendation_is_a_download(monkeypatch, settings_file, client):
    def refuse(request):
        raise httpx.ConnectError("refused")

    _patch_http(monkeypatch, refuse)
    o = client.get("/api/local/options").json()
    assert not o["ollama"]["running"] and o["recommended"]["engine"] in ("builtin", "apple")


def test_choosing_an_ollama_model_is_remembered(monkeypatch, settings_file, client):
    _patch_http(monkeypatch, _ollama_tags(["gemma3:4b"]))
    r = client.post("/api/local/use", json={"engine": "ollama", "model": "gemma3:4b"}, headers={"X-Bracket": "1"})
    assert r.json()["ok"] and config.LOCAL_ENGINE == "ollama" and config.LOCAL_MODEL == "gemma3:4b"
    assert json.loads(settings_file.read_text())["local_engine"] == "ollama"
    assert asyncio.run(local_llm.status())["ok"]


def test_apple_model_says_why_it_is_unavailable(monkeypatch, settings_file, client):
    import sys

    from backend import apple_llm

    apple_llm._cache["v"] = None
    st = apple_llm.status(0)
    if sys.platform != "darwin":
        assert st == {"available": False, "reason": "only on a Mac"}
    r = client.post("/api/local/use", json={"engine": "apple"}, headers={"X-Bracket": "1"})
    if not st["available"]:
        assert r.status_code == 400 and r.json()["error"] == st["reason"] and config.LOCAL_ENGINE == ""


def test_apple_snapshots_become_deltas(monkeypatch):
    """The SDK streams the whole answer so far each time; bracket's pipeline expects pieces."""
    import types

    from backend import apple_llm

    class Session:
        def __init__(self, instructions=None, model=None):
            assert instructions == "RULES"

        def stream_response(self, prompt, options=None):
            async def gen():
                for snap in ["urge", "urge\ncall", "urge\ncall upon", "urge\nrequest"]:
                    yield snap
            return gen()

    fm = types.SimpleNamespace(SystemLanguageModel=lambda **k: None, LanguageModelSession=Session,
                               GenerationOptions=lambda **k: None,
                               SystemLanguageModelGuardrails=types.SimpleNamespace(PERMISSIVE_CONTENT_TRANSFORMATIONS=1))
    monkeypatch.setattr(apple_llm, "_sdk", lambda: fm)
    monkeypatch.setattr(apple_llm, "status", lambda *a: {"available": True, "reason": ""})
    monkeypatch.setattr(config, "LOCAL_ENGINE", "apple")
    res = asyncio.run(local_llm.complete([{"role": "system", "content": "RULES"}, {"role": "user", "content": "x"}], 3))
    assert res["ok"] and res["lines"] == ["urge", "request"]
