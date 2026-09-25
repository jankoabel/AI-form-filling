import json

import httpx
import pytest

from formfill.llm import client as llm_client
from formfill.llm.client import LLMError, OpenAICompatibleChat, extract_json


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Tu je výsledok:\n```json\n{"a": "b}"}\n```') == {"a": "b}"}
    assert extract_json('prefix {"a": {"b": [1, 2]}} suffix') == {"a": {"b": [1, 2]}}
    with pytest.raises(LLMError):
        extract_json("no json here")
    with pytest.raises(LLMError):
        extract_json('{"a": ')


def _chat(handler):
    return OpenAICompatibleChat("key", "google/gemma-4-31b-it:free", "https://openrouter.test/api/v1",
                                retries=2, transport=httpx.MockTransport(handler))


def test_openrouter_request_shape_and_retry(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    assert _chat(handler).complete([{"role": "user", "content": "hi"}]) == '{"ok": true}'
    body = json.loads(calls[-1].content)
    assert calls[-1].url.path == "/api/v1/chat/completions"
    assert calls[-1].headers["Authorization"] == "Bearer key"
    assert body["model"] == "google/gemma-4-31b-it:free" and body["response_format"] == {"type": "json_object"}


def test_json_mode_dropped_when_unsupported():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format not supported"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    assert _chat(handler).complete([{"role": "user", "content": "x"}]) == "{}"
    assert "response_format" not in bodies[-1]


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    with pytest.raises(LLMError):
        _chat(lambda r: httpx.Response(503)).complete([{"role": "user", "content": "x"}])
