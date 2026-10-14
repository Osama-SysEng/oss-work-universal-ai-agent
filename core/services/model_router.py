"""
Model Router — local-only routing for oss-work OS v1.

Routes tasks to the independent local engine (llama-server) and,
optionally, a user-installed Ollama. Cloud and browser providers were
removed: no API keys, no external calls.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import os
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Model categories ──────────────────────────────────────────


class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    XAI = "xai"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    HUGGINGFACE = "huggingface"
    TOGETHER = "together"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    LOCAL = "local"
    BROWSER = "browser"


@dataclass
class ModelInfo:
    """Information about a supported model."""

    id: str
    name: str
    provider: ModelProvider
    category: str
    context_window: int
    supports_vision: bool = False
    supports_streaming: bool = True
    cost_per_1k_tokens: float = 0.0  # 0 = local, no billing
    api_available: bool = True
    default_for: list[str] = field(default_factory=list)


# ── Model Registry ────────────────────────────────────────────

MODELS = [
    # ── American ──
    ModelInfo(
        "gpt4o",
        "GPT-4o",
        ModelProvider.OPENAI,
        "general",
        context_window=128000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "gpt4o_mini",
        "GPT-4o Mini",
        ModelProvider.OPENAI,
        "general",
        context_window=128000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "chatgpt_free",
        "ChatGPT Free",
        ModelProvider.OPENAI,
        "general",
        context_window=30000,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "claude",
        "Claude",
        ModelProvider.ANTHROPIC,
        "general",
        context_window=200000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "gemini_pro",
        "Gemini Pro",
        ModelProvider.GOOGLE,
        "general",
        context_window=128000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "gemini_flash",
        "Gemini Flash",
        ModelProvider.GOOGLE,
        "fast",
        context_window=128000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "grok",
        "Grok",
        ModelProvider.XAI,
        "general",
        context_window=131072,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "perplexity",
        "Perplexity",
        ModelProvider.OPENAI,
        "search",
        context_window=50000,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "copilot",
        "Microsoft Copilot",
        ModelProvider.GOOGLE,
        "general",
        context_window=128000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    # ── Chinese ──
    ModelInfo(
        "kimi",
        "Kimi (Moonshot)",
        ModelProvider.GOOGLE,
        "general",
        context_window=200000,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "qwen",
        "Qwen (Alibaba)",
        ModelProvider.GOOGLE,
        "general",
        context_window=128000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "deepseek",
        "DeepSeek",
        ModelProvider.DEEPSEEK,
        "general",
        context_window=128000,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "deepseek_coder",
        "DeepSeek Coder",
        ModelProvider.DEEPSEEK,
        "code",
        context_window=128000,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "ernie",
        "Baidu ERNIE",
        ModelProvider.GOOGLE,
        "general",
        context_window=100000,
        supports_vision=True,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    ModelInfo(
        "glm",
        "Zhipu GLM",
        ModelProvider.GOOGLE,
        "general",
        context_window=128000,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=False,
    ),
    # ── Local ──
    ModelInfo(
        "ollama_llama3",
        "Ollama Llama 3",
        ModelProvider.OLLAMA,
        "general",
        context_window=8192,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "ollama_llama3_70b",
        "Ollama Llama 3 70B",
        ModelProvider.OLLAMA,
        "general",
        context_window=8192,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "ollama_mistral",
        "Ollama Mistral",
        ModelProvider.OLLAMA,
        "general",
        context_window=8192,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "lm_studio",
        "LM Studio",
        ModelProvider.LOCAL,
        "general",
        context_window=4096,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "gpt4all",
        "GPT4All",
        ModelProvider.LOCAL,
        "general",
        context_window=4096,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "llama_cpp",
        "llama.cpp",
        ModelProvider.LOCAL,
        "general",
        context_window=4096,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "oss_local",
        "oss-work Local Engine (llama-server + Qwen2.5-3B Q4_K_M, no keys)",
        ModelProvider.LOCAL,
        "general",
        context_window=4096,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
        default_for=["general_chat", "offline_fallback"],
    ),
    # ── Open-source APIs ──
    ModelInfo(
        "huggingface",
        "HuggingFace Inference",
        ModelProvider.HUGGINGFACE,
        "general",
        context_window=4096,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "together_llama",
        "Together AI Llama",
        ModelProvider.TOGETHER,
        "general",
        context_window=8192,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "groq_llama",
        "Groq Llama",
        ModelProvider.GROQ,
        "fast",
        context_window=8192,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
    ModelInfo(
        "openrouter",
        "OpenRouter Free",
        ModelProvider.OPENROUTER,
        "general",
        context_window=4096,
        supports_vision=False,
        cost_per_1k_tokens=0.0,
        api_available=True,
    ),
]


# ── Routing Table ─────────────────────────────────────────────

ROUTING_TABLE: dict[str, list[str]] = {
    "long_form_writing": ["claude", "gpt4o", "gemini_pro", "kimi", "qwen"],
    "code_generation": ["gpt4o", "deepseek_coder", "qwen", "ollama_llama3", "groq_llama"],
    "arabic_content": ["kimi", "qwen", "gemini_pro", "chatgpt_free"],
    "chinese_content": ["kimi", "qwen", "ernie", "glm"],
    "fast_response": ["groq_llama", "gemini_flash", "deepseek", "ollama_mistral"],
    "image_analysis": ["gpt4o", "gemini_pro", "claude"],
    "reasoning": ["gpt4o", "deepseek", "qwen", "claude"],
    "security_analysis": ["claude", "gpt4o", "deepseek"],
    "search_research": ["perplexity", "gemini_pro", "chatgpt_free"],
    "coding_help": ["gpt4o", "deepseek_coder", "qwen", "groq_llama"],
    "creative_writing": ["claude", "gpt4o", "kimi", "gemini_pro"],
    "translation": ["gemini_pro", "qwen", "kimi", "chatgpt_free"],
    "summarization": ["gemini_flash", "groq_llama", "ollama_mistral", "chatgpt_free"],
    "general_chat": ["chatgpt_free", "gemini_flash", "claude", "gemini_pro"],
    "markdown_formatting": ["gemini_flash", "groq_llama", "chatgpt_free"],
    "html_generation": ["gpt4o", "deepseek_coder", "qwen", "groq_llama"],
    "offline_fallback": ["oss_local", "llama_cpp", "ollama_llama3", "lm_studio", "gpt4all"],
}


# ── Model Router ──────────────────────────────────────────────


class ModelRouter:
    """
    Routes tasks to the best available AI model at zero cost.

    Uses a priority-based routing table, failover between candidates,
    and a local fallback for offline scenarios.

    Zero-cost routes:
    - Browser simulation (when user is logged into model's website)
    - Local models (Ollama, LM Studio)
    - Free API tiers (when available)
    """

    def __init__(self, default_model: str = "gemini_flash") -> None:
        self.default_model = default_model
        self._model_map = {m.id: m for m in MODELS}
        self._usage_log: list[dict[str, Any]] = []

    def classify_task(self, task: str) -> str:
        """Classify a task into a routing category."""
        task_lower = task.lower()

        if any(
            kw in task_lower
            for kw in [
                "code",
                "function",
                "class",
                "python",
                "javascript",
                "typescript",
                "api",
                "endpoint",
                "algorithm",
                "debug",
                "fix",
                "refactor",
                "implement",
            ]
        ):
            return "code_generation"

        if any(
            kw in task_lower
            for kw in ["image", "picture", "photo", "screenshot", "visual", "chart", "graph", "diagram"]
        ):
            return "image_analysis"

        if any(kw in task_lower for kw in ["arabic", "العربية", "عربي", "فصحى", "امي calibrate"]):
            return "arabic_content"

        if any(kw in task_lower for kw in ["chinese", "中文", "中国", "汉语"]):
            return "chinese_content"

        if any(
            kw in task_lower
            for kw in ["write", "article", "blog", "story", "essay", "creative", "novel", " poem", "narrative"]
        ):
            return "creative_writing"

        if any(
            kw in task_lower for kw in ["search", "research", "find", "look up", "investigate", "discover", "explore"]
        ):
            return "search_research"

        if any(kw in task_lower for kw in ["fast", "quick", "instant", "immediate", "urgent"]):
            return "fast_response"

        if any(kw in task_lower for kw in ["summarize", "summary", "tl;dr", "brief", "short"]):
            return "summarization"

        if any(
            kw in task_lower for kw in ["translate", "translation", "arabic", "chinese", "spanish", "french", "german"]
        ):
            return "translation"

        if any(kw in task_lower for kw in ["html", "css", "javascript", "frontend", "ui", "web page", "website"]):
            return "html_generation"

        if any(kw in task_lower for kw in ["analyze", "security", "vulnerability", "audit", "review", "check"]):
            return "security_analysis"

        if any(
            kw in task_lower
            for kw in ["reason", "think", "logic", "philosophy", "argument", "debate", "analyze deeply"]
        ):
            return "reasoning"

        if any(
            kw in task_lower for kw in ["long", "detailed", "comprehensive", "thorough", "complete guide", "in-depth"]
        ):
            return "long_form_writing"

        return "general_chat"

    def get_candidates(self, task_type: str) -> list[str]:
        """Get ordered list of candidate model IDs for a task type."""
        return ROUTING_TABLE.get(task_type, [self.default_model])

    def get_provider(self, model_id: str) -> ModelInfo | None:
        """Get model info by ID."""
        return self._model_map.get(model_id)

    async def is_available(self, model_id: str) -> bool:
        """Check if a model is available (API key set or browser accessible)."""
        model = self._model_map.get(model_id)
        if not model:
            return False

        if model.provider == ModelProvider.OLLAMA:
            return await self._check_ollama()
        elif model.provider == ModelProvider.LOCAL:
            return await self._check_local()
        else:
            # OS v1 is local-only: cloud/browser providers were removed.
            return False

    async def _check_ollama(self) -> bool:
        """Check if Ollama is running locally."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get("http://localhost:11434/api/tags")
                return r.status_code == 200
        except Exception as _exc:
            logger.exception("Unhandled exception in model_router.py")
            return False

    async def _check_local(self) -> bool:
        """Check if any local inference server is running (oss engine first)."""
        import httpx

        local_url = os.getenv("OSS_LOCAL_URL", "http://127.0.0.1:11400").rstrip("/")
        try:
            port = int(local_url.rsplit(":", 1)[-1].rstrip("/"))
        except ValueError:
            port = 11400
        ports = [port, 11400, 1234, 8080, 5000]
        for seen_port in dict.fromkeys(ports):
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    r = await client.get(
                        f"http://localhost:{seen_port}/health",
                        timeout=3.0,
                    )
                    if r.status_code == 200:
                        return True
            except Exception as _exc:  # noqa: BLE001 - preserve broad catch; logged below
                logger.debug("Suppressed exception in model_router.py: %s", _exc)
                continue
        return False

    async def complete(
        self,
        task: str,
        requirements: dict[str, Any] | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Route a task to the best available model and return the response.

        Tries candidates in order, failover on failure, local fallback last.
        """
        started = time.monotonic()
        req = requirements or {}

        # Determine task type and candidates
        task_type = self.classify_task(task)
        if model_id:
            candidates = [model_id]
        else:
            candidates = self.get_candidates(task_type)

        # OS strict mode (default): local-only system. Cloud/browser
        # candidates are skipped even if keys exist. Opt out explicitly:
        # OSS_OS_STRICT=false (not recommended for the OS).
        if os.getenv("OSS_OS_STRICT", "true").strip().lower() in ("1", "true", "yes", "on"):
            candidates = [
                c
                for c in candidates
                if (m := self._model_map.get(c)) and m.provider in (ModelProvider.LOCAL, ModelProvider.OLLAMA)
            ] or ["oss_local"]

        # Try each candidate
        last_error = None
        for candidate_id in candidates:
            model = self._model_map.get(candidate_id)
            if not model:
                last_error = f"Unknown model: {candidate_id}"
                continue

            # Check availability
            available = await self.is_available(candidate_id)
            if not available:
                last_error = f"Model {candidate_id} not available"
                continue

            # Try to complete
            try:
                response = await self._call_model(candidate_id, task, req)
                elapsed = (time.monotonic() - started) * 1000

                # Log usage
                self._usage_log.append(
                    {
                        "model": candidate_id,
                        "task_type": task_type,
                        "latency_ms": round(elapsed, 2),
                        "timestamp": time.time(),
                    }
                )

                return {
                    "status": "completed",
                    "model": candidate_id,
                    "provider": model.provider.value,
                    "task_type": task_type,
                    "response": response,
                    "latency_ms": round(elapsed, 2),
                    "route": "api" if model.api_available else "browser",
                }
            except Exception as e:
                logger.exception("Unhandled exception in model_router.py")
                last_error = str(e)
                continue

        # Local fallback (independent engine first, Ollama second)
        local_result = await self._local_fallback(task, req)
        if local_result:
            elapsed = (time.monotonic() - started) * 1000
            return {
                "status": "completed",
                "model": "oss_local",
                "provider": "local",
                "task_type": task_type,
                "response": local_result,
                "latency_ms": round(elapsed, 2),
                "route": "local",
            }

        return {
            "status": "failed",
            "model": None,
            "error": last_error or "No available model could complete the task",
            "task_type": task_type,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }

    async def _call_model(self, model_id: str, task: str, requirements: dict[str, Any]) -> str:
        """Call a specific model and return its response (local providers only)."""
        model = self._model_map.get(model_id)
        if not model:
            raise ValueError(f"Unknown model: {model_id}")

        # Local engine models
        if model.api_available and model.provider == ModelProvider.LOCAL:
            return await self._call_api_model(model, task, requirements)

        raise ValueError(
            f"Model '{model_id}' is unavailable: OS v1 is local-only (cloud and browser providers were removed)."
        )

    async def _call_api_model(self, model: ModelInfo, task: str, requirements: dict[str, Any]) -> str:
        """Call a local model via the independent engine (no keys)."""
        import httpx

        if model.provider == ModelProvider.LOCAL:
            # oss-work independent engine: llama-server (OpenAI-compatible, no keys).
            base_url = os.getenv("OSS_LOCAL_URL", "http://127.0.0.1:11400").rstrip("/")
            timeout = float(os.getenv("OSS_LOCAL_TIMEOUT", "120"))
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": task}],
                        "max_tokens": requirements.get("max_tokens", 512),
                        "stream": False,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]

        raise ValueError(f"No API implementation for provider: {model.provider} (OS v1 is local-only).")

    async def _local_fallback(self, task: str, requirements: dict[str, Any]) -> str | None:
        """Try local inference as fallback (oss engine first, then Ollama)."""
        import httpx

        # 1) oss-work independent engine (llama-server, OpenAI-compatible)
        try:
            base_url = os.getenv("OSS_LOCAL_URL", "http://127.0.0.1:11400").rstrip("/")
            timeout = float(os.getenv("OSS_LOCAL_TIMEOUT", "120"))
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "messages": [{"role": "user", "content": task}],
                        "max_tokens": requirements.get("max_tokens", 512),
                        "stream": False,
                    },
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as _exc:
            logger.debug("oss local engine unavailable: %s", _exc)

        # 2) Ollama (optional, only if the user installed it separately)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "llama3",
                        "prompt": task,
                        "stream": False,
                    },
                )
                if r.status_code == 200:
                    data = r.json()
                    return data.get("response", "") or data.get("generation", "")
        except Exception as _exc:
            logger.exception("Suppressed exception in model_router.py")

        return None

    def get_usage_stats(self) -> dict[str, Any]:
        """Get usage statistics for the routing session."""
        if not self._usage_log:
            return {"total_requests": 0, "models_used": {}, "avg_latency_ms": 0}

        models = {}
        total_latency = 0
        for entry in self._usage_log:
            model = entry["model"]
            models[model] = models.get(model, 0) + 1
            total_latency += entry["latency_ms"]

        return {
            "total_requests": len(self._usage_log),
            "models_used": models,
            "avg_latency_ms": round(total_latency / len(self._usage_log), 2),
            "task_types": dict(Counter(e["task_type"] for e in self._usage_log)),
        }

    def clear_usage_log(self) -> None:
        """Clear the usage log."""
        self._usage_log.clear()


# ── Convenience ───────────────────────────────────────────────

_router: ModelRouter | None = None


def get_router(default_model: str = "gemini_flash") -> ModelRouter:
    """Get or create the singleton router."""
    global _router
    if _router is None:
        _router = ModelRouter(default_model=default_model)
    return _router


def reset_router() -> None:
    """Reset the singleton (for testing)."""
    global _router
    _router = None
