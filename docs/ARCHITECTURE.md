# Architecture — OSS Work / OS_V1

## The request path

```
user request
  → 8.1 Multimodal Input        tag every input with a source and a confidence
  → 8.2 World Model and Memory  describe the state, predict what an action changes
  → 8.3 Reasoning Engine        build hypotheses, test them with tools
  → 8.4 Decision Engine         score the options, abstain or ask when the evidence is thin
  → 8.5 Verifier                check the artifacts, not the reasoning
  → 8.6 Adaptive Action Engine  run the approved plan under the safety layer
  → delivered result + log
```

When the verifier fails, control returns to reasoning or to evidence
gathering. Asking the model to think again is not a verification.

## The two systems

| | System One (SOM) | System Two (LLM) |
|---|---|---|
| Job | fast typed decisions | planning, reasoning, generation |
| Questions | choice, score, yes/no | free text |
| Output | label, level, or calibrated probability, with a rationale | prose or structured JSON |
| Backend | rule scorer by default; a Laya checkpoint through an adapter | the local llama.cpp server |
| When | routing, verification, guardrails, action risk | only when the task needs generation |

The rule is simple: the SOM answers first, the LLM runs only when the task
needs generation or when the SOM abstains. Every answer records its source,
so a template is never passed off as a model response.

## The modules

| Path | Responsibility |
|---|---|
| `osv1/config.py` | device tiers, limits, paths, safety switches |
| `osv1/contracts.py` | the typed objects that cross every boundary |
| `osv1/som.py` | System One: typed decisions, abstention, calibration |
| `osv1/calibration.py` | ECE, Brier, temperature scaling |
| `osv1/engine/local_engine.py` | the llama.cpp client |
| `osv1/engine/llm.py` | System Two: plans, hypotheses, chunked generation |
| `osv1/layers/` | the six layers |
| `osv1/agents/` | 30 domains, 10 specializations, 300 agents, the runner |
| `osv1/tools/` | files, code, sandbox, spreadsheet, dashboard, reader, REA, synthesis |
| `osv1/memory/` | facts, experiences, skills, assumptions, versioning, rollback |
| `osv1/learning/` | self-evolution, practice sessions, weekly personalization, scheduler |
| `osv1/safety/` | permissions, approvals, audit, kill switch, injection, secrets |
| `osv1/eval/` | the five measurable metrics |
| `osv1/interface/` | the local API, the command line, the live console |
| `osv1/sync.py` | the optional encrypted archive for storage the user owns |

## The data that flows

```python
TaskResult
├── plan          → Plan(steps=[PlanStep(action, tool, target, approval, rollback)])
├── decision      → Decision(outcome=decide|abstain|ask_user, options, confidence)
├── verification  → Verification(passed, checks, uncertainty, reasons)
├── actions       → ActionRecord(action, tool, target, outcome, permission, rollback)
├── metrics       → the five metrics with their sample counts
└── errors        → what did not work, in plain words
```

## State on disk

Everything lives under `data-osv1/` (override with `OSS_V1_DATA_DIR`):

| File | Holds |
|---|---|
| `memory.db` | the four memory types, with versions |
| `audit.log` | the hash-chained action log |
| `permissions.json` | the live grants |
| `approvals.json` | pending and decided approvals |
| `kill.switch` | the kill switch, if it is engaged |
| `jobs.db` | the background job schedule |
| `evolution.json` | candidates and promoted versions |
| `secrets.enc` | the encrypted secret store |

## The two modes

- **Plan** — builds a plan and stops. The plan is a proposal the user can
  approve, change, or reject.
- **Build** — executes the approved plan, verifies each step, and delivers
  the result with its log. Build never starts without a plan, and a step
  whose permission is missing is blocked rather than forced.
