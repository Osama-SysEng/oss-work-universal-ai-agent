# OSS Work / OS_V1 — Release Notes

## 1.0.0 — 21 October 2026

The first release built on the OS_V1 specification. The previous codebase was
replaced, not patched: the old modules are removed, and what remains is one
coherent system with a stated contract at every layer.

### What this release is

A local, independent AI agent that runs on the user's machine. One model
(OS_V1) with two modes:

- **Plan** — analyses, predicts, and proposes a plan. It executes nothing.
- **Build** — executes an approved plan, verifies every step, and delivers the
  result with its log.

### The six layers (spec section 8)

| Layer | Module | What it guarantees |
|---|---|---|
| Multimodal input | `osv1/layers/input_layer.py` | every input carries a source and a confidence; unreadable input is reported, never skipped |
| World model and memory | `osv1/layers/world_model.py` | every action is predicted before it runs and compared with what happened |
| Reasoning | `osv1/layers/reasoning.py` | hypotheses are tested with tools; a contradicted one is dropped |
| Decision | `osv1/layers/decision.py` | options are scored; the engine abstains or asks when the evidence is thin |
| Verifier | `osv1/layers/verifier.py` | independent checks over the artifacts, not over the reasoning |
| Action | `osv1/layers/action.py` | every action has a permission, a log entry, and a rollback path |

### System One and System Two

- System One (`osv1/som.py`) answers typed questions — choice, score, yes/no —
  with calibrated probabilities, a rationale trace, and an abstention
  threshold. The default backend is a transparent rule scorer; a Laya
  typed-decisions checkpoint is used when one is served locally.
- System Two (`osv1/engine/llm.py`) is the local llama.cpp server. It is used
  for planning and generation only, and every answer records whether a model
  or the rules produced it.

### The 300 specialized agents

30 domains times 10 specializations. Each agent has its own capabilities,
risk level, verification rules, plan template, and prompt. They are listed
by `oss-v1 agents`, by `/agents`, and by the live console.

### The safety layer

Permission scopes with explicit grants, human approval for irreversible
actions, a hash-chained audit log, an instant kill switch, prompt-injection
defence, and an encrypted secret store (DPAPI). The safety layer, the
permissions, the audit log, the kill switch, and the verifier's tests are off
limits to self-improvement work — the promotion gate refuses to touch them.

### The tool layer

Root-confined file tools, AST-based code analysis, a sandbox with no network
and no inherited secrets, a built-in spreadsheet engine that writes real
`.xlsx` files, a self-contained dashboard builder, a read-only reader, the
REA analysis adapter, and App Synthesis — which understands a file format and
builds the matching tool inside the system.

### The interface

A local API on the loopback interface, a command line, and a live console
whose animation is bound to the real event stream. The desktop shell (Tauri)
loads that console; it contains no model and fakes no result.

### Removed from the previous release

The old core package, the old agent suite, the keyword-scoring "imagination"
engine and its unmeasurable claims, the static Next.js console with its fixed
demo data, the 3D showcase page, the unused PostgreSQL, Redis, and Qdrant
clients, the conflicting SQL schemas, and the review-only updater. The
replacement is smaller, and everything left has a test behind it.
