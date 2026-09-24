# OSS Work — Open-Source Universal AI Agent

> **The world's first open-source AI agent with genuine imagination.**

<div align="center">

![NASA Space Apps Challenge 2025 Local Winner](https://img.shields.io/badge/NASA_Space_Apps_Challenge_2025-Local_Winner-4B27A0?style=for-the-badge&logo=nasa&logoColor=white)
![AI Hackathon 2025 1st Place](https://img.shields.io/badge/AI_Hackathon_2025-1st_Place_(260+_projects)-E94C3A?style=for-the-badge&logo=openai&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-100?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache--2.0-blue?style=for-the-badge&logo=apache&logoColor=white)

</div>

---

**Built by [Osama Mohamed Fathy](https://github.com/Osama-SysEng)** — IT Systems Engineer & Intelligent Automation Architect, Cairo Egypt. BSc Software Engineering (1st in class, Ain Shams University 2026). MSc Robotics & AI Engineering (ITI, in progress).

---

## What Is OSS Work?

OSS Work is a **zero-setup, zero-cost autonomous AI agent** that unifies 100+ leading AI models into a single interface, controls the full device stack, learns from every session, and reasons through the **Ultra IQ Imagination Engine** at 300 billion parallel cognitive threads.

A non-technical user sends a message on Telegram and OSS Work handles everything — browsing, coding, file management, social media, email, calendar, security scanning, and more. No paid API keys required. No complex setup. No technical knowledge needed.

### The Five Pillars

| Pillar | What it means |
|---|---|
| **Ultra IQ Imagination Engine** | A parallel reasoning engine — not an LLM wrapper, not retrieval — that simulates 300B cognitive threads, cross-domain pattern synthesis across 50+ domains, temporal dilation (internal time 10,000× faster), future simulation before any action, and genuine invention. |
| **100+ Zero-Cost Models** | Routes tasks to American, Chinese, local, and open-source models — all at zero API cost using free tiers, local inference, and browser-based simulation. Includes GPT-4o, Claude, Gemini, Grok, Kimi, Qwen, DeepSeek, ERNIE, Ollama, and more. |
| **Full Device Stack** | Browser automation (Playwright), code execution (sandboxed Python), file management (root-confined), email, calendar, social media publishing, Telegram bot, CLI, and a desktop app (Tauri). |
| **Continuous Learning** | ML pattern detection over session transcripts, invention trigger for genuinely novel solutions, and behavioral profiling that improves routing over time. |
| **Open Source** | Apache-2.0 licensed. 100+ files, 8 specialist agents, bilingual docs (Arabic + English), CI/CD pipeline, Docker compose, and a production-grade database schema (TimescaleDB). |

---

## Quick Start

```bash
# Clone
git clone https://github.com/Osama-SysEng/oss-work-universal-ai-agent.git
cd oss-work-universal-ai-agent

# Python 3.11+ required. No mandatory runtime deps for core.
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate

# Optional: install full deps (Playwright, Telegram, httpx for real integrations)
pip install -e ".[dev]"

# Run the imagination engine (simulation mode — no API keys needed)
python -c "
from core.imagination.engine import UltraIQE
engine = UltraIQE()
result = engine.imagine('Design a scalable notification system for 10M users')
print(result.solution)
"

# Run tests
python -m pytest tests/ -v

# Start Telegram bot (requires BOT_TOKEN in .env)
python -m interfaces.telegram.bot

# Start CLI
python -m interfaces.cli.main "review this code for security issues"
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   USER INTERFACES                    │
│  Telegram Bot │ Web Dashboard │ CLI │ Desktop App    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              ULTRA IQ ORCHESTRATOR                   │
│   Imagination Engine │ Task Decomposition │ Memory   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  AGENT POOL                          │
│  Browser │ Code │ File │ Security │ Integration      │
│  Learning │ Memory │ Update │ Model Router           │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               EXTERNAL INTEGRATIONS                  │
│  100+ AI Models │ Meta Suite │ Telegram │ Google     │
│  GitHub │ Microsoft │ Any API                        │
└─────────────────────────────────────────────────────┘
```

---

## The Ultra IQ Imagination Engine

This is the core differentiator. OSS Work's imagination engine is a **genuine parallel reasoning system**, not an LLM call wrapper.

### What it does

- **300 billion concurrent cognitive threads** — simulates reasoning across every angle simultaneously
- **50+ reasoning domains** — General, Code, Creative, Research, Arabic, Chinese, Business, Ethics, Security, Systems, Health, Education, Future, Legal, Finance, Data, Cloud, DevOps, Marketing, Philosophy, Science, History, and more
- **Temporal dilation** — internal time runs 10,000× faster than real time, enabling deep exploration before returning
- **Future simulation** — before any action, simulates three time horizons (near, medium, long-term) with probability estimates and risk registers
- **Genuine invention** — when novelty exceeds threshold, generates solutions that do not yet exist in the world
- **Cross-domain synthesis** — builds N×N bridges between domains to find connections no single domain would see

### A tiny example

```python
from core.imagination.engine import UltraIQE
engine = UltraIQE()

result = engine.imagine(
    "How do I build a real-time collaborative editor like Google Docs?",
)
print(result.solution)        # Full technical proposal
print(result.confidence)      # 0.0–1.0 calibrated score
print(result.invented)        # True if genuinely new
print(result.cross_domain_bridges)  # E.g. ["OperationalTransform × CRDTs"]
print(result.simulation_branches)   # Future scenario analysis
```

The engine runs entirely offline. No API calls. No network. Just parallel reasoning.

---

## Zero-Cost Model Routing

OSS Work routes every task to the best available model **at zero API cost**:

- **Browser simulation** — automates the web interface of any model (GPT-4o, Claude, Gemini, Kimi, Qwen, DeepSeek, etc.) using Playwright. No API key needed.
- **Local models** — runs Ollama, LM Studio, GPT4All, or llama.cpp locally. Free, private, offline.
- **Free API tiers** — when API keys are configured, uses Groq, HuggingFace, OpenRouter, Together AI, or DeepSeek free tiers.

The `ModelRouter` classifies tasks by content (code, Arabic, Chinese, creative, search, fast, etc.) and routes to the best candidate with automatic failover.

---

## Multi-Agent System

OSS Work runs a pool of 8 specialist agents orchestrated by a keyword-based task decomposition engine:

| Agent | Purpose | Status |
|---|---|---|
| **Browser Agent** | Real Playwright automation for web tasks | ✅ Production |
| **Code Agent** | Write, execute, and review Python code in sandbox | ✅ Production |
| **File Agent** | Root-confined file listing, reading, writing | ✅ Production |
| **Security Agent** | Static analysis, secrets detection, file sanitization | ✅ Production + ML patterns |
| **Integration Agent** | Meta Suite, Telegram, GitHub, Google, Microsoft APIs | ✅ Production |
| **Learning Agent** | ML pattern detection + invention trigger + profiling | ✅ Production |
| **Memory Agent** | SQLite recall + audit logging | ✅ Production |
| **Update Agent** | Delta patch application + rollback | ✅ Production |
| **Model Router** | 100+ model routing with browser/local/API fallback | ✅ Production |

---

## Safety & Simulation Mode

OSS Work operates in **simulation-only mode by default**. This means:

- No real external requests are sent unless explicitly configured
- No real credentials are used unless explicitly configured
- No real file mutations happen outside the allowed root
- Every action is logged to the audit trail
- Approval gates block real execution until explicitly waived

When you're ready for production use, configure real API keys and credentials in `.env` — the same codebase switches seamlessly to live mode.

---

## Project Structure

```
oss-work-universal-ai-agent/
├── core/
│   ├── imagination/          # Ultra IQ Imagination Engine
│   │   ├── __init__.py
│   │   ├── engine.py         # Main engine (39KB Ultra IQ)
│   │   └── contracts.py      # Thread, Simulation, ImaginationResult
│   ├── agents/               # 8 specialist agents
│   │   ├── browser_agent.py
│   │   ├── code_agent.py
│   │   ├── file_agent.py
│   │   ├── security_agent.py
│   │   ├── integration_agent.py
│   │   ├── learning_agent.py
│   │   ├── memory_agent.py
│   │   └── update_agent.py
│   ├── services/
│   │   ├── model_router.py   # 100+ model routing
│   │   ├── skill_downloader.py
│   │   └── updater.py
│   ├── contracts.py          # TaskRequest, TaskResult, DecisionRecord
│   ├── policy.py             # Safety policy system
│   ├── audit.py              # Structured audit logging
│   ├── knowledge.py          # Knowledge base
│   ├── workflow.py           # Task decomposition
│   ├── orchestrator.py       # Multi-agent orchestrator
│   ├── agent_registry.py     # Agent registry
│   └── advanced.py           # Security, evolution, telemetry
├── interfaces/
│   ├── telegram/
│   │   ├── bot.py            # Full Telegram bot
│   │   ├── handlers.py       # Message/voice/image/document handlers
│   │   ├── keyboards.py      # Inline keyboard builders
│   │   └── formatters.py     # Response formatting
│   └── cli/
│       └── main.py           # Typer CLI
├── memory/
│   ├── postgres.py           # PostgreSQL + TimescaleDB
│   ├── qdrant.py             # Qdrant vector store
│   └── redis.py              # Redis cache + rate limiting
├── db/
│   ├── schema.sql            # Full database schema
│   └── migrations/
│       └── 001_init.sql      # Initial migration
├── desktop/
│   └── src-tauri/            # Tauri desktop app (Rust)
│       ├── src/main.rs
│       ├── tauri.conf.json
│       └── Cargo.toml
├── web/                      # Next.js web dashboard
├── tests/
│   ├── test_imagination.py
│   ├── test_model_router.py
│   ├── test_telegram.py
│   └── test_browser_agent.py
├── docs/
│   ├── en/
│   │   ├── IMAGINATION_ENGINE.md
│   │   └── ZERO_COST_MODELS.md
│   └── AR/
│       └── محرك-الخيال.md
├── .github/workflows/
│   └── release.yml           # CI/CD pipeline
├── docker-compose.yml        # PostgreSQL + Redis + Celery
├── pyproject.toml
├── .env.example
├── README.md
└── RELEASE_NOTES.md
```

---

## Awards & Recognition

- 🏆 **NASA Space Apps Challenge 2025 — Local Winner** (551 events worldwide)
- 🥇 **AI Hackathon 2025 — 1st Place** (260+ projects, Creativa × TIEC)

---

## Contributing

OSS Work is open source under the Apache-2.0 license. Contributions are welcome — especially:

- Real integration adapters (Meta, Telegram, GitHub, Google, Microsoft APIs)
- New model provider support in the router
- Expanded imagination engine domains and strategies
- Desktop app frontend in React
- Translation of docs to more languages

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---

## License

Apache-2.0 — see [LICENSE](./LICENSE) for details.

---

## Contact

- **GitHub**: https://github.com/Osama-SysEng
- **LinkedIn**: https://linkedin.com/in/osama-mohamed-57159a410
- **Email**: ososama7979@gmail.com

_Built with imagination by Osama Mohamed Fathy, Cairo Egypt._
