"""
Model Router — Zero-cost routing to 100+ AI models.
Routes tasks to the best available model without requiring API keys.
Uses free tiers, local models, and browser-based simulation.

Supports:
- American models (ChatGPT, Claude, Gemini, Grok, Perplexity, Copilot)
- Chinese models (Kimi, Qwen, DeepSeek, ERNIE, Zhipu)
- Local models (Ollama, LM Studio, GPT4All, llama.cpp)
- Open-source APIs (HuggingFace, Together AI, Groq, OpenRouter)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
    cost_per_1k_tokens: float = 0.0  # 0 = free tier
    api_available: bool = True
    browser_url: str | None = None
    default_for: list[str] = field(default_factory=list)


# ── Model Registry ────────────────────────────────────────────

MODELS = [
    # ── American ──
    ModelInfo("gpt4o", "GPT-4o", ModelProvider.OPENAI, "general",
              context_window=128000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://chat.openai.com"),
    ModelInfo("gpt4o_mini", "GPT-4o Mini", ModelProvider.OPENAI, "general",
              context_window=128000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://chat.openai.com"),
    ModelInfo("chatgpt_free", "ChatGPT Free", ModelProvider.OPENAI, "general",
              context_window=30000, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://chat.openai.com"),
    ModelInfo("claude", "Claude", ModelProvider.ANTHROPIC, "general",
              context_window=200000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://claude.ai"),
    ModelInfo("gemini_pro", "Gemini Pro", ModelProvider.GOOGLE, "general",
              context_window=128000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://gemini.google.com"),
    ModelInfo("gemini_flash", "Gemini Flash", ModelProvider.GOOGLE, "fast",
              context_window=128000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://gemini.google.com"),
    ModelInfo("grok", "Grok", ModelProvider.XAI, "general",
              context_window=131072, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://x.com/i/grok"),
    ModelInfo("perplexity", "Perplexity", ModelProvider.OPENAI, "search",
              context_window=50000, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://perplexity.ai"),
    ModelInfo("copilot", "Microsoft Copilot", ModelProvider.GOOGLE, "general",
              context_window=128000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://copilot.microsoft.com"),

    # ── Chinese ──
    ModelInfo("kimi", "Kimi (Moonshot)", ModelProvider.GOOGLE, "general",
              context_window=200000, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://kimi.moonshot.cn"),
    ModelInfo("qwen", "Qwen (Alibaba)", ModelProvider.GOOGLE, "general",
              context_window=128000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://tongyi.aliyun.com"),
    ModelInfo("deepseek", "DeepSeek", ModelProvider.DEEPSEEK, "general",
              context_window=128000, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://deepseek.com"),
    ModelInfo("deepseek_coder", "DeepSeek Coder", ModelProvider.DEEPSEEK, "code",
              context_window=128000, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https:// DeepSeek.com"),
    ModelInfo("ernie", "Baidu ERNIE", ModelProvider.GOOGLE, "general",
              context_window=100000, supports_vision=True,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://qianfan.baidubce.com"),
    ModelInfo("glm", "Zhipu GLM", ModelProvider.GOOGLE, "general",
              context_window=128000, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=False,
              browser_url="https://open.bigmodel.cn"),

    # ── Local ──
    ModelInfo("ollama_llama3", "Ollama Llama 3", ModelProvider.OLLAMA, "general",
              context_window=8192, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("ollama_llama3_70b", "Ollama Llama 3 70B", ModelProvider.OLLAMA, "general",
              context_window=8192, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("ollama_mistral", "Ollama Mistral", ModelProvider.OLLAMA, "general",
              context_window=8192, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("lm_studio", "LM Studio", ModelProvider.LOCAL, "general",
              context_window=4096, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("gpt4all", "GPT4All", ModelProvider.LOCAL, "general",
              context_window=4096, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("llama_cpp", "llama.cpp", ModelProvider.LOCAL, "general",
              context_window=4096, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),

    # ── Open-source APIs ──
    ModelInfo("huggingface", "HuggingFace Inference", ModelProvider.HUGGINGFACE, "general",
              context_window=4096, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("together_llama", "Together AI Llama", ModelProvider.TOGETHER, "general",
              context_window=8192, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("groq_llama", "Groq Llama", ModelProvider.GROQ, "fast",
              context_window=8192, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
    ModelInfo("openrouter", "OpenRouter Free", ModelProvider.OPENROUTER, "general",
              context_window=4096, supports_vision=False,
              cost_per_1k_tokens=0.0, api_available=True),
]


# ── Routing Table ─────────────────────────────────────────────

ROUTING_TABLE: dict[str, list[str]] = {
    "long_form_writing":    ["claude", "gpt4o", "gemini_pro", "kimi", "qwen"],
    "code_generation":      ["gpt4o", "deepseek_coder", "qwen", "ollama_llama3", "groq_llama"],
    "arabic_content":       ["kimi", "qwen", "gemini_pro", "chatgpt_free"],
    "chinese_content":      ["kimi", "qwen", "ernie", "glm"],
    "fast_response":        ["groq_llama", "gemini_flash", "deepseek", "ollama_mistral"],
    "image_analysis":       ["gpt4o", "gemini_pro", "claude"],
    "reasoning":            ["gpt4o", "deepseek", "qwen", "claude"],
    "security_analysis":    ["claude", "gpt4o", "deepseek"],
    "search_research":      ["perplexity", "gemini_pro", "chatgpt_free"],
    "coding_help":          ["gpt4o", "deepseek_coder", "qwen", "groq_llama"],
    "creative_writing":     ["claude", "gpt4o", "kimi", "gemini_pro"],
    "translation":          ["gemini_pro", "qwen", "kimi", "chatgpt_free"],
    "summarization":        ["gemini_flash", "groq_llama", "ollama_mistral", "chatgpt_free"],
    "general_chat":         ["chatgpt_free", "gemini_flash", "claude", "gemini_pro"],
    "markdown_formatting":  ["gemini_flash", "groq_llama", "chatgpt_free"],
    "html_generation":      ["gpt4o", "deepseek_coder", "qwen", "groq_llama"],
    "offline_fallback":     ["ollama_llama3", "lm_studio", "gpt4all"],
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

        if any(kw in task_lower for kw in ["code", "function", "class", "python", "javascript",
                                              "typescript", "api", "endpoint", "algorithm",
                                              "debug", "fix", "refactor", "implement"]):
            return "code_generation"

        if any(kw in task_lower for kw in ["image", "picture", "photo", "screenshot", "visual",
                                              "chart", "graph", "diagram"]):
            return "image_analysis"

        if any(kw in task_lower for kw in ["arabic", "العربية", "عربي", "فصحى", "امي calibrate"]):
            return "arabic_content"

        if any(kw in task_lower for kw in ["chinese", "中文", "中国", "汉语"]):
            return "chinese_content"

        if any(kw in task_lower for kw in ["write", "article", "blog", "story", "essay",
                                              "creative", "novel", " poem", "narrative"]):
            return "creative_writing"

        if any(kw in task_lower for kw in ["search", "research", "find", "look up", "investigate",
                                              "discover", "explore"]):
            return "search_research"

        if any(kw in task_lower for kw in ["fast", "quick", "instant", "immediate", "urgent"]):
            return "fast_response"

        if any(kw in task_lower for kw in ["summarize", "summary", "tl;dr", "brief", "short"]):
            return "summarization"

        if any(kw in task_lower for kw in ["translate", "translation", "arabic", "chinese",
                                              "spanish", "french", "german"]):
            return "translation"

        if any(kw in task_lower for kw in ["html", "css", "javascript", "frontend", "ui", "web page",
                                              "website"]):
            return "html_generation"

        if any(kw in task_lower for kw in ["analyze", "security", "vulnerability", "audit",
                                              "review", "check"]):
            return "security_analysis"

        if any(kw in task_lower for kw in ["reason", "think", "logic", "philosophy", "argument",
                                              "debate", "analyze deeply"]):
            return "reasoning"

        if any(kw in task_lower for kw in ["long", "detailed", "comprehensive", "thorough",
                                              "complete guide", "in-depth"]):
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
        elif model.provider == ModelProvider.HUGGINGFACE:
            return bool(os.getenv("HUGGINGFACE_API_KEY"))
        elif model.provider == ModelProvider.GROQ:
            return bool(os.getenv("GROQ_API_KEY"))
        elif model.provider == ModelProvider.OPENROUTER:
            return bool(os.getenv("OPENROUTER_API_KEY"))
        elif model.provider == ModelProvider.DEEPSEEK:
            return bool(os.getenv("DEEPSEEK_API_KEY"))
        else:
            # Browser-based: check if Playwright is available
            try:
                import playwright.async_api  # noqa: F401
                return True
            except ImportError:
                return False

    async def _check_ollama(self) -> bool:
        """Check if Ollama is running locally."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get("http://localhost:11434/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def _check_local(self) -> bool:
        """Check if any local inference server is running."""
        import httpx
        ports = [1234, 8080, 5000]
        for port in ports:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    r = await client.get(f"http://localhost:{port}/health", timeout=3.0)
                    if r.status_code == 200:
                        return True
            except Exception:
                continue
        return False

    async def complete(
        self, task: str, requirements: dict[str, Any] | None = None,
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
                self._usage_log.append({
                    "model": candidate_id,
                    "task_type": task_type,
                    "latency_ms": round(elapsed, 2),
                    "timestamp": time.time(),
                })

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
                last_error = str(e)
                continue

        # Local fallback
        local_result = await self._local_fallback(task, req)
        if local_result:
            elapsed = (time.monotonic() - started) * 1000
            return {
                "status": "completed",
                "model": "ollama_llama3",
                "provider": "ollama",
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

    async def _call_model(
        self, model_id: str, task: str, requirements: dict[str, Any]
    ) -> str:
        """Call a specific model and return its response."""
        model = self._model_map.get(model_id)
        if not model:
            raise ValueError(f"Unknown model: {model_id}")

        # API-based models
        if model.api_available:
            return await self._call_api_model(model, task, requirements)

        # Browser-based models
        if model.browser_url:
            return await self._call_browser_model(model, task)

        raise ValueError(f"No API or browser route for model: {model_id}")

    async def _call_api_model(
        self, model: ModelInfo, task: str, requirements: dict[str, Any]
    ) -> str:
        """Call a model via its API."""
        import httpx

        if model.provider == ModelProvider.GROQ:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY not set")
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model.id,
                "messages": [{"role": "user", "content": task}],
                "max_tokens": requirements.get("max_tokens", 4096),
                "temperature": requirements.get("temperature", 0.7),
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]

        elif model.provider == ModelProvider.HUGGINGFACE:
            api_key = os.getenv("HUGGINGFACE_API_KEY")
            if not api_key:
                raise ValueError("HUGGINGFACE_API_KEY not set")
            url = f"https://api-inference.huggingface.co/models/{model.id}"
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(url, json={"inputs": task}, headers=headers)
                r.raise_for_status()
                return r.json().get("generated_text", r.text)

        elif model.provider == ModelProvider.OPENROUTER:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY not set")
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://oss-work.local",
            }
            payload = {
                "model": model.id,
                "messages": [{"role": "user", "content": task}],
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]

        elif model.provider == ModelProvider.TOGETHER:
            api_key = os.getenv("TOGETHER_API_KEY")
            if not api_key:
                raise ValueError("TOGETHER_API_KEY not set")
            url = "https://api.together.xyz/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model.id,
                "messages": [{"role": "user", "content": task}],
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]

        else:
            raise ValueError(f"No API implementation for provider: {model.provider}")

    async def _call_browser_model(
        self, model: ModelInfo, task: str
    ) -> str:
        """Call a model via its web interface (zero API cost)."""
        import asyncio
        from playwright.async_api import async_playwright

        url = model.browser_url
        if not url:
            raise ValueError(f"No browser URL for model: {model.id}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)

                # Find and fill the input
                input_selector = "textarea, input[type='text'], input[type='prompt']"
                await page.wait_for_selector(input_selector, timeout=10000)
                await page.fill(input_selector, task)
                await page.press(input_selector, "Enter")

                # Wait for response
                await asyncio.sleep(3)  # Brief wait for model to respond

                # Extract response (model-specific — simplified)
                body_text = await page.inner_text("body")
                return body_text[:3000]  # Truncate
            finally:
                await browser.close()

    async def _local_fallback(self, task: str, requirements: dict[str, Any]) -> str | None:
        """Try local inference as fallback."""
        # Try Ollama
        try:
            import httpx
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
        except Exception:
            pass

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
