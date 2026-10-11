# Scaling — oss-work-universal-ai-agent (interfaces/api + core)

## Workers
- No Dockerfiles exist for the API (`deploy/` holds only compose for
  Timescale). `uvicorn.run()` in `interfaces/api/server.py::main` and
  `core/runtime.py` is single-process by design: this is a **desktop-local,
  single-user** agent. Documented as intentional in-memory exception —
  do NOT add `--workers 2` without also externalizing `TaskProcessor`
  state and the `RateLimiter`, which live in process memory.
- For shared/network deployments: run behind a process manager with
  `--workers 2` + a Redis-backed limiter and a persistent task queue.

## Rate limiting
- Already present: `core/rate_limit.py::RateLimiter` enforced in
  `interfaces/api/server.py::submit_task` (default 60 req/60s via
  `OSS_RATE_LIMIT` / `OSS_RATE_WINDOW`). No change needed.

## Pagination (default 50 / max 500)
- `GET /models` (both `interfaces/api/server.py` and `core/runtime.py`):
  new optional `limit/offset`, response adds `total/limit/offset`
  alongside `models`. Old clients reading only `models` unaffected.

## Remaining capacity limits (honest)
- `TaskProcessor` is in-process; concurrent `/task` calls share one event
  loop — long model calls block others. Needs a job queue for multi-user.
- Memory backends (`memory/redis.py` optional, else local) are per-process.
- 100+ model registry is static; `/models` pagination only bounds payload
  size, not compute.
