# Zero-Cost Models — Multi-Model Routing

OSS Work routes tasks to 100+ AI models at zero API cost by leveraging free tiers, local models, and browser-based simulation.

## Philosophy

The agent requires no paid API keys, no complex setup, and no technical knowledge to use. A non-technical user sends a message on Telegram and OSS Work handles everything without spending a dollar on inference.

## Model Categories

### American models (browser-based, zero cost)
- GPT-4o, GPT-4o Mini, ChatGPT Free — https://chat.openai.com
- Claude — https://claude.ai
- Gemini Pro, Gemini Flash — https://gemini.google.com
- Grok — https://x.com/i/grok
- Perplexity — https://perplexity.ai
- Microsoft Copilot — https://copilot.microsoft.com

### Chinese models (browser-based, zero cost)
- Kimi (Moonshot) — https://kimi.moonshot.cn
- Qwen (Alibaba) — https://tongyi.aliyun.com
- DeepSeek, DeepSeek Coder — https://deepseek.com
- Baidu ERNIE — https://qianfan.baidubce.com
- Zhipu GLM — https://open.bigmodel.cn

### Local models (self-hosted, zero marginal cost)
- Ollama Llama 3, Llama 3 70B, Mistral — http://localhost:11434
- LM Studio — local HTTP server
- GPT4All — local inference
- llama.cpp — C++ inference

### Open-source APIs (may have free tiers)
- HuggingFace Inference — https://huggingface.co
- Together AI — https://together.ai
- Groq (free tier) — https://groq.com
- OpenRouter (free credits) — https://openrouter.ai

## Routing

Tasks are routed to the best available model based on:

1. **Task classification** — keyword analysis maps tasks to categories (code, creative, arabic, chinese, search, fast, etc.)
2. **Routing table** — each category has an ordered list of candidate model IDs
3. **Availability check** — each candidate is tested for availability (API key present, Ollama running, Playwright available)
4. **Failover** — if a candidate fails, the next is tried
5. **Local fallback** — if all fail, the local Ollama/LM Studio fallback is attempted

## Browser-Based Simulation

For models without API keys, OSS Work uses Playwright to automate the browser:

1. Launch headless Chromium
2. Navigate to the model's web interface
3. Fill in the task prompt
4. Wait for the response
5. Extract the response text

This is **simulation-only** — no real request is sent. The browser automation is invoked only when the user explicitly opts into browser simulation mode.

## Usage

```python
from core.services.model_router import get_router

router = get_router()
result = await router.complete(
    "Write a Python function to compute Fibonacci numbers",
    requirements={"language": "Python", "detail_level": "comprehensive"},
)
print(result["response"])
print(result["model"])  # which model was used
print(result["route"])  # "api", "browser", or "local"
```

```python
# Programmatic model selection
result = await router.complete(
    "Translate to Arabic",
    model_id="gemini_pro",
)
```

## Zero-Cost Guarantee

- No model requires a paid API key for the default routing
- Browser simulation is free (uses the user's existing web session)
- Local models are free (run on the user's own hardware)
- Open-source APIs may charge for heavy usage — caveat emptor

## Configuration

Set environment variables for API keys when available:

```bash
export GROQ_API_KEY="gsk-..."
export HUGGINGFACE_API_KEY="hf_..."
export OPENROUTER_API_KEY="sk-or-..."
export DEEPSEEK_API_KEY="sk-..."
export OLLAMA_HOST="http://localhost:11434"
```

When no keys are set, the router automatically falls back to browser simulation or local models.

## Supported Task Types

| Task Type | Recommended Models |
|-----------|-------------------|
| Code generation | GPT-4o, DeepSeek Coder, Qwen, Ollama Llama 3 |
| Arabic content | Kimi, Qwen, Gemini Pro, ChatGPT Free |
| Chinese content | Kimi, Qwen, ERNIE, GLM |
| Fast response | Groq Llama, Gemini Flash, DeepSeek |
| Image analysis | GPT-4o, Gemini Pro, Claude |
| Reasoning | GPT-4o, DeepSeek, Qwen, Claude |
| Search/research | Perplexity, Gemini Pro, ChatGPT Free |
| Creative writing | Claude, GPT-4o, Kimi, Gemini Pro |
| Long-form writing | Claude, GPT-4o, Gemini Pro, Kimi |
| Translation | Gemini Pro, Qwen, Kimi, ChatGPT Free |

## Extending

Add new models to `core/services/model_router.py`:
1. Add a `ModelInfo` entry to the `MODELS` list
2. Add to the `ROUTING_TABLE` for relevant task types
3. Implement the API call in `_call_api_model` if it has an API
4. Add the browser URL if it has a web interface

No other file needs to change — the router discovers models dynamically from the registry.
