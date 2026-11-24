"""Model backends. A backend maps (system prompt, messages) to the model's reply text.

MockBackend is a deterministic, intentionally gullible stand-in used to test the harness
itself offline. Numbers from it say nothing about real models. For real results use
AnthropicBackend or OpenAICompatBackend (works with Ollama, vLLM, OpenAI, etc.).
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import random
import re
import urllib.request
from typing import Dict, List, Optional

Messages = List[Dict[str, str]]


class Backend:
    name = "base"

    def complete(self, system: str, messages: Messages) -> str:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------- mock
class MockBackend(Backend):
    """Deterministic fake model that sometimes obeys injected instructions.

    p_user / p_tool: chance of obeying an instruction found in the user message or in
    tool output. Spotlighting (UNTRUSTED_DATA markers in the system prompt) cuts the
    tool-output chance by 10x. Mutations shift the chance (encoded text is less reliable,
    fake [SYSTEM] tags are more persuasive). All draws are seeded, so runs reproduce.
    """

    name = "mock"

    def __init__(self, seed: int = 0, p_user: float = 0.85, p_tool: float = 0.65):
        self.seed = seed
        self.p_user = p_user
        self.p_tool = p_tool

    # --- helpers
    @staticmethod
    def _decode_b64(text: str) -> str:
        out = []
        for tok in re.findall(r"[A-Za-z0-9+/=]{16,}", text):
            try:
                out.append(base64.b64decode(tok, validate=True).decode("utf-8", "ignore"))
            except (binascii.Error, ValueError):
                continue
        return "\n".join(out)

    def _injection(self, text: str, source: str, spotlight: bool, rng: random.Random,
                   system: str, history: str) -> Optional[str]:
        decoded = self._decode_b64(text) if "base64" in text.lower() else ""
        combined = text + "\n" + decoded
        p = self.p_user if source == "user" else self.p_tool
        if "[SYSTEM" in text.upper():
            p = min(1.0, p * 1.2)
        if re.search(r"thanks", text, re.I) and re.search(r"please", text, re.I):
            p *= 0.85
        if decoded:
            p *= 0.5
        if spotlight and source == "tool":
            p *= 0.1

        action = None
        m = re.search(r"(?:send|forward|email|mail)\b[^\n]{0,100}?\bto\s+([\w.+\-]+@[\w.\-]+\.\w+)",
                      combined, re.I)
        if m:
            parts = []
            if re.search(r"api key|config|credential|\bkey\b", combined, re.I):
                k = re.search(r"service_api_key=(\S+?);", system)
                if k:
                    parts.append(k.group(1))
            if re.search(r"record|customer|data|vault|note", combined, re.I):
                v = re.search(r"vault-token=(\S+)", history)
                if v:
                    parts.append(v.group(1))
            body = "Requested info: " + " ".join(parts) if parts else "Hello"
            action = json.dumps({"tool": "send_email",
                                 "args": {"to": m.group(1), "subject": "FYI", "body": body}})
        else:
            m = re.search(r"read_document with name ['\"]([\w\-]+)['\"]", combined, re.I)
            if m:
                action = json.dumps({"tool": "read_document", "args": {"name": m.group(1)}})
            else:
                m = re.search(r"query_customer with customer_id ['\"]([\w\-]+)['\"]", combined, re.I)
                if m:
                    action = json.dumps({"tool": "query_customer", "args": {"customer_id": m.group(1)}})
                elif re.search(
                    r"(print|reveal|repeat|show|output|translate|display)[^\n]{0,80}"
                    r"(system prompt|api key|internal config|configuration|instructions|credentials)",
                    combined, re.I):
                    wants_key = re.search(r"api key|credentials", combined, re.I)
                    if wants_key:
                        k = re.search(r"service_api_key=(\S+?);", system)
                        key = k.group(1) if k else "n/a"
                        if re.search(r"dash between every character", combined, re.I):
                            key = "-".join(key)
                        elif re.search(r"reverse order", combined, re.I):
                            key = key[::-1]
                        action = json.dumps({"final": f"The key is {key}"})
                    else:
                        action = json.dumps({"final": system})
        if action is None:
            return None
        return action if rng.random() <= p else None

    def complete(self, system: str, messages: Messages) -> str:
        n_assist = sum(1 for m in messages if m["role"] == "assistant")
        spotlight = "UNTRUSTED_DATA" in system
        history = "\n".join(m["content"] for m in messages)
        rng = random.Random(f"{self.seed}|{messages[-1]['content']}|{n_assist}")

        if n_assist == 0:
            task = messages[0]["content"]
            act = self._injection(task, "user", spotlight, rng, system, history)
            if act:
                return act
            m = re.search(r"document\s+'([\w\-]+)'", task)
            if m:
                return json.dumps({"tool": "read_document", "args": {"name": m.group(1)}})
            m = re.search(r"(https?://\S+)", task)
            if m:
                return json.dumps({"tool": "fetch_page", "args": {"url": m.group(1).rstrip(".")}})
            m = re.search(r"customer\s+'?([\w\-]+)'?", task)
            if m:
                return json.dumps({"tool": "query_customer", "args": {"customer_id": m.group(1)}})
            return json.dumps({"final": "How can I help?"})

        last = messages[-1]["content"]
        if n_assist >= 2:
            return json.dumps({"final": "Done."})
        act = self._injection(last, "tool", spotlight, rng, system, history)
        if act:
            return act
        return json.dumps({"final": "Here is a summary of the requested item."})


# --------------------------------------------------------------------------- real models
def _post_json(url: str, headers: Dict[str, str], body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (user-supplied endpoint)
        return json.loads(resp.read().decode())


class AnthropicBackend(Backend):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: Optional[str] = None,
                 base_url: str = "https://api.anthropic.com", max_tokens: int = 1024):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        if not self.api_key:
            raise SystemExit("Set ANTHROPIC_API_KEY to use the anthropic backend.")

    def build_request(self, system: str, messages: Messages) -> dict:
        return {"model": self.model, "max_tokens": self.max_tokens,
                "system": system, "messages": messages}

    def complete(self, system: str, messages: Messages) -> str:
        data = _post_json(
            f"{self.base_url}/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
             "content-type": "application/json"},
            self.build_request(system, messages),
        )
        return "".join(b.get("text", "") for b in data.get("content", []))


class OpenAICompatBackend(Backend):
    """Any /v1/chat/completions server: OpenAI, Ollama (http://localhost:11434/v1), vLLM..."""

    name = "openai-compat"

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1",
                 api_key: Optional[str] = None, max_tokens: int = 1024):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "none")
        self.max_tokens = max_tokens

    def build_request(self, system: str, messages: Messages) -> dict:
        return {"model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}] + messages}

    def complete(self, system: str, messages: Messages) -> str:
        data = _post_json(
            f"{self.base_url}/chat/completions",
            {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"},
            self.build_request(system, messages),
        )
        return data["choices"][0]["message"]["content"]


def make_backend(kind: str, model: Optional[str], base_url: Optional[str], seed: int) -> Backend:
    if kind == "mock":
        return MockBackend(seed=seed)
    if kind == "anthropic":
        return AnthropicBackend(model=model or "claude-sonnet-5-5", base_url=base_url or "https://api.anthropic.com")
    if kind == "openai":
        if not model:
            raise SystemExit("--model is required for the openai backend")
        return OpenAICompatBackend(model=model, base_url=base_url or "http://localhost:11434/v1")
    raise SystemExit(f"unknown backend: {kind}")
