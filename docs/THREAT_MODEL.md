# Threat model and release boundary — OS_V1

## Security objective

OS_V1 protects the user's files and the user's machine from the agent's own
mistakes, and keeps the agent from acting on the user's behalf without a
decision. It does not claim to protect an unpatched operating system, a
compromised host, a malicious administrator, or a future adapter that has not
been reviewed.

The system has real access to the user's files, so this layer is mandatory
(specification section 19). It sits under every other component, and the
system itself may not change it.

## Trust boundaries

| Boundary | Default control | Required before production activation |
|---|---|---|
| User input → task contracts | length and type validation, a source tag, and a confidence value on every input | authenticated identity and tenant authorization |
| Agent → filesystem | canonical path confinement inside the granted roots | a dedicated operating-system account and per-tenant roots |
| Agent → code execution | sandbox with no network and no inherited secrets, time limit | an operating-system-level jail (container or VM), CPU and memory limits, egress control |
| Agent → programs | an explicit user allowlist, a confined working directory, a scrubbed environment | the dedicated account, and an audit of every program launched |
| Agent → external services | a read-only reader, and nothing else | OAuth and a token vault, consent, signature validation, idempotency, retries, a kill switch |
| Agent → the safety layer | refused by the promotion gate, and by the immutable-core list | an external review of the gate itself |
| Memory store | four separate types, per-user namespace, parameterized statements | encryption at rest, a retention policy, backup and restore tests |
| Audit log | a hash chain, so an edit is detected | an append-only remote sink with a reviewed retention |
| Sync archive | encrypted by the operating system (DPAPI) | user-held keys, an audited storage target, a tested restore |
| Provenance | every model, dataset, tool, and dependency recorded with its origin and licence | a legal review of everything in the review queue |

## Abuse cases the design rejects

- **Path traversal** — every path is resolved and checked against the granted
  roots; a request naming a file outside them is refused with the reason.
- **Destructive work without a decision** — deletion, sending, paying,
  publishing, and system changes wait for an explicit approval, and the
  approval is consumed once.
- **Prompt injection** — content from files, web pages, tools, and cloned
  repositories is data. It is tagged, scanned for instruction-like passages,
  and never enters the instruction channel. The action layer is what actually
  stops an instruction from becoming an action.
- **Dynamic host execution** — no `eval`, no `exec`, no shell built from
  user text. Generated code runs in the sandbox.
- **Unbounded fan-out** — the number of agents, the context window, the
  output size, and the file size all have explicit limits.
- **Secrets in the logs** — keys that commonly hold credentials are replaced
  before a line is written, in both the operational log and the audit log.
- **Silent memory corruption** — facts, experiences, skills, and assumptions
  are separate types, and a memory snapshot can be restored in one step.
- **Self-modification of the guardrails** — the safety layer, the
  permissions, the audit log, the kill switch, and the verifier's tests are
  refused by the promotion gate.
- **Verification that agrees with itself** — the verifier re-derives the
  facts from the artifacts, never from the reasoner's claims. The evaluation
  harness plants known errors and checks that they are caught, with a control
  case so that a verifier which rejects everything cannot pass.

## Residual risks

- The runtime is a local foundation, not a multi-tenant hosted service. It has
  no network API, no distributed queue, and no high-availability database, so
  it cannot substantiate claims of arbitrary-scale resilience.
- The sandbox blocks the network for Python children. A child that compiles
  native code, or runs another runtime, can get past it. The limit is
  documented in `SECURITY.md` rather than papered over.
- The local API has no authentication. It binds to `127.0.0.1`, and it must
  stay there.
- The model is a 3B quantized local model. Its output is not the output of a
  frontier model, and the interface says which model produced an answer.
- The prompt-injection check is a heuristic. It catches the common patterns;
  it is not a proof.
- The dedicated operating-system account is not created by the agent, and it
  does not exist yet. Until it does, the confinement is an application-level
  boundary, not an account boundary.
- Capacity is not established. The device tiers in the specification are
  planning targets; the numbers in `README.md` are measurements of what runs
  on one machine, not service-level objectives.
