# oss-work OS (v1) — independent local system

English summary + Arabic notes. Code stays English; no secrets anywhere.

## What it is

A single local system. No API keys, no cloud calls, no Telegram, no Docker.
Default route for every task: the local engine
(`llama-server` + `qwen2.5-3b-q4_k_m` on `127.0.0.1:11400`).

- Boot: `python -m ossys.boot boot` (or installed `oss-os boot`)
- Engine starter: `C:\tools\llama\start-engine.cmd`
- Strict mode: `OSS_OS_STRICT=true` (default). Automatic routing uses LOCAL
  providers only. Explicit `--agent`/model choice is still respected.
  Opt out only deliberately: `OSS_OS_STRICT=false`.

## Layout (`ossys/`)

| File | Purpose |
|---|---|
| `config.py` | Version, strict flag, URLs, data/skills/workspace dirs |
| `kernel.py` | Boot, real dispatch to core agents + ossys services, background submit |
| `archetypes.py` | 30 task-agent archetypes (executor mapping) |
| `task_registry.py` | 300 task agents T001..T300 (data, not files) |
| `scheduler.py` | Persistent background jobs over SQLite |
| `store.py` | SQLite state: jobs, skills, runs |
| `skills.py` | Self-built skills from yes/no answers |
| `office/` | txt/md/csv native; docx only with python-docx; notes-to-HTML decks |
| `browser.py` | Read-only web reader (no JS/forms/screenshots — refused honestly) |
| `hosting.py` | Loopback static hosting without Docker |
| `boot.py` | `oss-os` CLI: boot/status/run/tasks/submit/jobs/drain/skill-new/serve |

## Honest limits (v1)

- 3B local model: light tasks + decisions. Heavy work is split or queued.
- Browser: no JavaScript, no login, no forms.
- Office: no native xlsx/pptx editing (CSV + HTML decks instead).
- Phase 2 (done): cloud/Telegram/JEV/skill-download code physically removed
  (9 files); integrations are loopback-only; DB `telegram_chat_id` columns
  kept for data compatibility only and are never used as provider identity.
