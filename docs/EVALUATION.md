# The held-out evaluation — OS_V1

The specification's success test (section 1.1) is not that the system
*looks* capable. It is that a person who is not an expert gives OS_V1 a goal
and receives a verified, finished result — with no expert to operate the
system and no expert to check its work. A suite the system wrote for tasks
it already knows cannot measure that. This document describes the suite that
can, and what it has measured so far.

## What "held out" means, exactly

Held out is a property of **provenance**, and provenance is not something a
check can prove. The suite says so instead of claiming a check that cannot
exist. What it means here:

| Task kind | Where the ground truth comes from |
|---|---|
| `arabic_routing` | Written by hand **from the domain definitions** — never taken from the router's decisions. |
| `math` | Computed by the suite **from the arithmetic itself**, so a wrong answer is the model's, not the grader's. |
| `gap` | Questions **nobody can know**: a file that does not exist, tomorrow's visitors, a password. |
| `code` | The delivered answer's code is **executed in the sandbox** against its own tests. |

What a machine *can* verify, it does:

* a task that is a bare keyword would grade substring matching instead of
  routing, and is **refused, not scored**;
* a task whose expected domain claims none of its words is reported as a
  **finding about the vocabulary** — kept in the score, because hiding it
  would hide the finding.

## The four kinds of task, and what each can prove

| Kind | What it measures | What it cannot prove |
|---|---|---|
| `arabic_routing` (30) | an Arabic goal reaches the right domain and specialization | that the *answer* is good |
| `math` (15) | the delivered answer contains the exact number | reasoning about *why* the answer is right |
| `gap` (8) | the system does not fabricate on questions nobody can know | that a fluent non-answer is honest — the grading is an abstention-marker **proxy**, and says so |
| `code` (5) | the delivered answer contains code that passes its own tests, executed | that the code is good beyond its tests |

Total: **58 tasks**.

## Running it

```bash
oss-v1 graded              # all 58 tasks (needs the local engine)
oss-v1 graded --limit 3    # three engine tasks, for a smoke run
```

Routing tasks run offline. The other 28 need the local engine, and are
**skipped with their reason** when it is down — never scored as zero, because
"the model was not there" is not a failure of the model.

The report lands in `data-osv1/graded-evaluation.json` and feeds
`oss-v1 qualities --report`, which is where the qualities become measured
instead of targets.

## Measured: the routing tasks

The 30 routing tasks need no model, so they were graded first, against the
runtime as it stands. **The result is bad, and it is the point of the suite.**

| Measure | Value | Samples |
|---|---|---|
| Domain accuracy on natural Arabic goals | **9 / 30 = 0.30** | 30 tasks |
| `q_abstain` — System One not confident enough to keep its decision | **0.9833** | 60 decisions |
| `t1_p50` — fast-path latency | **40.8 ms** | 60 decisions |

The goals are ordinary sentences a user would write — "أصلح استعلام SQL
بطيء في قاعدة البيانات", "جهّز كشف رواتب الموظفين" — written from the domain
definitions. The router gets less than a third of them right, and System One
abstains on 98 % of the decisions it is asked for.

Why the suite reports this instead of hiding it: the routing that was
verified earlier worked on the phrasings the keyword lists were tuned with.
On sentences nobody tuned, it does not generalize. That is what a held-out
suite is for — and the fix (a real classifier, or a vocabulary built from a
**development** set) has to come from tasks that are not these 30.

The diagnosis the suite also reports: on 12 of the 30 tasks, the expected
domain claims none of the words in the sentence — the vocabulary cannot
describe its own work. That is a finding about the system, kept in the
score rather than hidden from it.

The 28 engine tasks need the local model. Measuring them once found two real
defects, which is what a held-out suite is for — and both were fixed before
the numbers below could mean anything.

## What measuring the engine tasks found

**A planned file write could never work.** The action engine mapped every file
tool to the step's `target` alone, so `file.write` was called without its
`content` argument and every write failed with
`missing 1 required positional argument: 'content'`. The content lives in the
step's `detail`, and it was never passed. The engine said so plainly in its
own answer — *"no Python script was created, the function was not written"* —
which is the system reporting a failure rather than inventing a success.
`tests/test_safety_layer.py` now executes a planned write end to end, which
is the test that was missing and let the defect survive. A step that names no
target is now reported as a malformed plan instead of surfacing as a
`TypeError`, or as a permission error that would blame the wrong thing.

**A question was graded as an answer.** For an arithmetic prompt the decision
engine asked the user, and its question quoted the right number among its
options. The grader scanned the delivered text for the expected number, found
it inside the question, and scored a pass — grading the question rather than
an answer. The status is now checked before any number is looked for:
`needs_information`, `needs_approval`, and `planned` fail the task with that
reason. The same rule was applied to the code grader, and an answer cut off
before its closing fence is now graded on the code it does contain instead of
failing for a missing fence.

## The cascade is measured on the same runs

Section 27.6 models System One and System Two as a cascade,
`E[T] = T1 + q·T2`. The suite measures it, and so does every run of the
runtime:

```bash
oss-v1 cascade            # T1, T2, q, and E[T] — all with their samples
```

Two escalation signals are recorded and never confused: `q_abstain` is the
share of System One decisions it was not confident enough to keep, which is
the `q` of the formula; `q_llm` is the share of calls the slow path
actually answered. A number without samples is not a result, so both carry
their counts and the distribution they were measured on.

The first full run also measured where the slow path breaks. On the Lite
tier (a 3B model on the CPU), `t2_p95` sat at **120,029 ms** — the old fixed
timeout, to the millisecond — and **15 of 56** engine calls (27 %) were
recorded as unreachable because they hit it. The inference timeout now
belongs to the device tier (Lite 300 s, Standard 120 s, Pro 60 s) instead of
being a constant in the client, and an explicit `OSS_LOCAL_TIMEOUT` is never
overwritten. `Settings.engine_timeout` existed before this and was read by
nothing; wiring it into the engine is what makes it a setting at all.

## What the suite does *not* do

* It does not grade style, usefulness, or whether the answer would satisfy a
  human. A human review is stronger, and this suite does not pretend
  otherwise.
* It does not measure learning across sessions. The learning exponent β
  needs a history of practice sessions, and the history is not long enough
  yet — so that quality stays a **target**, and the report says so.
* It does not tune the router. The routing tasks are frozen: improving the
  Arabic vocabulary on them would be tuning on the test set, so any
  improvement has to come from a separate development set.
