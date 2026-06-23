# autoresearch: Durak local-heuristics lab

This is an experiment to have an LLM autonomously search for a strong **memoryless**
strategy for two-player *podkidnoy* Durak, under a locked rules engine, and measure how
far simple local heuristics can go against fixed baselines — including a memory-counting
opponent.

In **experiment mode**, you edit the heuristic strategy. In **meta mode**, you edit the
search policy (directions, loop notes, diagnostics, helper scripts). Neither mode may
change the locked contract (see **Locked vs mutable**). Everything else is the fixed
harness.

## Operating model: inner experiment loop + outer meta loop

This repo is run by one autonomous agent in two modes:

1. **Experiment mode**: search for a better memoryless heuristic.
2. **Meta mode**: improve the feedback loop itself.

The transcript is not the source of truth. Durable state lives in this file, especially:

* `## Current best`
* `## Open questions`
* `## Editable research directions`
* `## Loop notes`
* `## Rejected directions`

The agent should periodically rewrite these sections so the next cycle starts from compressed evidence rather than from the chat transcript.

Default cadence:

* Run **5 experiment attempts**.
* Then run **1 meta-review**.
* Repeat until the human interrupts, the metric plateaus, or further improvement would require weakening a locked invariant.

## Locked vs mutable

Do not let the meta-agent rewrite the **contract**. Let it rewrite only the **search
policy**.

| Locked (contract) | Mutable (search policy) |
|-------------------|---------------------------|
| README rules | heuristic strategy (`strategy_heuristic.cpp`) |
| Durak engine | `program.md` research directions |
| baselines (B0/B1/B3/B4) | `program.md` loop notes |
| metric formula | `program.md` rejected directions, open questions, current best |
| keep/revert thresholds | analysis diagnostics (`analysis.ipynb`) |
| tests, forbidden checks | helper scripts for speed/logging (`scripts/`) |
| full-eval seed counts | |

Meta mode may edit only the **mutable** column. Experiment mode may edit only the
heuristic strategy row. Neither mode may touch the locked column — not even to "clarify"
or "optimize" the contract.

## Setup

To start a new experiment:

1. Choose a run tag automatically from today's date, e.g. `jun22`.
   If `autoresearch/<tag>` already exists, append a suffix: `jun22b`, `jun22c`, etc.
2. Create the branch from current master:
   `git checkout -b autoresearch/<tag>`.
3. Read the in-scope files:
   - `README.md`
   - `durak/include/policy_core.hpp`
   - `durak/src/strategy_heuristic.cpp`
   - `program.md`
   - `analysis.ipynb`
4. Run `durak\build.bat test`.
5. Initialize `results.tsv` if missing.
6. Start the loop. Do not wait for human confirmation.

## What you CAN and CANNOT do

Permissions follow **Locked vs mutable** above. The meta-agent rewrites search policy,
not contract.

### Experiment mode permissions

During an individual strategy experiment, you may edit exactly one mutable file:

* `durak/src/strategy_heuristic.cpp`

You CAN:

* Change the body of `choose_move_core`.
* Add, remove, reorder, or simplify local heuristics.
* Tune numeric constants.
* Update the manifest (`kHeuristicCount`, `kParameterCount`, `kComplexity`) to match.
* Use only `LocalFeatures` always and the optional `MemoryFeatures*` only as a refinement of the same heuristic logic.

You CANNOT during experiment mode:

* Edit anything in the **Locked** column (engine, baselines, metric, thresholds, tests, full eval).
* Use `static` or global mutable state to remember turns, cards, seeds, games, or opponent actions.
* Add I/O, files, networking, clock access, threading, or randomness inside `strategy_heuristic.cpp`.
* Add a heuristic class that fires only when `memory != nullptr`.
* Edit `analysis.ipynb` to make a result look better.

### Meta mode permissions

After every 5 experiment attempts, enter meta mode.

In meta mode, you may edit **mutable** items only:

* `program.md` — durable sections (`## Current best`, `## Open questions`, `## Editable research directions`, `## Loop notes`, `## Rejected directions`) and loop guidance that does not change thresholds or eval sizes
* `analysis.ipynb` — diagnostics only (keep rate, discard reasons, complexity drift, B4/search divergence)
* `scripts/` — helper scripts for faster triage, log parsing, or safe caching that does not affect simulation results
* `README.md` — loop documentation only; do not change locked rules or metric definitions

