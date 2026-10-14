# Models (OS v1 — local only)

> Superseded. As of oss-work OS v1, cloud and browser providers were removed.
> The system is local-only: no API keys, no external calls.

- Default engine: `oss_local` — llama-server (llama.cpp) + `qwen2.5-3b-q4_k_m`
  on `127.0.0.1:11400`. Start it with `C:\tools\llama\start-engine.cmd`.
- Optional: a user-installed Ollama on `127.0.0.1:11434` (second fallback).
- Strict routing: `OSS_OS_STRICT=true` (default) — automatic routing uses
  LOCAL providers only.

See `docs/OS.md` for the full OS contract.
