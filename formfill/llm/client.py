"""LLM access: an OpenAI-compatible chat client (OpenRouter by default, also works with
Ollama / LM Studio / vLLM via ``LLM_BASE_URL``) plus robust JSON extraction."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    def complete(self, messages: list[dict], *, json_mode: bool = True) -> str: ...


class OpenAICompatibleChat:
    def __init__(self, api_key: str | None, model: str, base_url: str, timeout: float = 90,
                 retries: int = 2, temperature: float = 0.2, transport=None):
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.retries = retries
        self.temperature = temperature
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def complete(self, messages: list[dict], *, json_mode: bool = True) -> str:
        headers = {"Content-Type": "application/json",
                   "HTTP-Referer": "https://github.com/aiteam-hiring-assigment",
                   "X-Title": "AI Form Filler"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._client.post(self.url, headers=headers, json=payload)
                if resp.status_code == 400 and json_mode and "response_format" in payload:
                    # Some free models do not support JSON mode; the prompt still asks for JSON.
                    payload.pop("response_format")
                    continue
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                if not content:
                    raise LLMError("empty completion")
                return content
            except (httpx.HTTPError, LLMError, KeyError, IndexError, ValueError) as exc:
                last = exc
                log.warning("LLM call failed (attempt %d): %s", attempt + 1, exc)
                time.sleep(min(2 ** attempt, 8))
        raise LLMError(f"LLM request failed: {last}")


def extract_json(text: str) -> dict:
    """Parse the first JSON object in a completion (tolerates ```json fences / chatter)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        raise LLMError("no JSON object in completion")
    depth, in_str, escape = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"invalid JSON: {exc}") from exc
                if not isinstance(data, dict):
                    raise LLMError("JSON is not an object")
                return data
    raise LLMError("unterminated JSON object")
