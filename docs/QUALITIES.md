# The thirteen qualities — OS_V1

Specification section 1.1 names the qualities; section 27 gives each one a
law, a formula, an engineering rule, and a test. This document says where
each of them lives in the code, and what is measured today.

The honest rule of the project applies here too: **a number without samples
is not a result**, and a quality with no measurement stays a target.

## The register

`osv1/quality/qualities.py` holds the thirteen entries, and
`osv1/quality/models.py` holds the formulas as functions.

```bash
oss-v1 qualities           # the register: law, formula, rule, test, metric
oss-v1 qualities --report  # what is measured today, and what is still a target
```

| # | Quality | Core law | Key formula | Where it is computed | Key metric |
|---|---|---|---|---|---|
| 1 | Speed | Roofline and Amdahl | `T = T_prefill + N·T_token` | `models.prefill_time`, `token_time`, `amdahl_speedup` | p95 latency |
| 2 | Intelligence | Universal intelligence, No Free Lunch | `1 − (1 − p)^n` | `models.best_of_n_success`, `confidence_interval` | Benchmark score with interval |
| 3 | Power | Reliability compounding | `P_job = Π p_i` | `models.job_reliability`, `step_reliability_with_retry` | End-to-end completion rate |
| 4 | Faster learning | PAC bound, power law of practice | `e(n) = e∞ + (e0 − e∞)·n^(−β)` | `models.fit_learning_curve`, `pac_sample_bound` | Learning exponent β |
| 5 | Imagination | World model, simulation lemma | `V(π) = E[Σ γ^t·r_t]` | `models.discounted_return`, `negative_log_likelihood`, `kl_divergence` | Prediction NLL, plan regret |
| 6 | Human-mind simulation (Ultra IQ) | Dual-process cascade | `E[T] = T1 + q·T2` | `models.cascade_time`, `chow_threshold` | The five Ultra IQ metrics |
| 7 | Absolute safety | Safety properties, rule of three | `P ≤ 3 / n` | `models.rule_of_three`, `residual_failure_probability` | Red-team failure bound |
| 8 | The best reverse engineering | Data-processing inequality | `ε ≤ ln(1/δ) / n` | `models.behavioral_parity`, `mismatch_bound` | Behavioral parity Π |
| 9 | Independence | Series availability | `A = Π A_i` | `models.series_availability`, `network_latency_floor` | Offline success rate |
| 10 | The SOM | Decision theory, proper scoring | `a* = argmin Σ p·Loss` | `models.softmax`, `sigmoid`, `combine_logits`, `value_of_information` | ECE, Brier, latency |
| 11 | Mathematical logic | SMT, floating-point error | `error ≈ κ·u` | `models.relative_error`, `dimensions_match`; `verifier.check_math` | Claims checked by a tool |
| 12 | Scientific grounding | Bayesian evidence | `Posterior odds = prior odds × LR` | `models.posterior_odds`, `confidence_interval`, `sample_size_for_margin` | Claims with checkable sources |
| 13 | Absolute knowledge | Entropy, memory physics | `KV bytes = 2·layers·kv_heads·head_dim·L·b` | `models.shannon_entropy`, `information_gain`, `kv_cache_bytes` | Needle recall, gap closure time |

Every formula is checked against the worked example the specification gives
for it, in `tests/test_osv1_quality.py`. A formula that drifts from the
specification fails the suite rather than a report.

## What the models changed in the system

Three of the engineering rules are not commentary; they are code:

- **§27.11 — the verifier checks arithmetic.** `verifier.check_math` sends
  the numbers in the answer to exact decimal comparison against values
  recomputed from the source, checks that stated probabilities sum to one, and
  labels the outcome *"tested, not proven"* outside the decidable fragments.
- **§27.5 — the world model measures its own predictions.** Every prediction
  is compared with what happened, and `WorldModel.prediction_quality` reports
  the negative log-likelihood and the KL divergence between the predicted and
  the observed outcome, with their sample counts.
- **§27.13 — the memory cost of the window is computed, not guessed.**
  `tier_kv_cache` reports the KV cache of a full window per device tier, in
  16-bit and in 4-bit, which is what makes the 1M-token window a decision
  rather than a slogan.

## The three foundations that stay fixed

Section 1.1 says three things do not move, because a system built to break
its own limits needs exactly one set of limits it cannot break:

| Foundation | The rule | Where it is enforced |
|---|---|---|
| Safety | The safety layer, the permissions, the audit log, the kill switch, and the verifier's tests are refused by the promotion gate. | `osv1/learning/evolution.py` |
| Legal | Licences and terms of use are respected; a non-permissive licence waits for a legal review, and closed services are never reverse engineered. | `osv1/provenance.py`, `osv1/tools/rea.py` |
| Honesty | Anything not measured is written as a target; every metric carries its sample count. | `osv1/eval/metrics.py`, `tests/test_release_assets.py` |

## The expert-free completion rate

The success test of section 1.1: a person who is not a technical expert
gives OS_V1 a goal and receives a verified, finished result without an
expert to operate the system or check its work.

`models.expert_free_completion_rate` counts it: each run contributes
`(completed, needed_human_intervention)`, and the rate is the share of runs
that finished without anyone stepping in. It is measured per task batch, with
the sample count. The held-out suite below measures the *score* on graded
tasks; the expert-free rate over a batch of real user goals is still a
target, and is not reported as if it were measured.

## What moves a quality from target to measured

The held-out suite ([docs/EVALUATION.md](docs/EVALUATION.md)) is what moves
the qualities that need a *task distribution* rather than a component test.
When a snapshot of it exists, `oss-v1 qualities --report` reads it and the
qualities it can honestly speak for stop being targets:

| Quality | What the suite measures |
|---|---|
| Intelligence | the score on the held-out tasks, with its confidence interval and its sample count |
| Human-mind simulation | the cascade of §27.6 — `q`, `T1`, `T2`, `E[T]` — measured on the same runs |
| Absolute knowledge | the share of answers that did not fabricate on questions nobody can know (a marker-based **proxy**, and labelled as one) |
| Speed | `p50`/`p95` of the fast path and the slow path, separately |

A snapshot that does not exist is reported as missing — never as zero,
because "the model was not there" is not a score. The suite never tunes the
router: its tasks are frozen, and any improvement to the vocabulary has to
come from a separate development set.

## Limits that physics and mathematics do not allow breaking

Section 27.14 lists them. The system works as close to them as it can:

| Limit | What OS_V1 does instead |
|---|---|
| No algorithm is best on every problem | targets the user's own task distribution |
| Program equivalence is undecidable | test-based evidence, containment, and "tested, not proven" labels |
| Processing cannot create information | infers with priors and confirms with tests |
| A minimum energy per erased bit | optimizes the bytes moved |
| Finite memory and bandwidth | quantization, device tiers, overflow to memory |
| A signal cannot beat light | runs locally |
| Real actions are irreversible | snapshots, rollback, and human approval |
| Evidence needs enough samples | reports bounds with their trial counts |
