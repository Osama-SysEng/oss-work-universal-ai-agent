# OSS Work / OS_V1

> A local, independent AI agent that plans, decides, verifies, and then acts — on your own machine, with no provider, no API key, and no internet in the core path.

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-100?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache--2.0-blue?style=for-the-badge&logo=apache&logoColor=white)
![Offline](https://img.shields.io/badge/runtime-offline%20first-3fb950?style=for-the-badge)
![Agents](https://img.shields.io/badge/agents-300-4f9dff?style=for-the-badge)

</div>

**Built by [Osama Mohamed Fathy](https://github.com/Osama-SysEng)** — IT Systems Engineer & Intelligent Automation Architect, Cairo, Egypt. BSc Software Engineering (Ain Shams University), MSc Robotics & AI Engineering (ITI, in progress).

---

## What OS_V1 is

One model, presented to you as a single thing, with two modes:

- **Plan** — analyses, predicts, and proposes a plan. It executes nothing. You approve, change, or reject it.
- **Build** — executes the approved plan, verifies every step, and delivers the result with its log.

The central idea is to replace *a language model that writes a convincing answer* with *a system that thinks, predicts, decides, verifies, and then acts*. Every important output passes an independent verification step before it reaches you.

This release is built from the OS_V1 specification. The old codebase was replaced, not patched — see [RELEASE_NOTES.md](RELEASE_NOTES.md).

## The five pillars

| Pillar | What it means here |
|---|---|
| **Two systems, one model** | System One answers fast typed questions (routing, verification, risk) with calibrated probabilities; System Two (the local llama.cpp server) plans and generates. You never pick a model. |
| **Independent verification** | The verifier re-derives the facts from the artifacts — the files written, the rows counted, the tools run — and never asks the reasoner whether it did well. |
| **300 specialized agents** | 30 domains × 10 specializations. Each agent has its own tools, risk level, verification rules, and plan template. |
| **Its own tools** | A spreadsheet engine that writes real `.xlsx` files, a dashboard builder, AST code analysis, a no-network sandbox, a read-only reader, and an app-synthesis engine that builds a tool after understanding a file format. |
| **A safety layer that cannot be edited by the system** | Permission scopes, human approval for irreversible actions, a tamper-evident audit log, an instant kill switch, prompt-injection defence, and an encrypted secret store. |

## Quick start

```bash
git clone https://github.com/Osama-SysEng/oss-work-universal-ai-agent.git
cd oss-work-universal-ai-agent

python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m pytest tests/ -q       # the whole suite runs offline, with no keys
python -m osv1.interface.cli status
python -m osv1.interface.api     # the live console on http://127.0.0.1:8080
```

The language model is optional. Without it the system still plans, verifies, and works with the tools; with it the answers get better.

```bash
# Windows: start the local engine first
C:\tools\llama\start-engine.cmd  # llama-server on 127.0.0.1:11400
```

```bash
# then plan and build
python -m osv1.interface.cli plan "review core/policy.py for security issues"
python -m osv1.interface.cli build "review core/policy.py for security issues"
```

## What the numbers in this repository are

Every number below was counted from the code, and `tests/test_release_assets.py`
fails the build if the README drifts away from the code.

| Claim | Value | How it is counted |
|---|---|---|
| Specialized agents | **300** | 30 domains × 10 specializations, asserted in the registry |
| Python modules | **61** | `osv1/**/*.py` |
| Lines of implementation | **~12,900** | the same modules |
| Tools the agent layer can run | **20** | the tool registry at runtime |
| Local API endpoints | **27** | the `@app` decorators in `osv1/interface/api.py` |
| Tests | **231** | `python -m pytest tests/ -q` — offline, no keys, no engine |

Nothing here is a benchmark claim against another system. The five metrics of
the specification are implemented and reported per run, and the evaluation
harness measures what it can measure today — with the sample count next to
every number:

```bash
oss-v1 evaluate
# suites: 13/13 passed
# verification_catch_rate: 1.0  (5 seeded errors, all caught; the control case passes)
# independence: true  (the core plans with the model unreachable)
```

A held-out evaluation set and a long-context benchmark do not exist yet; that
is listed in [todo.md](todo.md), not implied to be done.

## Architecture

```
user request
  → 8.1 Multimodal Input        every input carries a source and a confidence
  → 8.2 World Model and Memory  every action is predicted before it runs
  → 8.3 Reasoning Engine        hypotheses are tested with tools
  → 8.4 Decision Engine         options are scored; abstain or ask when thin
  → 8.5 Verifier                independent checks over the artifacts
  → 8.6 Adaptive Action Engine  run the plan under the safety layer
  → delivered result + log
```

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
العربية: [docs/AR/دليل-المشروع.md](docs/AR/دليل-المشروع.md)

### System One and System Two

System One turns a state plus a typed question into a structured, calibrated
decision in one pass: a label with probabilities, a level on an ordinal scale,
or a calibrated yes/no, always with a rationale trace. It abstains when it is
not confident, and the request then asks you instead of guessing.

The default backend is a transparent rule scorer — fast, offline, inspectable,
and labelled as a heuristic wherever it is used. A Laya typed-decisions
checkpoint is supported through an adapter (`OSS_V1_LAYA_MODEL`); no weights
are bundled, and the system says so when none is served.

System Two is the local engine. It is used for planning and generation only.
Every answer records whether a model or the rules produced it, so a template
is never passed off as a model response.

### The 300 agents

```bash
oss-v1 agents --domain security-engineering
oss-v1 agent A153
oss-v1 plan "optimize the slow query in api.py" --agent A065
```

Each agent is a capability profile, not a persona: what it may use, what it
must produce, and what has to be true before its answer is delivered.
[docs/AGENTS.md](docs/AGENTS.md) has the full table.

**Arabic requests work.** Every domain and specialization carries the Arabic
words people actually use, written as short stems so the inflected forms
match — `راجع` and `مراجعة` both reach the review agents, `ثغرة` and `ثغرات`
both reach the security domain, and both spellings of a hamza are listed.

## The context window

The window scales with the device tier: Lite 128K, Standard 256K, Pro 1M
(§23). A request that does not fit is **summarized, not dropped** — the
overflow is listed with what replaced it, and the summary comes from the
local model when it is up and from a rule-based extract otherwise, which the
result says out loud.

```bash
oss-v1 context --file report.md     # how a text fits in this machine's window
```

Long answers are produced as chunks with checkpoints, so an interrupted run
resumes instead of starting over.

## Provenance

Every model, dataset, tool, and dependency is recorded with its origin and
its licence, and anything that is not a permissive licence is put in the
review queue before it is used (§20, §23).

```bash
oss-v1 provenance
oss-v1 provenance --add model "my model" "C:/models/mine.gguf" "unknown"
```

## Evaluation

```bash
oss-v1 evaluate
```

The harness runs the per-layer suites separately, plants known errors in real
artifacts to measure the verification catch rate, and checks that the core
still works with the language model unreachable. The report lands in
`data-osv1/evaluation.json`.

## The thirteen qualities

The specification names thirteen qualities and gives each one a law, a
formula, an engineering rule, and a test. They are not adjectives here:
every formula is code in `osv1/quality/models.py`, every rule is enforced
where it belongs, and every formula is checked against the worked example
the specification gives for it.

| # | Quality | Law | Where it lives |
|---|---|---|---|
| 1 | Speed | Roofline and Amdahl | `quality.models:prefill_time, amdahl_speedup` |
| 2 | Intelligence | No Free Lunch, best-of-n | `quality.models:best_of_n_success, confidence_interval` |
| 3 | Power | Reliability compounding | `quality.models:job_reliability, step_reliability_with_retry` |
| 4 | Faster learning | PAC bound, power law of practice | `quality.models:fit_learning_curve` |
| 5 | Imagination | World model, simulation lemma | `quality.models:negative_log_likelihood, kl_divergence` |
| 6 | Human-mind simulation (Ultra IQ) | Dual-process cascade | `quality.models:cascade_time, chow_threshold` |
| 7 | Absolute safety | Rule of three | `quality.models:rule_of_three` + the immutable core |
| 8 | Best reverse engineering | Data-processing inequality | `quality.models:behavioral_parity, mismatch_bound` |
| 9 | Independence | Series availability | `quality.models:series_availability` + the offline suite |
| 10 | The SOM | Decision theory, proper scoring | `quality.models:softmax, combine_logits, value_of_information` |
| 11 | Mathematical logic | Floating-point error, units | `quality.models:relative_error` + `verifier.check_math` |
| 12 | Scientific grounding | Bayesian evidence | `quality.models:posterior_odds, sample_size_for_margin` |
| 13 | Absolute knowledge | Entropy, KV-cache physics | `quality.models:knowledge_gap, kv_cache_bytes` |

```bash
oss-v1 qualities           # the register
oss-v1 qualities --report  # what is measured today, and what is still a target
```

Three of the rules are code, not commentary: the verifier checks the
arithmetic in an answer and labels the result *tested, not proven* outside
the decidable fragments; the world model reports the negative log-likelihood
and KL divergence between what it predicted and what happened; and the
memory cost of the full window is computed per device tier instead of
guessed.

The full table, the three foundations that stay fixed, and the limits that
physics does not allow breaking are in [docs/QUALITIES.md](docs/QUALITIES.md).

## The safety layer

| Control | Behaviour |
|---|---|
| Permission scopes | files, network, programs, and irreversible actions are granted explicitly and can be revoked |
| Human approval | deleting, sending, paying, publishing, and system changes wait for your decision |
| Program control | only programs on the user's allowlist start, from the workspace, with a scrubbed environment |
| Audit log | every action is chained by hash, so an edited or removed line is detected |
| Kill switch | one file stops every action, the scheduler, and the background work |
| Injection defence | content from files, pages, and tools is data, never an instruction |
| Secrets | encrypted by the operating system (DPAPI); never written in plain text |
| Immutable core | self-improvement may not touch the safety layer, the permissions, the audit log, the kill switch, or the verifier's tests |

Known limits are written down in [SECURITY.md](SECURITY.md): the sandbox
blocks the network for Python children but is not an operating-system jail,
and the local API has no authentication because it binds to the loopback
interface only.

## Memory

Four types that never blur into each other: **facts** (verified), **experiences**
(what was tried and what happened), **skills** (reusable procedures with their
conditions and tests), and **assumptions** (tagged as assumptions, revocable,
never treated as facts). Everything is local, versioned, and under your
control: read it, correct it, delete it, export it, roll it back.

## Self-evolution, practice, personalization

- **Self-evolution** — log, learn, ask, test against a frozen suite, promote.
  A candidate that regresses anything is rejected; every version is kept with
  a one-step rollback.
- **Practice sessions** — build the same project twice, once from the README
  only and once from the analysis of its artifact, then compare the results.
  Cloned code runs in the sandbox with no network, the original's code is never
  copied, and weight training only uses permissive licences.
- **Weekly personalization** — studies how you work, scores itself against the
  choices you actually made, and writes an encrypted artifact on your machine.
  The artifact is a preference profile, **not** neural adapter weights; a real
  adapter needs a training stack this repository does not bundle.

## The interface

`python -m osv1.interface.api` serves the live console on `127.0.0.1:8080`.
The animation is bound to the real event stream: the layer lights up because
something happened, and the stop button stops the run. The plan, the
confidence, the verification checks, the permissions in use, and the action
log are always on screen.

The desktop shell under `desktop/` is a thin Tauri window that loads that
console. It contains no model and fakes no result; building it needs Rust,
which is not installed in this environment.

## Independence

| Layer | Rule | How it is kept |
|---|---|---|
| Compute | runs offline | the core path never opens a socket |
| Models | the local engine only | no provider client exists in the code |
| Keys | none | there is no key in the code, the README, or the template |
| Tools | its own | spreadsheet, dashboard, analysis, sandbox, reader, synthesis |
| Memory | local | SQLite on your machine, with an optional encrypted archive |
| Interface | its own | the local console and the command line |

## Honest limits

- The local model is a 3B quantized model. It is good at light tasks and
  decisions; heavy work is split or queued.
- The browser is a read-only reader: no JavaScript, no forms, no login, no
  screenshots.
- The sandbox blocks the network for Python children. Native code can get past
  that; use a container for a real jail.
- The personalization artifact is a preference profile, not a trained adapter.
- The local API has no authentication. Keep it on the loopback interface.
- There is no held-out benchmark set yet, so the metrics are per-run
  observations rather than results to compare against other systems.

The full list of what is still open is in [todo.md](todo.md).

## Roadmap

The specification's phases, with the acceptance criteria that close each one:

| Phase | Deliverable | Acceptance |
|---|---|---|
| 0 Foundation | base model chosen, local runtime, contracts, evaluation harness | harness runs, contracts reviewed, licences cleared |
| 1 Core | reasoning, verifier, decision, plus the SOM head | calibration and latency targets met on the SOM sets |
| 2 Agent | dedicated user, file access, browser control, safety layer | red-team passes, kill switch and logs verified |
| 3 Memory | four memory types, skill learning, calibration loop, weekly session | a skill learned in one session is reused in another |
| 4 REA | embedded REA, generated tools, practice sessions | generated files open cleanly, practice metrics tracked |
| 5 Interface | the app and the synchronized animation | the user can always see what, why, and how to stop |
| 6 World model | world model and OS_V1 training | prediction accuracy and unified-model benchmarks met |
| 7 Release | integration, full suite, package | every earlier acceptance criterion passes together |

**This release covers the foundation and the core of phases 0 to 3, with the
tool layer, the safety layer, and the interface in place.** The numbers in the
table are targets; the work that remains is in `todo.md`.

## Repository layout

```
osv1/
├── config.py            device tiers, limits, paths, safety switches
├── contracts.py         the typed objects that cross every boundary
├── som.py               System One: typed decisions and abstention
├── calibration.py       ECE, Brier, temperature scaling
├── context.py           the context window, overflow summarization, checkpoints
├── provenance.py        the origin and licence of everything that is used
├── engine/              the local engine client and System Two
├── layers/              the six layers of the specification
├── agents/              30 domains, 10 specializations, 300 agents, the runner
├── tools/               files, code, sandbox, spreadsheet, dashboard, reader, REA, synthesis, programs
├── memory/              facts, experiences, skills, assumptions, versioning
├── learning/            self-evolution, practice, personalization, scheduler
├── safety/              permissions, approvals, audit, kill switch, injection, secrets
├── eval/                the five measurable metrics and the evaluation harness
├── interface/           the local API, the command line, the live console
└── sync.py              the optional encrypted archive
docs/                    architecture, agents, and the Arabic guide
tests/                   the suite, including the frozen promotion gate
desktop/                 the Tauri shell
```

## Documentation

| Document | What it holds |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | the layers, the modules, the state on disk |
| [docs/AGENTS.md](docs/AGENTS.md) | the 30 domains, the 10 specializations, routing |
| [docs/QUALITIES.md](docs/QUALITIES.md) | the thirteen qualities, their laws, their models, and the three fixed foundations |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | the trust boundaries, the abuse cases, the residual risks |
| [docs/SUPPLY_CHAIN.md](docs/SUPPLY_CHAIN.md) | the dependency licences, the pinning, the provenance register |
| [docs/SCALING.md](docs/SCALING.md) | the device tiers, the context window, and where local ends |
| [docs/LOGGING.md](docs/LOGGING.md) | the two logs, the redaction, and the chain verifier |
| [SECURITY.md](SECURITY.md) | what the safety layer enforces, and what it does not |
| [todo.md](todo.md) | every deliberate limit and every open task |
| [PRD.md](PRD.md) | the endpoints and the acceptance criteria (Arabic) |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | what this release replaced, and why |
| [docs/AR/دليل-المشروع.md](docs/AR/دليل-المشروع.md) | the Arabic guide |
| [docs/AR/دليل-الأمان.md](docs/AR/دليل-الأمان.md) | the Arabic safety guide |

## Contributing

Contributions are welcome — especially the held-out evaluation set, a real
operating-system sandbox, a typed-decision dataset for System One, and a
second model backend to compare against. Every new capability needs a test
and a stated limit.

## License

Apache-2.0 — see [LICENSE](LICENSE). Base model weights must be under
Apache 2.0 or MIT; anything else needs a legal review first.

---

<div dir="rtl">

## بالعربية

**OSS Work / OS_V1** وكيل ذكاء اصطناعي محلي موحّد: يخطّط، يقرر، يتحقق، ثم ينفّذ — على جهازك أنت، بلا مزوّد وبلا مفاتيح وبلا إنترنت في المسار الأساسي.

- **وضعان:** `Plan` يقترح خطة ولا ينفّذ شيئاً، و`Build` ينفّذ الخطة المعتمدة ويتحقق من كل خطوة.
- **نظامان:** System One للقرارات السريعة المنظّمة (التوجيه، التحقق، تقدير الخطورة) باحتمالات معايرة، وSystem Two (محرك llama.cpp المحلي) للتخطيط والتوليد. المستخدم يرى نموذجاً واحداً فقط.
- **300 وكيل متخصص:** 30 مجالاً × 10 تخصصات، لكل وكيل أدواته ومستوى خطورته وقواعد تحققه وقالب خطته.
- **طبقة أمان لا يعدّلها النظام:** أذونات صريحة، موافقة بشرية للأفعال غير القابلة للتراجع، سجل تدقيق مقاوم للتلاعب، مفتاح إيقاف فوري، دفاع ضد حقن التعليمات، وأسرار مشفّرة.
- **ذاكرة بأربعة أنواع لا تختلط:** وقائع، خبرات، مهارات، افتراضات — محلية، مُصدَّرة بإصدارات، وتحت سيطرتك.
- **تعلّم ذاتي ببوابة:** تسجيل ← تعلّم ← سؤال ← اختبار على مجموعة مجمّدة ← ترقية، مع تراجع بخطوة.

الأرقام في هذا الملف مقيسة من الكود، واختبار `tests/test_release_assets.py` يُفشل البناء إذا تعارضت مع الواقع. الحدود الصريحة — نموذج 3B، متصفح للقراءة فقط، sandbox على مستوى Python لا النظام، بلا مصادقة على API المحلي — موثّقة في `todo.md` و`SECURITY.md`.

**التشغيل:** `pip install -e ".[dev]"` ثم `python -m pytest tests/ -q` ثم `python -m osv1.interface.api` (اللوحة الحية على `127.0.0.1:8080`).

</div>
