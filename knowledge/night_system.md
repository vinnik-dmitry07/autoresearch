> **Design history — not a live verdict.** Early autonomous-loop review (2026).
> Frozen numbers and phase verdicts: `system/README.md` + `knowledge/DEPLOY_BOOK_SCOPE.md`.

My opinion: **the system has become very good as a skeptical research stack**, but it is still **not ready to be an autonomous “AI researcher while I sleep”** without additional safeguards.

I would rate it as follows:

**8/10 as a research system.**
**5–6/10 as a nighttime autonomous loop.**

## What is genuinely strong about it

The main strength is the right architecture: `lib.py` is declared as the single leaf module containing the canonical engine, P&L, metrics, PSR/DSR/bootstrap, portfolio math, and an independent reconciliation path through vectorbt. This is exactly what is needed to avoid spawning multiple backtest engines with different results.

The second strength is `data.py`: it explicitly encodes honesty about survivorship bias. The structural list includes delisted/acquired pairs, yfinance is labeled as a free biased fallback, and Sharadar is treated as the path to survivorship-free and point-in-time data. This is very good design.

The third strength is `evaluate.py`: it has exactly the battery needed for this kind of strategy — cost curve, delay decay, subperiods, regimes, capacity, artifact flags, gates, PBO/DSR/MinTRL, and Quality Score. This is not just “calculate Sharpe”; it is a full reviewer.

The fourth strength is `research.py`: it combines baseline, vectorbt verification, CV, robustness, ablation, random-direction control, reliability, synthetic null, cost/capacity ladder, and quality score into one end-to-end audit. This already looks like a real research harness.

## Main idea

The system is correctly moving from:

```text
“AI, find a strategy with high Sharpe”
```

to:

```text
“AI, propose a hypothesis, run it through an independent audit, and prove that it is not an artifact”
```

That is exactly the right direction.

## What I would fix before nighttime AI

I would do 5 things.

1. **Lock the baseline with a baseline lock file.**

```text
BASELINE_LOCK.json
  data_hash
  code_hash
  config
  pair list
  canonical metrics
  vectorbt max_diff
```

Any code change should be compared against it.

2. **Separate gates into report gates and trading gates.**

```text
report_gate:
  may look at the full history, used for analysis

trading_gate:
  walk-forward / train-only only,
  used to build the book
```

3. **Add an experiment registry.**

Every nighttime run should write:

```text
experiment_id
hypothesis
code diff
data version
config
metrics
reason accepted/rejected
```

Without this, the AI will rediscover the same ideas again and again.

4. **Make the verifier mandatory after any change to `lib.py`.**

Minimum:

```text
py_compile
unit tests
vectorbt diff
empyrical metrics diff
baseline regression diff
no import cycles
```

5. **Forbid the nighttime agent from changing `lib.py` directly.**

Let it create new experiments in `experiments/`, `overlays/`, and `candidate_rules/`, but let the core change only through a separate review.

## My verdict

The system is **good and mature**. It is already much better than typical quant research code because it has:

* a single canonical engine;
* independent verification through vectorbt;
* explicit handling of survivorship bias;
* ex-ante candidate discipline;
* robustness / ablation / delay / cost checks;
* PBO / DSR / bootstrap;
* separate hunt / evaluate / book / research layers.

But for “AI while I sleep,” it lacks an **operational safety layer**: baseline lock, experiment registry, strict write permissions, CI/regression tests, and walk-forward-only gates.

My short conclusion:

> As a research stack — yes, this is already a strong system.
> As an autonomous nighttime researcher — almost, but first it needs to close selection look-ahead, import consistency, unused cost parameters, and PIT-data TODOs. After that, nighttime loops can be launched, but only with permission to propose PRs/experiments, not to silently change the baseline.

I’ll answer as a quant research systems engineer, an ACM Software System Award laureate for reliable research platforms.

Yes. I would formalize this not as “the AI should search for Sharpe,” but as a **multi-criteria system for improving the research pipeline**.

The main rule:

