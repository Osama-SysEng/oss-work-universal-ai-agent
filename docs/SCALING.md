# Capacity and scaling — OS_V1

OS_V1 is a local system. "Scaling" here means one machine, one user, and one
model — and being honest about where that ends.

## The device tiers

Spec section 23 gives the planning targets. They are confirmed by benchmark,
not by this file.

| Tier | RAM | GPU | Context window | Input budget (after the output reserve) |
|---|---|---|---|---|
| Lite | 16 GB | none | 128K tokens | 120K |
| Standard | 32 GB | 12-16 GB VRAM | 256K tokens | 248K |
| Pro | 64 GB | 24 GB+ VRAM | 1M tokens | 992K |

The tier is detected from the machine's memory, and it can be set with
`OSS_V1_TIER`. The VRAM figure is never guessed — there is no reliable
portable way to read it, so the tier only moves the context window.

```bash
oss-v1 context --file big-report.md   # how a text fits on this machine
```

The token count is an estimate of four characters per token, for mixed English
and Arabic text. The method is stated wherever the number is used, because a
capacity claim needs an honest method behind it.

## What happens when a task exceeds the window

1. The pieces that fit stay whole.
2. The rest is summarized — by the local model when it is up, by an
   extractive rule otherwise, and the result says which one produced it.
3. Every overflowed piece is listed with what replaced it, so nothing is
   dropped silently.
4. Retrieval from memory supplies the relevant experiences and skills for the
   parts that were summarized away.

Long answers are produced as chunks with checkpoints under
`data-osv1/state/<request>/`, so an interrupted run resumes instead of
starting over.

## Background work

The scheduler (`osv1/learning/scheduler.py`) keeps persistent jobs in a
local SQLite file and runs the ones that are due: the weekly personalization
session, and practice sessions. One failing job never stops the batch, and
the kill switch stops the scheduler before it starts the next job.

A single machine runs one worker. The queued work is small by design: a
personalization session over the user's own samples, and a practice session
over one project.

## The limits, stated plainly

- **A laptop is not production.** The system has no high-availability
  database, no distributed queue, and no worker isolation. It cannot
  substantiate a claim about arbitrary numbers of users.
- **The local model is the bottleneck.** A 3B quantized model is good at
  light tasks and decisions. Heavy work is split into smaller steps or
  queued, and the time to solution is reported per run.
- **The context window is a tier setting, not a measurement of quality.**
  A longer window does not make a small model reason better.
- **Everything is one user.** Memory is namespaced per user, but there is no
  authentication layer, and the local API has no multi-tenant isolation.
- **Before a service deployment** the work is listed in `todo.md`: an
  authenticated multi-tenant API, a shared queue, worker isolation, per-tenant
  quotas, a pooling database, backpressure, observability, disaster recovery,
  and load tests against a stated service-level objective.
