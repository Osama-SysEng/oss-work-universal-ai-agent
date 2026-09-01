# Threat Model and Release Boundary

## Security objective

The safe release protects the local data root and prevents the runtime from silently executing code, installing packages, contacting providers, or mutating files outside an explicitly configured root. It does not claim to protect an unpatched operating system, a compromised host, a malicious administrator, or a future live adapter that has not been reviewed.

## Trust boundaries

| Boundary | Default control | Required before production activation |
|---|---|---|
| User input to task contracts | Length and type validation | Authenticated identity and tenant authorization |
| Agent to filesystem | Canonical path confinement | OS account isolation and per-tenant roots |
| Agent to code execution | Denied | Separate sandbox, seccomp/container policy, CPU/memory limits, egress control |
| Agent to external provider | Simulation only | OAuth/token vault, consent, signature validation, idempotency, retries, kill switch |
| Artifact to updater | Hash inspection only | Signed provenance, SBOM, staged rollout, rollback, reproducible build |
| Memory database | Per-user namespace and parameterized SQL | Encryption at rest, retention policy, backup and restore tests |

## Abuse cases

The design specifically rejects path traversal, destructive operations without approval, dynamic host execution, runtime package installation, unverified archive extraction, unbounded fan-out, and logs containing secrets or raw content. A production review must add authentication, authorization, dependency and supply-chain checks, rate limits at the service edge, and adversarial testing.

## Residual risks

The current runtime is a local foundation rather than a multi-tenant hosted service. It has no network API, no distributed queue, no HA database, and no provider adapter. It therefore cannot substantiate claims of arbitrary-user-scale resilience. Capacity must be established through workload-specific load tests and a defined service-level objective.
