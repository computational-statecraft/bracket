"""Tier 2: Claude, streamed so the grid fills line by line. Only ever called on an explicit request from the
facilitator (C, or a whole-sentence rewrite). Off unless an API key is set.

Routes (``cloud_api``): ``anthropic`` (the Anthropic API, or a proxy at ``cloud_base_url``); ``bedrock-gateway`` (an
organization's gateway in front of AWS Bedrock that takes a key header instead of AWS signing; ``cloud_base_url``
required); ``off``.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from . import config
from .prompts import RULES


def status() -> dict:
    if config.CLOUD_API == "off":
        return {"ok": False, "model": config.CLOUD_MODEL, "error": "cloud off", "detail": "Turned off in Settings: everything stays on this machine."}
    if not config.CLOUD_KEY:
        return {"ok": False, "model": config.CLOUD_MODEL, "error": "no key", "detail": "Optional. Add an Anthropic API key to offer Claude's proposals on request."}
    if not config.CLOUD_ENABLED:
        return {"ok": False, "model": config.CLOUD_MODEL, "error": "no gateway", "detail": "The Bedrock gateway route needs a base URL in Settings."}
    return {"ok": True, "model": config.CLOUD_MODEL, "api": config.CLOUD_API, "gateway": config.CLOUD_BASE_URL or "api.anthropic.com"}


def _speed_options(model: str) -> dict:
    """Rewording a span needs no reasoning, and thinking costs seconds the room does not have.
    Current models reject non-default sampling parameters, so none are sent."""
    model = model.split("anthropic.")[-1]  # Bedrock IDs: us.anthropic.claude-sonnet-4-6 -> claude-sonnet-4-6
    if model.startswith("claude-sonnet-5-5"):
        return {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}}
    if model.startswith(("claude-opus-5-5", "claude-fable-5")):  # thinking cannot be turned off; keep it shallow
        return {"output_config": {"effort": "low"}}
    if model.startswith(("claude-haiku-5-5", "claude-sonnet-5", "claude-opus-5")):
        return {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}
    return {}  # older models: send nothing they might reject


# Set once a gateway has rejected the thinking/effort fields, so later requests go without them.
_plain = False


_clients: dict = {}


def _client():
    """One client (and so one kept-alive connection to the gateway) per event loop: a new TLS handshake per request
    costs ~100–200 ms the room would wait for."""
    import asyncio

    loop = asyncio.get_running_loop()
    sig = (loop, config.CLOUD_API, config.CLOUD_KEY, config.CLOUD_BASE_URL, config.CLOUD_AUTH, config.CLOUD_KEY_HEADER, config.CLOUD_TIMEOUT_S)
    if sig not in _clients:   # new settings (a key typed on the setup screen) get a new client
        _clients.clear()
        _clients[sig] = _new_client()
    return _clients[sig]


def _new_client():
    from anthropic import AsyncAnthropic

    kw = {"base_url": config.CLOUD_BASE_URL, "timeout": config.CLOUD_TIMEOUT_S, "max_retries": 1}
    if config.CLOUD_API == "bedrock-gateway":
        return _gateway_bedrock(**kw)
    if config.CLOUD_KEY_HEADER:
        kw.update(api_key=config.CLOUD_KEY, default_headers={config.CLOUD_KEY_HEADER: config.CLOUD_KEY})
    elif config.CLOUD_AUTH == "bearer":
        kw.update(auth_token=config.CLOUD_KEY)
    else:
        kw.update(api_key=config.CLOUD_KEY)
    return AsyncAnthropic(**kw)


def _gateway_bedrock(**kw):
    """The SDK's Bedrock client (request shape, model-in-path URLs, AWS event-stream decoding), authenticated with a
    gateway key header instead of AWS request signing."""
    from anthropic import AsyncAnthropicBedrock

    header = config.CLOUD_KEY_HEADER or "x-api-key"
    key = config.CLOUD_KEY

    class GatewayBedrock(AsyncAnthropicBedrock):
        async def _prepare_request(self, request) -> None:
            request.headers[header] = key

    return GatewayBedrock(aws_region="us-east-1", **kw)  # the region only names the default AWS host, unused here


def _extra_body() -> dict:
    return {"extra_body": {"anthropic_version": config.BEDROCK_API_VERSION}} if config.CLOUD_API == "bedrock-gateway" else {}


async def check() -> dict:
    """One tiny real request, so the setup screen shows whether the gateway, key and model work before the room sees it."""
    text, err, ms = "", None, None
    async for ev in stream("Reply with the single word: ready", max_tokens=256, system=None):
        text += ev.get("delta", "")
        err = ev.get("error", err)
        ms = ev.get("ms", ms)
    return {"ok": err is None and bool(text.strip()), "ms": ms, "error": err, "plain": _plain, "model": config.CLOUD_MODEL}


async def stream(prompt: str, max_tokens: int = 1024, system: str | None = RULES) -> AsyncIterator[dict]:
    """Yield {'delta': str} events as text arrives, then {'done': True, 'ms': int}. On error yield {'error': str}.
    prompt is the request; the rules go in the system field, as they do for the local model."""
    t0 = time.perf_counter()
    if not config.CLOUD_ENABLED:
        yield {"error": status().get("detail") or "cloud disabled"}
        return
    global _plain
    from anthropic import BadRequestError

    for attempt in (0, 1):
        sent_text = False
        try:
            async with _client().messages.stream(
                model=config.CLOUD_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **({"system": system} if system else {}),
                **({} if _plain else _speed_options(config.CLOUD_MODEL)),
                **_extra_body(),
            ) as s:
                async for text in s.text_stream:
                    sent_text = True
                    yield {"delta": text}
                final = await s.get_final_message()
            if final.stop_reason == "refusal":
                yield {"error": "Claude declined this request", "ms": int((time.perf_counter() - t0) * 1000)}
                return
            yield {"done": True, "ms": int((time.perf_counter() - t0) * 1000)}
            return
        except BadRequestError as e:
            # a gateway that does not pass the thinking/effort fields through: retry once without them, and remember
            if attempt == 0 and not _plain and not sent_text and _speed_options(config.CLOUD_MODEL):
                _plain = True
                continue
            if attempt == 1:
                _plain = False  # failed without them too, so they were not the problem
            yield {"error": str(e)[:200], "ms": int((time.perf_counter() - t0) * 1000)}
            return
        except Exception as e:  # noqa: BLE001
            yield {"error": str(e)[:200], "ms": int((time.perf_counter() - t0) * 1000)}
            return
