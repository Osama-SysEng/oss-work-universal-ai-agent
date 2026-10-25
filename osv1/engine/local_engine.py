"""Local inference engine client (llama.cpp llama-server, OpenAI-compatible).

The engine is the only reasoning backend OSS Work uses. It runs on the user's
own machine, needs no API key, and speaks the OpenAI chat-completions shape so
a different local runtime can be swapped in without touching the layers.

Environment:
    OSS_LOCAL_URL     default http://127.0.0.1:11400
    OSS_LOCAL_MODEL   informational label, e.g. qwen2.5-3b-q4_k_m
    OSS_LOCAL_TIMEOUT seconds, default 120
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class LocalEngineError(RuntimeError):
    """Raised when the local engine cannot serve a request."""


class LocalEngine:
    """A thin, honest client for a locally served model."""

    def __init__(
        self,
        base_url: str | None = None,
        model_label: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OSS_LOCAL_URL", "http://127.0.0.1:11400")).rstrip("/")
        self.model_label = model_label or os.getenv("OSS_LOCAL_MODEL", "local")
        self.timeout = float(timeout or os.getenv("OSS_LOCAL_TIMEOUT", "120"))

    def health(self) -> bool:
        """True when the engine answers its health endpoint."""
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False

    def models(self) -> list[dict[str, Any]]:
        """Model ids the engine reports, when it reports any.

        llama.cpp answers with ``models`` and OpenAI-compatible servers with
        ``data``; both are read, because a measurement that names its model
        has to get the name from whichever shape the server speaks.
        """
        try:
            response = httpx.get(f"{self.base_url}/v1/models", timeout=5)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, KeyError):
            return []
        if not isinstance(payload, dict):
            return []
        raw = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("models")
        if not isinstance(raw, list):
            return []
        return [entry for entry in raw if isinstance(entry, dict)]

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 512, temperature: float = 0.0) -> dict[str, Any]:
        """Chat completion. Returns ``{"content", "model"}``; raises when down."""
        try:
            response = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                json={"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {"content": content, "model": self.model_label}
        except Exception as exc:  # noqa: BLE001 - the caller needs one clear failure
            raise LocalEngineError(
                "Local engine unreachable. Start it with: llama-server -m <model.gguf> --host 127.0.0.1 --port 11400"
            ) from exc

    def describe(self) -> dict[str, Any]:
        """What the engine is, as the engine reports it.

        The label is what the operator configured; the id below is what the
        server says it is serving. A measurement that names its model has to
        name it from the source, not from an environment variable, so the
        reported id wins and the label is kept beside it.
        """
        reported = ""
        for entry in self.models():
            identifier = entry.get("id") or entry.get("name")
            if isinstance(identifier, str) and identifier.strip():
                # The server may report a whole path; the file name is the
                # model's identity, and the path is the operator's machine.
                reported = identifier.strip().replace("\\", "/").rsplit("/", 1)[-1]
                break
        return {
            "base_url": self.base_url,
            "model": reported or self.model_label,
            "model_label": self.model_label,
            "reported_by_engine": bool(reported),
            "timeout_s": self.timeout,
            "healthy": self.health(),
        }
