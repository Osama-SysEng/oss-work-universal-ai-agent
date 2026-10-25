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

### The context window

`osv1/context.py` implements the capacity rules of section 10: the window
scales with the device tier (Lite 128K, Standard 256K, Pro 1M), the token
count is an estimate with the method stated, and a request that does not fit
is summarized rather than dropped — by the local model when it is up, by an
extractive rule otherwise, with the source named in the result. Long answers
are written as chunks with checkpoints, so an interrupted run resumes.

### Provenance

`osv1/provenance.py` records the origin and the licence of every model,
dataset, tool, and dependency the system uses, and puts anything that is not
a permissive licence into the review queue before it is used (sections 20
and 23).

### The evaluation harness

`osv1/eval/harness.py` runs the per-layer suites separately, plants known
errors in real artifacts to measure the verification catch rate — with a
control case, so the number means something — and checks that the core still
plans with the language model unreachable.

### Program control

`osv1/tools/program_tools.py` starts only the programs the user allowed,
from the workspace, with a scrubbed environment and a time limit.

### The held-out suite, and a measured cascade

The specification's success test is that a non-expert gets a finished,
verified result. A suite the system wrote for tasks it knows cannot measure
that, so `osv1/eval/graded.py` is the suite that can: 58 graded tasks whose
answers the agents never see while they work.

The routing ground truth is written by hand from the domain definitions,
never from the router's own decisions — provenance no machine can verify,
so the suite says so instead of claiming a check that cannot exist. What it
can verify, it does: a task that is a bare keyword is refused rather than
scored, and a task whose expected domain claims none of its words is
reported as a finding about the vocabulary, and kept in the score rather
than hidden from it.

Four kinds of task, each saying what it can and cannot prove: 30 Arabic
routing goals, 15 arithmetic answers computed from the arithmetic itself, 8
questions nobody can know (graded for fabrication by an abstention-marker
proxy, which is labelled a proxy), and 5 code tasks whose delivered code is
executed in the sandbox against its own tests. Tasks that need the engine
are skipped with their reason when it is down, never scored as zero.

The dual-process cascade of section 27.6 is measured instead of assumed:
`SomEngine` and `LlmClient` report their times and their escalations to a
`CascadeRecorder`, which computes `q_abstain` (the `q` of
`E[T] = T1 + q·T2`), `q_llm`, both percentiles, and the expected time.
`oss-v1 cascade` and `GET /metrics/cascade` expose it; `oss-v1 graded` runs
the suite.

Measuring the engine tasks, then the suite itself, found four real defects,
and all four are fixed with the test that would have caught them:

- **a planned file write could never work.** The action engine passed only
  the step's `target` to every file tool, so `file.write` was called without
  its `content` argument and every write failed with
  `missing 1 required positional argument`. The content lives in the step's
  `detail` and was never passed. The system reported the failure honestly —
  *"no Python script was created"* — instead of inventing a success.
  `tests/test_safety_layer.py` now executes a planned write end to end.
- **a question was graded as an answer.** The decision engine asked the user
  about an arithmetic prompt, and its question quoted the right number among
  its options; the grader found that number in the question and scored a
  pass. Graders now check the status before looking for any number.
- **the engine timeout was a constant in the client.** On the Lite tier
  `t2_p95` sat at 120,029 ms — the old timeout, to the millisecond — and 15
  of 56 calls (27 %) were lost to it. The timeout now follows the device
  tier, and the `Settings.engine_timeout` that nothing had ever read is
  wired into the engine.
- **the audit log broke under ordinary use, and hid what it should have
  caught.** Three faults, found because the API tests went red against a
  chain that really was broken at entry 96: the log's path was a fixed
  relative one, so it ignored `OSS_V1_DATA_DIR` and left the audit trail
  behind in the working directory while the rest of the state moved;
  each writer took its `previous` hash from its own memory, so two writers
  appending at once produced entries whose `prev` matched nothing — the
  exact signature the chain exists to detect for tampering, produced by
  normal use; and a line that did not parse was skipped silently, so
  destroying the last entry of a log went unreported. The path now follows
  the data directory (an explicit override still wins), appends and reads
  take an exclusive lock and chain to the tail actually on disk, and an
  unreadable line is reported as damage. The tamper detection itself worked
  correctly the whole time — it found the real break.

### The thirteen qualities and their models

The specification of section 27 asks for each ambition to become a model
that can be computed, tested, and improved. `osv1/quality/` is that layer:
the register of the thirteen qualities with their laws, engineering rules,
and tests, and the formulas as functions. Every formula is checked against
the worked example the specification gives for it.

Three of the engineering rules became code rather than commentary:

- the verifier checks the arithmetic in an answer against values recomputed
  from the source, checks that stated probabilities sum to one, and labels
  the outcome *tested, not proven* outside the decidable fragments;
- the world model reports the negative log-likelihood and the KL divergence
  between what it predicted and what happened, with their sample counts;
- the memory cost of the full context window is computed per device tier,
  in 16-bit and in 4-bit.

`oss-v1 qualities --report` separates what is measured from what is still a
target, and never mixes the two.

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