You may NOT edit anything in the **Locked** column:

* README rules / Durak rules
* Durak engine, simulator, RNG
* B0/B1/B3/B4 baselines
* metric formula or Occam penalty
* keep/revert thresholds or gate seed counts
* tests, forbidden checks
* full-eval protocol (5M seeds, paired eval, CI method)

Allowed meta improvements include:

* Add a faster smoke check before a full run (same seeds/thresholds).
* Improve log parsing and triage output.
* Cache safe intermediate outputs that do not affect simulation results.
* Add notebook diagnostics for loop health.
* Prune research directions that repeatedly failed.
* Append rejected directions so the agent does not retry them.
* Rewrite the next batch of research directions based on evidence.

Meta changes must be committed with a `meta:` prefix. Strategy improvements must be committed with an `exp:` prefix.

## The metric

The harness reports **paired** scores over deal seeds. For each seed the challenger plays
both seats against the opponent on the same deck; per-game scoring is win=1, draw=0.5,
loss=0, and `pair_score` is the mean challenger points across the two games. The headline
number is `point_rate = mean(pair_score)`.

- **Reporting / final claim**: `point_rate(B2 vs B4)`.
- **Search objective** (drives keep/discard, smoother gradient):

```
search_score = 0.50 * point_rate(B2 vs B4)
             + 0.30 * point_rate(B2 vs B1)
             + 0.20 * point_rate(B2 vs B0)
             - complexity_score / 10000
```

B4 is the primary benchmark for reporting; the composite ladder score only stabilizes
search. `complexity_score = 100 * heuristics + 10 * parameters` (the Occam term).

**Simplicity (Occam) criterion**: if two variants have `point_rate` within 0.005, prefer
the one with the lower `complexity_score`. Removing a heuristic for equal-or-better score
is a win. A tiny gain that adds an extra heuristic or parameter is usually not worth it.

## Evaluation protocol (no peeking)

Gates for fast feedback; decide keep/discard **only** on gate 3 (full). Do not stop
on the first time a confidence interval crosses a threshold during a batch — that is
sequential peeking.

| Gate | Command | Seeds | Purpose |
|------|---------|-------|---------|
| 0 smoke | `match --opponent B4 --seeds 5000` | 5k | crash / illegal move |
| 1 B4 | `triage.bat b4` | 100k | cheap B4-only signal (~1.5s) |
| 2 ladder | `triage.bat quick` | 100k × 3 parallel | composite `search_score` (~6s) |
| 2b medium | `triage.bat medium` | 500k × 3 parallel | confirm maybe zone (~20s) |
| 2c dual | `triage.bat dual` | 100k × 3 × 2 seeds | two quick ladders, seed 0/1 (~12s) |
| 3 full | `triage.bat full` | 5M × 3 parallel | **keep/discard only here** (~1.7 min) |

Quick delta rules (100k seeds; SE ≈ 0.0016 → noise ±0.003):

| Δ search / Δ B4 | Action |
|-----------------|--------|
| both < 0.003 | discard (no full) |
| either 0.003–0.006 | `triage.bat medium` or `triage.bat dual`, then re-check |
| Δsearch ≥ 0.006 **or** ΔB4 ≥ 0.005 | `triage.bat full` (B4-first catches reporting wins) |

Shortcut (rebuild + gates 0–2, optional gate 3):

```bat
set BEST_SEARCH=0.77341
set BEST_B4=0.61206
scripts\triage.bat quick
scripts\triage.bat full
```

Set `BEST_SEARCH` to the current best `search_score` from `results.tsv`. Set `BEST_B4` for
early exit: if B4 drops more than 0.005 below best, gate 2 skips B1/B0. `triage.bat full`
runs gate 2 (quick) then gate 3 only when thresholds above are met.
Override with `FORCE_FULL=1` when you deliberately want a full eval despite low delta.

Rebuild during the loop: `durak\build.bat fast` (incremental; skip CMake reconfigure).
Use `durak\build.bat test` only after a **keep**, or when unsure.

Confidence intervals are normal-approximation by default (`--ci normal`); `--ci bootstrap`
is available but unnecessary at 5M seeds.