> Every change must improve at least one item from the list and not worsen the others beyond the allowed limit.

So not:

```text
found a strategy with higher Sharpe
```

but:

```text
the change sped up the audit by 35%,
did not change baseline metrics beyond tolerance,
preserved the vectorbt diff,
did not increase selection bias,
kept the result reproducible
```

You already have a good foundation for this: `lib.py` contains the single canonical engine and independent verification, `evaluate.py` has a reliability battery with cost/delay/subperiod/regime/DSR/PBO/bootstrap checks, `hunt.py` has ex-ante prefiltering and OOS/multiple-testing discipline, and `research.py` assembles an end-to-end skeptical audit.

I would turn your 10 points into a **Change Acceptance Scorecard**:

```text
Change must improve:
  speed
  cost
  simplicity
  result reliability
  reproducibility
  anti-bias / anti-reward-hacking
  auditability
  robustness
  safety of changes
  hypothesis quality
```

But importantly: not every item should be “optimizable.” Some should be **hard gates**.

For example:

```text
HARD GATES:
  reproducibility
  no look-ahead
  no import-cycle
  vectorbt verification
  baseline regression tolerance
  deterministic seeds
  audit log exists

SOFT OBJECTIVES:
  speed
  cost
  simplicity
  hypothesis quality
  robustness margin
```

Otherwise, the agent will start “improving” speed at the cost of honesty, or hypothesis quality at the cost of reward hacking.

Practically, I would add a file like:

```text
SYSTEM_OBJECTIVES.yaml
```

with logic like this:

```yaml
hard_gates:
  reproducible:
    required: true
    evidence:
      - code_hash
      - data_hash
      - config_hash
      - seed

  no_accounting_regression:
    required: true
    checks:
      - vectorbt_max_diff <= 1e-10
      - baseline_metric_drift <= tolerance

  no_selection_leakage:
    required: true
    checks:
      - trading_gate_uses_train_only
      - walk_forward_selection_reported

  auditability:
    required: true
    evidence:
      - experiment_id
      - hypothesis
      - code_diff
      - metrics_before
      - metrics_after
      - rejection_reason_or_acceptance_reason

soft_objectives:
  speed:
    direction: minimize_runtime
  cost:
    direction: minimize_data_and_compute_cost
  simplicity:
    direction: minimize_complexity
  robustness:
    direction: maximize_stability
  hypothesis_quality:
    direction: maximize_novel_valid_hypotheses
```

For your night loop, I would make the final verdict on a change look like this:

```text
ACCEPT:
  hard gates passed
  at least one soft objective improved
  no critical metric degraded
  experiment is logged

REJECT:
  any hard gate failed
  improvement only exists in full-sample
  improvement disappears OOS / WF
  result not reproducible
  change increases complexity without measured benefit

QUARANTINE:
  promising but unstable
  needs human review
  touches lib.py / accounting / data logic / gates
```

A particularly important point: **hypothesis quality should not be measured only by the result**.

A good hypothesis should have:

```text
1. Economic reason
2. Expected failure mode
3. Minimal code change
4. Predefined evaluation
5. OOS / walk-forward check
6. Negative control
7. Clear rejection condition
```

For example, a bad hypothesis:

```text
Try 200 different z_win values and choose the best Sharpe.
```

A good hypothesis:

```text
Dual-class pairs with a stable voting/control discount should exhibit stronger
mean reversion after a corporate-event filter. Check: train-only classification,
OOS Sharpe, delay decay, cost ladder, random-direction control, DSR adjustment.
```

The final system formulation could be:

```text
The system is not allowed to maximize trading performance directly.

It must improve the research process by proposing hypotheses and changes that
increase speed, reduce cost, simplify the stack, improve reliability,
reproducibility, robustness, auditability, and safety, while reducing bias and
reward hacking.

Every accepted change must pass hard safety gates and produce an auditable
before/after report.
```

I would set this as the **top-level invariant** for the nighttime agent:

> The agent does not optimize Sharpe. The agent optimizes trust in the research process.
