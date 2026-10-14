"""Local inference engine client (llama.cpp llama-server, OpenAI-compatible).

Default OS engine: no API keys, no cloud. Configure via env:
  OSS_LOCAL_URL (default http://127.0.0.1:11400)
  OSS_LOCAL_MODEL ( informational label, e.g. qwen2.5-3b-q4_k_m)
  OSS_LOCAL_TIMEOUT (seconds, default 120)
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class LocalEngineError(RuntimeError):
    pass


class LocalEngine:
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
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200 and r.json().get("status") in ("ok", "loading", "error")
        except (httpx.HTTPError, ValueError):
            return False

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 512) -> dict[str, Any]:
        """Chat completion. Returns {content, model}. Raises LocalEngineError when down."""
        import httpx

        try:
            r = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                json={"messages": messages, "max_tokens": max_tokens, "stream": False},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return {"content": content, "model": self.model_label}
        except Exception as exc:
            raise LocalEngineError(
                "Local engine unreachable. Start it: llama-server -m <model.gguf> --host 127.0.0.1 --port 11400"
            ) from exc