**keep vs current best** (full_eval only):

```
search_score_full      >= best_search_score + 0.005
AND lower_ci(search)    >= best_lower_ci
```

When within 0.005, prefer lower `complexity_score`.

**dominates B4** (a reporting claim, not required to keep):

```
lower_ci(point_rate vs B4) > 0.52
```

**Memory ablation** (run after a `keep`, not every step):

```
durak\build\simulate.exe --mode ablate --eval full
```

This runs B3 (the same core with memory enabled) vs B2 (same core, no memory). A
`point_rate` near 0.5 means memory adds nothing to this logic; the value of memory for the
current heuristics is roughly `point_rate(B3 vs B2) - 0.5` scaled to your interpretation.

## Output format

`simulate` prints progress lines per batch and a summary, e.g.:

```
--- ladder results ---
B2 vs B4           point_rate=0.49151  ci95=[0.49079, 0.49224]  win=0.0372 loss=0.0624 split=0.9004  ...
B2 vs B1           point_rate=0.92294  ci95=[0.92141, 0.92447]  ...
B2 vs B0           point_rate=0.96037  ci95=[0.95918, 0.96155]  ...
search_score=0.68334  (0.5*B4 + 0.3*B1 + 0.2*B0 - complexity/10000)
reporting_point_rate_vs_B4=0.49078  lower_ci=0.48976  complexity=310
```

Run the loop's evaluation with output redirected to a log (do NOT flood your context):

```
durak\build\simulate.exe --mode ladder --eval full --batch 500000 > durak\run.log 2>&1
```

Then read the summary lines from the log.

## Logging results

When an experiment finishes, append a row to `results.tsv` (tab-separated; do NOT use
commas — they break in descriptions). Leave `results.tsv` untracked by git.

Columns:

```
commit	opponent	point_rate	search_score	lower_ci	games	complexity	status	description
```

