# OSS-Work Safe Release

OSS-Work is a **local-first multi-agent runtime foundation**. This release prioritizes explicit policy boundaries, deterministic behavior, bounded resources, auditability, and honest capability reporting over unsupported claims such as zero-cost access to proprietary models, limitless throughput, autonomous device control, or immunity from compromise.

> Security is a risk-reduction property, not an absolute promise. Production deployment still requires threat modeling, dependency review, operating-system hardening, secrets management, monitoring, backups, staged rollout, and independent security testing.

## What works in this release

The project provides a dependency-free Python core with a corrected agent lifecycle, typed task contracts, root-confined filesystem operations, bounded local memory, local static pattern checks, deterministic orchestration, simulation-only browser and integration boundaries, a review-only updater, and a responsive Next.js operator console adapted from the supplied dashboard and orchestration designs. Code execution, external messaging, login automation, runtime package installation, and hot updates are deliberately disabled.

| Capability | Release state | Boundary |
|---|---|---|
| Task decomposition | Enabled | Maximum five delegated agents per request |
| File listing, reading, and search | Enabled | Confined to `OSS_WORK_ALLOWED_ROOT` |
| File write/delete/move | Approval-gated | Root-confined; directory deletion is not supported |
| Code generation and review | Enabled | No execution in the host process |
| Browser automation | Simulation only | No login, navigation, scraping, or form submission |
| External integrations | Simulation only | No live credentials or outbound delivery |
| Security scanning | Local checks | Not a replacement for CodeQL, Snyk, ZAP, or a penetration test |
| Runtime updates and skill downloads | Disabled | Artifact inspection only; no install or extraction |
| Memory | Local SQLite | Parameterized queries and per-user namespace |
| Behavioral profiling | Disabled by default | Only request-scoped aggregate statistics are available |

## Quick start

Use Python 3.11 or newer. The safe core has no mandatory third-party runtime dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pytest
python -m core.main --version
python -m core.main "review this code for security"
```

Set `OSS_WORK_DATA_DIR` to choose the runtime data directory. Set `OSS_WORK_ALLOWED_ROOT` to constrain filesystem access. Never place provider tokens in source files, logs, `.env.example`, or release archives. Use a deployment secret manager for any future provider adapter.

## Approval model

A mutation is never implied by an agent capability. The caller must provide an explicit `approved` value in the request context, and the policy must also permit that class of action. External actions remain simulation-only even when approval is present until a separately reviewed provider adapter is commissioned.

Every decision object includes its classification, source signals, explanation, recommended human action, policy decision, and `external_action_attempted` flag. The latter must remain false for the safe release.

## Scaling notes

The included orchestrator is intentionally bounded and synchronous. It is suitable as a testable foundation, not a claim of infinite concurrency. A production service should add an authenticated API boundary, a shared queue, worker isolation, per-tenant quotas, validated telemetry ingestion, database pooling, backpressure, observability, disaster recovery, and load tests against a stated service-level objective. No finite implementation can guarantee that it will be unaffected by any number of users.

## Repository layout

| Path | Purpose |
|---|---|
| `core/contracts.py` | Typed task and decision objects |
| `core/policy.py` | Default-deny and simulation policy |
| `core/audit.py` | Structured audit events with sensitive-field filtering |
| `core/agents/` | Safe agent implementations |
| `scripts/updater.py` | Review-only artifact verifier |
| `tests/` | Focused safety and reliability tests |
| `docs/` | English and Arabic operating guidance |
| `web/` | Responsive Next.js operator console; static presentation until a reviewed API is connected |
| `core/services/telemetry.py` | Validated event envelope and bounded backpressure queue |
| `db/timescale/` | Staging-ready PostgreSQL/TimescaleDB telemetry and aggregate migration |
| `deploy/` | Loopback-only staging compose profile with file-based secret loading |

## License and commissioning

This foundation is released under Apache-2.0. Before enabling any live integration or code execution, obtain a provider-specific security review, define consent and revocation behavior, add signed payload verification and idempotency, isolate workers, and test rollback in staging. Those steps are intentionally not hidden behind a one-click installer.
