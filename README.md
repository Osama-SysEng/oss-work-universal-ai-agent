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

OSS Work is a **zero-setup, zero-cost autonomous AI agent** that runs fully on your machine: a local inference engine (no API keys), 300 task agents over 30 archetypes, an office suite, a read-only web reader, loopback app hosting, and background work — reasoned through the **Ultra IQ Imagination Engine**.

A local user runs a task and OSS Work handles everything on this machine — reading, coding, file management, office documents, security scanning, and more. No paid API keys required. No complex setup.

### The Five Pillars

| Pillar | What it means |
|---|---|
| **Ultra IQ Imagination Engine** | A parallel reasoning engine — not an LLM wrapper, not retrieval — that explores many solution threads, synthesizes patterns across domains, simulates outcomes before any action, and records genuinely novel solutions. |
| **Local Engine, Zero Cost** | All reasoning runs on the independent local engine (llama-server + local GGUF model) with optional user-installed Ollama — no API keys, no cloud calls, no billing. |
| **Full Device Stack** | Browser automation (Playwright), root-confined file management, office suite, read-only web reader, loopback hosting, CLI, and a desktop app (Tauri). |
| **Continuous Learning** | ML pattern detection over session transcripts, invention trigger for genuinely novel solutions, and behavioral profiling that improves routing over time. |
| **Open Source** | Apache-2.0 licensed. 78 Python modules, 7 specialist agents + orchestrator + 300 OS task agents, bilingual docs (Arabic + English), CI/CD pipeline, and a local SQLite state store (Postgres/Timescale optional, never required). |

---

## Quick Start

```bash
# Clone
git clone https://github.com/Osama-SysEng/oss-work-universal-ai-agent.git
cd oss-work-universal-ai-agent

# Python 3.11+ required. No mandatory runtime deps for core.
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate

# Optional: install full deps (Playwright, httpx for local integrations)
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

# Start the OS (local only, no keys needed)
python -m ossys.boot boot

# Start CLI
python -m interfaces.cli.main "review this code for security issues"
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   USER INTERFACES                    │
│  Web Dashboard │ CLI │ Desktop App    │
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
│               LOCAL INTEGRATIONS                   │
│  Local engine │ Office suite │ Reader │ Hosting    │
│  GitHub │ Microsoft │ Any API                        │
└─────────────────────────────────────────────────────┘
```

---

## The Ultra IQ Imagination Engine

This is the core differentiator. OSS Work's imagination engine is a **genuine parallel reasoning system**, not an LLM call wrapper.

### What it does

- **Many concurrent reasoning threads** — explores every angle simultaneously (bounded by `max_threads`)
- **39 reasoning domains** — General, Code, Creative, Research, Arabic, Business, Ethics, Security, Systems, Health, Education, Future, Legal, Finance, Data, Marketing, Philosophy, Science, History, and more
- **Future simulation** — before any action, simulates near/medium/long-term horizons with probability estimates and risk registers
- **Genuine invention** — when novelty exceeds threshold, records solutions not seen before in local history
- **Cross-domain synthesis** — builds bridges between domains to find connections no single domain would see

### A tiny example

```python
from core.imagination.engine import UltraIQE

engine = UltraIQE()

result = engine.imagine(
    "How do I build a real-time collaborative editor like Google Docs?",
)
print(result.solution)  # Full technical proposal
print(result.confidence)  # 0.0–1.0 calibrated score
print(result.invented)  # True if genuinely new
print(result.cross_domain_bridges)  # E.g. ["OperationalTransform × CRDTs"]
print(result.simulation_branches)  # Future scenario analysis
```

The engine runs entirely offline. No API calls. No network. Just parallel reasoning.

---

## Local Model Routing

OSS Work routes every task locally **at zero API cost**:

- **Independent engine** — llama-server (llama.cpp) with a local quantized model on loopback. No API key needed, nothing leaves the machine.
- **Optional Ollama** — if the user installed Ollama separately, it serves as a second local fallback.

The `ModelRouter` classifies tasks by content (code, Arabic, creative, fast, etc.) and routes to the local engine with automatic failover. `OSS_OS_STRICT=true` (default) keeps automatic routing local-only.

---

## Multi-Agent System

OSS Work runs 7 specialist agents plus an orchestrator (keyword-based task decomposition):

| Agent | Purpose | Status |
|---|---|---|
| **Browser Agent** | Real Playwright automation for web tasks | ✅ Production |
| **Code Agent** | Write, execute, and review Python code in sandbox | ✅ Production |
| **File Agent** | Root-confined file listing, reading, writing | ✅ Production |
| **Security Agent** | Static analysis, secrets detection, file sanitization | ✅ Production + ML patterns |
| **Integration Agent** | Loopback webhooks/REST + local log (no cloud services) | ✅ Production |
| **Learning Agent** | ML pattern detection + invention trigger + profiling | ✅ Production |
| **Memory Agent** | SQLite recall + audit logging | ✅ Production |
| **Update Agent** | Delta patch application + rollback | ✅ Production |
| **Model Router** | Local-only routing (independent engine + optional Ollama) | ✅ Production |

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
│   │   ├── model_router.py   # local-only routing
│   │   ├── local_engine.py   # llama-server client (no keys)
│   │   └── updater.py
│   ├── contracts.py          # TaskRequest, TaskResult, DecisionRecord
│   ├── policy.py             # Safety policy system
│   ├── audit.py              # Structured audit logging
│   ├── knowledge.py          # Knowledge base
│   ├── workflow.py           # Task decomposition
│   ├── orchestrator.py       # Multi-agent orchestrator
│   ├── agent_registry.py     # Agent registry
│   └── advanced.py           # Security, evolution, telemetry
├── ossys/                    # oss-work OS v1 (local only, no keys)
│   ├── kernel.py             # boot + real dispatch + background
│   ├── task_registry.py      # 300 task agents (data, not files)
│   ├── archetypes.py         # 30 agent archetypes
│   ├── scheduler.py          # persistent background jobs
│   ├── skills.py             # self-built skills (yes/no)
│   ├── office/               # documents / sheets / decks
│   ├── browser.py            # read-only web reader
│   ├── hosting.py            # loopback hosting (no Docker)
│   └── boot.py               # oss-os CLI
├── interfaces/
│   ├── cli/
│   │   └── main.py           # Typer CLI (local only)
│   └── api/
│       └── server.py         # Desktop Local API
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
│   ├── test_ossys_kernel.py  # OS kernel + strict routing
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

- Local OS services (office suite, reader, hosting, skills)
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

## What's New (Oct 2026)
- Live PostgreSQL (10 tables; TimescaleDB hypertables need a Timescale server)
- ~110 tests collected, 0 errors
- Interactive 3D showcase: open `web-3d/index.html` (Three.js, animated, mouse-reactive)