1. git commit short hash (7 chars)
2. opponent: `B4` for the headline row; optionally also `B1`, `B0`, or `B3vsB2` (ablation)
3. point_rate achieved (e.g. 0.491510) — use 0.000000 for crashes
4. search_score (composite; for non-B4 rows you may repeat the run's search_score)
5. lower_ci of the relevant metric
6. number of games (= 2 * seeds)
7. complexity_score from the manifest
8. status: `keep`, `discard`, `crash`, or `timeout`
9. short text description of what this experiment tried

## The experiment loop

The loop runs on a dedicated branch (e.g. `autoresearch/jun22`).

LOOP FOREVER:

1. Note the current best commit and its `search_score` from `results.tsv`.
2. Edit `durak/src/strategy_heuristic.cpp` with one experimental idea (and update the
   manifest). Keep changes minimal and Occam-friendly.
3. Fast triage (do **not** commit yet):

```bat
set BEST_SEARCH=<best search_score from results.tsv>
set BEST_B4=<best B4 point_rate from results.tsv>
scripts\triage.bat quick
```

   Read `durak\triage.log` (or console). Discard immediately if gate 0 fails or gate 2
   shows a clear regression vs `BEST_SEARCH`.

4. Escalate by delta (or set `FORCE_FULL=1`):

```bat
rem maybe zone (0.003–0.006):
scripts\triage.bat medium
scripts\triage.bat dual

rem full keep/discard gate:
scripts\triage.bat full
```

   Or: `durak\build\simulate.exe --mode ladder --eval full --batch 500000 > durak\run.log 2>&1`

5. Read the summary from `durak\triage.log` or `durak\run.log`.
6. Append row(s) to `results.tsv` (do NOT commit results.tsv).
7. Apply the keep rule (full_eval only). If **keep**:
   - `git add durak/src/strategy_heuristic.cpp && git commit`,
   - `scripts\post_keep.bat` (tests + ablation + analysis; skip slow steps when inert):

```bat
set SKIP_ABLATE=1
set SKIP_ANALYSIS=1
scripts\post_keep.bat
```

   Log `B3vsB2` row when ablation runs. Refresh charts with `scripts\run_analysis.bat`
   when `SKIP_ANALYSIS` was set. If **discard**: `git checkout -- durak/src/strategy_heuristic.cpp` (no commit was made).
8. Parameter sweeps (one numeric constant): prefer `scripts\sweep_atk_trump.py` pattern —
   `build.bat fast` per value, gate 1 (`match B4 --eval quick`) only; stops early if no
   B4 improvement.

## Meta-review loop

After every 5 experiment attempts:

1. Review the last 5 rows or attempted rows in `results.tsv`, plus recent git diffs and logs.
2. Classify each attempt:
   - useful signal
   - noisy/inconclusive
   - obvious regression
   - crash/bug
   - repeated failed direction
   - complexity-only change
3. Identify the biggest feedback-loop bottleneck:
   - slow build
   - slow full eval
   - weak quick/full correlation
   - unclear logs
   - repeated doomed ideas
   - too many full evals
   - too few promising candidates reaching full eval
4. Make at least one concrete loop improvement if safe:
   - update `program.md`
   - improve `analysis.ipynb` diagnostics
   - improve a helper script
   - add a log parser
   - prune research directions
5. Append compressed notes to `## Loop notes`.
6. Rewrite `## Editable research directions` with the next 5 experiments.
7. Commit meta changes:

```bat
git add program.md analysis.ipynb scripts
git commit -m "meta: tighten autoresearch feedback loop"
```

If there are no safe meta changes, append a note explaining why to `## Loop notes` and
continue experiments.

**Crashes**: if a run produces no summary, read the tail of `durak\run.log`. If it is a
trivial bug you introduced, fix it and re-run. If the idea is fundamentally broken, log
`crash` and move on.

**NEVER STOP**: once the loop has begun, do NOT pause to ask the human whether to continue.
The human may be away and expects you to keep iterating indefinitely until manually
stopped. If you run out of ideas, think harder: re-read the heuristics, try removing one
to simplify, try combining near-misses, reconsider the take/throw-in trade-offs, study
where B4's memory actually helps (via the ablation and the win/loss/split breakdown). The
loop runs until the human interrupts you.

---

# Durable agent memory

The sections below are editable by the agent during meta mode.

## Current best

- Commit: `d5bca3c`
- B4 point_rate: 0.61938
- Search score: 0.77742
- Lower CI: 0.61913
- Complexity: 100
- Why it is best: Narrowed finish pile trump dump window to `deck<=5` (was 6); +0.007 B4 vs AD. Pile-only; open strip unchanged.

## Open questions

- Which local situations does B4 exploit most? Likely midgame when B2 opens pairs too early or hoards trumps before finish window — open-strip widening regressed sharply (AK). **Full-eval W/L/S at AQ:** win=0.379 loss=0.113 split=0.509 — ~51% split games; next gains need split→win via attack timing, not defense.
- Is the B2 weakness mostly attack choice, defense choice, take/pass threshold, or trump conservation? **Attack/finish** — pile trump dump axis drives all keeps since exp P; defense trump ±5 (BJ/BK) and take tweaks regressed or neutral.
- Are B1/B0 gains misleading relative to B4? Yes — B1/B0 ~0.945/0.969 flat while B4 moved 0.49→0.61; search_score tracks B4 for keeps.
- Does complexity reduction improve B4 parity? Already at complexity 100 (H1-only); further simplification neutral; widening open strip hurts.

## Editable research directions

Next 5 experiment ideas:

1. **Pair delay deck>=5 vs 6** — CD medium 0.62160 vs BY 0.62155; pick one via medium/dual only (no new knobs).
2. **Full eval gate** — run `triage.bat full` on deck>=5 only if willing to spend ~1.7m to confirm sub-gate +0.002 (likely discard).
3. **Pair delay + pile unchanged** — manifest-only confirm; no code change (skip as experiment).
4. **Split diagnostic on CD** — compare W/L/S vs AQ on medium logs (split ~0.501 vs 0.509).
5. **Hold AQ** — do not keep sub +0.002 without full gate; pile finish window still locked.

Rules for selecting ideas:

- Prefer one-change experiments.
- Prefer simplification when score is flat.
- Prefer changes that can be screened by quick B4 signal.
- Avoid retrying rejected directions unless a new mechanism is given.

## Rejected directions

Append failed idea classes here so they are not retried.

```text
- direction: open strip / endgame open widening (opp<=4+ or deck window on open path)
  evidence: exp AK quick B4 0.598 (−0.014 vs best); prior open deck<=6 neutral
  do not retry unless: pile-only axis with different trigger (not same-rank open strip)

- direction: defense / voluntary take / pile cap / same-rank trump defense
  evidence: exp K–N quick −0.01 B4; transcript probes
  do not retry unless: new mechanism unrelated to take/pass

- direction: pile opp<=6
  evidence: exp AE probe regression; quick B4 drop
  do not retry unless: paired with deck<=5 narrow window

- direction: pile opp<=4 (when best is opp<=5)
  evidence: exp AS quick B4 −0.009 vs AQ
  do not retry unless: —

- direction: pile dump requires >=2 trumps (pile path only)
  evidence: exp AX quick B4 −0.010 vs AQ
  do not retry unless: —

- direction: inverse strip (skip trump dump when deck=0 opp<=2)
  evidence: exp AY quick B4 −0.002 vs AQ
  do not retry unless: —

- direction: pile deck<=1
  evidence: exp BB quick B4 −0.020 vs AQ
  do not retry unless: —

- direction: phase-split void pile -9/-10 when deck>5
  evidence: exp BD/BF quick neutral vs AQ
  do not retry unless: global void change (not phase-split)

- direction: pile deck<=3/4 dual/medium without dual agreement
  evidence: exp BC/BG medium +0.003 B4, dual disagree, below full gate
  do not retry unless: dual agrees on two seeds AND medium >= +0.005 B4

- direction: defense trump cost +45/+55
  evidence: exp BJ/BK b4 neutral vs AQ
  do not retry unless: —

- direction: attack trump penalty +95 (vs +100)
  evidence: exp BL b4 neutral
  do not retry unless: —

- direction: global void pile -9
  evidence: exp BI/AL b4 neutral vs AQ
  do not retry unless: —

- direction: pile deck>=6 (widen finish window)
  evidence: exp BH b4 −0.007 vs AQ; prior Y/AM neutral at wider deck
  do not retry unless: —

- direction: pile deck>=9
  evidence: exp Z/Z2 quick worse than deck<=6
  do not retry unless: —

- direction: pile opp<=3 (finish combo)
  evidence: exp BM quick B4 0.590 (−0.030 vs AQ); worse than opp<=4 AS −0.009
  do not retry unless: paired with different deck window

- direction: attack trump penalty +105
  evidence: exp BO quick neutral vs AQ (same as BL +95)
  do not retry unless: —

- direction: void open -6 / pair deck>=8 / pair cap min+1
  evidence: exp BP/BQ/BR quick neutral vs AQ
  do not retry unless: combined with measurable quick delta >= +0.003

- direction: skip midgame pair-open entirely
  evidence: exp BS quick B4 −0.002; split↓ win↑ but net B4 loss
  do not retry unless: paired with finish tweak that recovers B4

- direction: pile deck<=4 / open strip opp<=2 / void pile -7 / pair deck>=10
  evidence: exp BU/BV/BW/BX quick neutral vs AQ
  do not retry unless: —

- direction: void open -7 / void -8 global / skip pile deck>5 / pair cap min+3
  evidence: exp BZ/CA/CB/CC quick neutral vs AQ
  do not retry unless: —

- direction: pair-open deck>=4 / deck>=3
  evidence: exp CF/CH quick B4 −0.001..−0.002 vs AQ
  do not retry unless: —

- direction: pair-open deck>=8 / deck>=10 alone
  evidence: exp CG/BQ/BX quick +0.002 but below gate; deck>=5/6/7/8 cluster similar
  do not retry unless: combined with second axis OR full eval shows >= +0.005
```

## Loop notes

Append compressed meta-review notes here.

Format:

```text
date/window: jun22 batch-1 (5 attempts AK–AP)
- attempts: 5 discards (1 regression AK, 4 neutral); 0 full evals; 0 keeps
- bottleneck: plateau at AD — micro-tweaks within ±0.0005 B4 on quick; open widen fails
- what changed: (prior session) triage medium/dual/full gates, post_keep.bat, analysis diagnostics
- result: best unchanged f86282d B4 0.61206 search 0.77341
- next bias: pile-only parameter sweeps via b4 gate; avoid open strip; batch combos only after single-axis sweep
```

```text
date/window: jun22 batch-2 (AQ–AV)
- attempts: 1 keep (AQ deck<=5), 4 discards; 1 full eval
- bottleneck: deck window sensitive — 5 beats 6; 4/3 neutral/maybe
- what changed: exp AQ committed d5bca3c
- result: B4 0.61938 search 0.77742 (+0.007 B4 vs AD)
- next bias: refine deck<=5 only; medium gate for AU deck<=3; skip opp narrow
```

```text
date/window: jun22 batch-3 (AW–BB)
- attempts: 5 discards (2 regressions AX/BB, 1 mild AY, 2 maybe AW/BA below gate); 0 keeps
- bottleneck: deck window asymmetric — narrower than 5 hurts; 3/2 need dual before full
- what changed: none (best unchanged)
- result: d5bca3c B4 0.61938 search 0.77742
- next bias: hold deck<=5; dual for deck<=3; no >=2-trump pile gate
```

```text
date/window: jun22 batch-4 (BC–BG)
- attempts: 5 discards; 0 full evals; 0 keeps
- bottleneck: deck<=3 stable maybe (+0.003) but never crosses gate; phase-split void neutral
- what changed: none
- result: d5bca3c B4 0.61938 search 0.77742
- next bias: hold AQ; close deck/void sweeps; need qualitative new axis for next keep
```

```text
date/window: jun22 batch-5 (BH–BL)
- attempts: 5 discards (1 regression BH deck<=6, 4 neutral); 0 full evals; 0 keeps
- bottleneck: AQ plateau — all single-knob tweaks within b4 noise (±0.0003)
- what changed: closed deck sweep (6 regresses, 5 best); void/defense/attack knobs neutral
- result: d5bca3c B4 0.61938 search 0.77742
- next bias: W/L/S guided ideas; finish combo opp<=3; delayed pair-open
```

```text
date/window: jun22 batch-6 (BM–BR)
- attempts: 5 discards (1 regression BM opp<=3 −0.030, 4 neutral); 0 full evals; 0 keeps
- bottleneck: AQ hard plateau — open/pair/trump/void knobs all within quick noise; W/L/S shows ~51% split
- what changed: W/L/S diagnostic logged; closed finish opp<=3 and trump +105 / pair-delay axes
- result: d5bca3c B4 0.61938 search 0.77742
- next bias: skip midgame pairs; narrow pile deck<=4; tighter open strip opp<=2; split→win attack timing
```

```text
date/window: jun22 batch-7 (BS–BX)
- attempts: 5 discards (1 mild regression BS −0.002, 4 neutral); 0 full evals; 0 keeps
- bottleneck: pair/finish/void axes exhausted at quick resolution; BS shifts W/L/S (split 0.509→0.468) but loses B4
- what changed: closed batch-6 directions (BU/BV/BW/BX); logged BS W/L/S side effect
- result: d5bca3c B4 0.61938 search 0.77742
- next bias: partial pair delay deck>=6; void open-only; early pile pass; pair cap min+3
```

```text
date/window: jun22 batch-8 (BY–CC)
- attempts: 5 discards (1 maybe BY +0.002 quick/medium, 4 neutral); 0 full evals; 0 keeps
- bottleneck: first measurable B4 lift since AQ but below full/medium gate (+0.003); split 0.509→0.502 on BY
- what changed: closed void-open / pile-pass / pair-cap / void-8 axes; opened pair-delay deck threshold sweep
- result: d5bca3c B4 0.61938 search 0.77742 (BY best probe 0.62155 medium)
- next bias: sweep deck>=5/6/7 for pair-open; medium/full only if >= +0.003 B4 on quick
```

```text
date/window: jun22 batch-9 (CD–CH)
- attempts: 5 discards (3 maybe +0.002 at deck>=5/7/8, 2 mild regressions deck>=3/4); 0 full evals; 0 keeps
- bottleneck: pair-delay cluster stable +0.002 medium but below +0.003 escalate and +0.005 keep gates
- what changed: deck threshold mapped — best CD deck>=5 medium 0.62160 (+0.0022 B4); split ~0.501
- result: d5bca3c B4 0.61938 search 0.77742 unchanged
- next bias: deck>=5 vs 6 tie-break on medium; optional full on CD only; no keep without gate
```
