# Architecture

The release is organized as a small policy-driven core. `TaskRequest` and `TaskResult` define the boundary contract. `SafetyPolicy` evaluates capability classes. Each agent uses `BaseAgent` for lifecycle metrics and `AuditLogger` for structured events. The orchestrator performs deterministic, bounded delegation and never grants permissions to child agents.

The local filesystem agent resolves paths before access and confines them to `OSS_WORK_ALLOWED_ROOT`. The memory agent uses SQLite WAL mode with parameterized queries and a per-user namespace. The browser and integration agents return simulation results with `external_action_attempted=false`. The updater verifies an artifact hash but does not download, extract, install, or hot-reload code.

## Production scaling path

A hosted deployment should place an authenticated API gateway before the orchestrator, persist requests in a durable queue, and process work in isolated workers. Tenant quotas, concurrency limits, database pooling, circuit breakers, backpressure, structured metrics, distributed tracing, and tested backups are mandatory for a serious capacity claim. The present release intentionally stops before that operational boundary.
