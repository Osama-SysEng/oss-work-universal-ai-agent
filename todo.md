# OSS Work / OS_V1 — what is still open

This file lists the work that is **not** done. Nothing here is a claim; every
line is either a deliberate limit of this release or a piece of work that has
to happen before the system is used for anything that matters.

## Deliberate limits of this release

- The language model is a local 3B quantized model. Heavy reasoning is split
  into smaller steps or queued. The device tiers in the specification are
  planning targets, not measured results.
- System One ships as a transparent rule scorer with calibration tools. A
  Laya typed-decisions checkpoint is supported through an adapter, but no
  checkpoint is bundled and no fine-tuning has been run.
- The sandbox blocks the network for Python children. It is not an operating
  system jail.
- The personalisation session writes an encrypted preference artifact, not
  neural adapter weights. Training a real adapter needs a training stack
  that this repository does not bundle.
- The browser is a read-only reader: no JavaScript, no forms, no login, no
  screenshots.
- The local API has no authentication, because it binds to the loopback
  interface only.
- The REA adapter runs the built-in analyzer when the pinned REA engine is
  not installed locally, and says which engine produced each finding.

## Work that has to happen before production

- An authenticated, multi-tenant API with per-tenant quotas and a real
  session store.
- A distributed queue and worker isolation for the background sessions.
- Provider-specific OAuth, consent, signature, idempotency, retry, and
  kill-switch controls, for the optional external integrations.
- A separately commissioned code sandbox at the operating-system level.
- An independent penetration test and a red-team suite over the safety
  layer.
- A dependency and SBOM review, and a signed build.
- Load tests tied to a stated service-level objective.
- Backups with a tested restore.
- A staged rollout with a rollback.

## Measurement that is still missing

The five metrics exist and are reported per run — search breadth, decision
quality, calibration, verification catch rate, and time to solution. What is
missing is a held-out evaluation set and a long-context test at the full
window, so the numbers are currently per-run observations rather than
benchmarks. A release is described as meeting the targets only when the
benchmarks exist.
