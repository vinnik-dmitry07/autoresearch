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
* `## Search mode`
* `## Open questions`
* `## Editable research directions`
* `## Loop notes`
* `## Rejected directions`

The agent should periodically rewrite these sections so the next cycle starts from compressed evidence rather than from the chat transcript.

Also maintain `## Search mode` (see **Durable agent memory**): the active exploration
strategy for the next experiment batch.

### Meta-review cadence (adaptive)

Run a **meta-review** when **any** trigger fires (check after each experiment attempt):

| Trigger | Action |
|---------|--------|
| **Counter** — 5 experiment attempts since last meta-review | Standard meta-review |
| **Keep** — any experiment kept | Meta-review **before** the next batch (update ablation map, set EXPLOIT/COMBO mode) |
| **Plateau** — 3 consecutive batches with 0 keeps and 0 full evals | Meta-review; switch search mode (usually EXPLORE → COMBO or PIVOT) |
| **Maybe-cluster** — 2+ probes in the last batch with medium/dual ΔB4 ≥ +0.002 on the same axis | Meta-review; plan a **sweep batch** or COMBO batch on that axis |
| **Axis closed** — same direction rejected 3+ times at quick/medium | Meta-review; append to `## Rejected directions`, stop that axis |

If no trigger fires, keep experimenting. Do not wait for exactly 5 attempts when a keep or
plateau trigger is active.

Default rhythm is still roughly **5 experiments → 1 meta-review**, but event-driven reviews
take priority over the counter.

### Search modes

Meta-review sets `## Search mode`. Experiment batches follow it.

| Mode | When | Experiment rule |
|------|------|-----------------|
| **EXPLORE** | New axis, flat score, or after a keep's first follow-up | **One change** per attempt; quick B4 screen first |
| **COMBO** | Single-axis maybe ≥ +0.002 medium (e.g. pair-delay, pile window) | **Two orthogonal changes** per attempt (hold best axis + test second); escalate on ΔB4 ≥ +0.005 quick |
| **SWEEP** | Meta plans a small grid on one parameter/window | **5 related variants** in one batch (see **Sweep batches**); one build cycle per variant |
| **ABLATE** | Best stack unclear; confirm load-bearing parts | **Disable one mechanism** per attempt (pile dump off, strip off, pair skip); quick only unless regression ≥ −0.005 |
| **PIVOT** | Current stack saturated; micro-tweaks capped below +0.003 medium | **Qualitatively new mechanism** only; no ±1 on exhausted axes |
| **EXPLOIT** | Immediately after a keep | Refine **one window** around the kept change; max 3 attempts then meta-review |

Keeps historically required **COMBO** (AQ pile-only, CQ pair+pile, CZ + open strip). Do not
stay in EXPLORE-only mode through a plateau.

### Sweep batches

When meta-review enters **SWEEP** mode, plan all 5 variants in `## Editable research
directions` as a labeled grid (e.g. `deck>=3/4/5/6/7` or `opp<=1/2/3/4/5`). The agent runs
them serially in one batch without asking the human:

1. Same baseline commit for all variants.
2. `build.bat fast` → `triage.bat quick` (→ `medium` if maybe) per variant.
3. Log every variant to `results.tsv` even if neutral.
4. After all 5: meta-review picks best signal, rejects closed cells, sets next mode.

Prefer gate 1 (`triage.bat b4`) for numeric sweeps; use `scripts\sweep_*.py` when one
exists. Do not run full eval on sweep variants unless one clears the normal full gate.

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

Enter meta mode when a **meta-review trigger** fires (see **Meta-review cadence**).

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

1. Note the current best commit, `search_score`, and **`## Search mode`** from
   `program.md` / `results.tsv`.
2. Edit `durak/src/strategy_heuristic.cpp` per the active search mode (and update the
   manifest):

   - **EXPLORE / PIVOT / ABLATE / EXPLOIT**: one change per attempt.
   - **COMBO**: two orthogonal changes (document both in the description).
   - **SWEEP**: one cell of the current sweep grid (meta lists all 5).

   Keep changes minimal and Occam-friendly.
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

When any **meta-review trigger** fires:

1. Review recent rows in `results.tsv` (last batch at minimum; last 15 if plateau), plus
   recent git diffs and triage summaries (not full logs).
2. Classify each attempt:
   - useful signal
   - noisy/inconclusive
   - obvious regression
   - crash/bug
   - repeated failed direction
   - complexity-only change
   - sweep cell (closed / open / best-in-grid)
3. Identify the biggest bottleneck — **search policy first**, harness second:
   - wrong search mode (EXPLORE on a combo axis, PIVOT needed)
   - repeated doomed ideas (missing `## Rejected directions` entry)
   - maybe-cluster not escalated to COMBO or SWEEP
   - too many full evals / too few promising candidates reaching full
   - slow build / slow full eval / weak quick–full correlation / unclear logs
4. **Set `## Search mode`** for the next batch (EXPLORE, COMBO, SWEEP, ABLATE, PIVOT, or
   EXPLOIT) with a one-line rationale.
5. Make at least one concrete loop improvement if safe (harness/diagnostics only):
   - update `program.md` durable sections
   - improve `analysis.ipynb` diagnostics
   - improve a helper script or add a sweep script
   - prune research directions / append rejected directions
6. Append compressed notes to `## Loop notes`.
7. Rewrite `## Editable research directions`:
   - **Normal modes**: next 5 experiments aligned with search mode.
   - **SWEEP mode**: label the 5-cell grid explicitly (variant 1…5).
8. Commit meta changes:

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

- Commit: `8487eb7`
- B4 point_rate: 0.68903
- Search score: 0.82464
- Lower CI: 0.68877
- Complexity: 100
- Why it is best: **QA** = ZW with the **defense reduced to its core**. The defense is now just:
  *cheapest beater (non-trump first), then take rather than burn an 8+ trump (`rank_of>=2`) while
  `deck>=5`, any pile size.* The two ZN shape tie-breaks (pair-keep `+4`, rank-reuse `−4`) are
  **dropped** — batch-2's broad take made them **net-harmful**. Full **+0.00288 search / +0.00409 B4**
  vs ZW (`310bc72`), with **fewer lines** (net −3). An **Occam simplification keep**: below the
  +0.005 add-gate, but it *removes* mechanism at robustly-better B4 (CIs non-overlapping) — and the
  Occam rule explicitly blesses "removing a heuristic for equal-or-better score."
- **The shape signals were obsoleted by the take.** On the WR/ZN base, pair-keep/rank-reuse were
  load-bearing (+0.0028 stack). Once the conservation take fires broadly, they conflict with it:
  ablating rank-reuse off gave +0.0015 search, ablating both gave +0.0023 (quick). The take changes
  *which* card is "cheapest," so the shape biases now mis-route the take.
- **Take floor re-shifted to 8+ (`rank_of>=2`).** With the shape signals gone, the cheapest beater
  changes, and the take optimum moved from rank>=3 (ZW) to **rank>=2** (+0.0027 search quick; rank>=1
  −0.0009 +loss; rank>=4 −0.0033). **deck>=5 still firm** (deck>=4 −0.024 — over-takes). Kept cell:
  rank>=2 / deck>=5 / no-cap.
- **Ladder:** B4 0.68903 (win 0.5311, split 0.3617, loss 0.1072), B1 **0.97519** (win 0.961), B0
  **0.98782** (win 0.979). B2 wins the majority of deals vs the memory-counting baseline.
- **Memory ablation:** B3 vs B2 **0.50000** exactly — **split 1.0000, identical play**. Removing the
  shape tie-breaks made the cheapest-beater unambiguous, so the wired memory prior now never changes
  a single move. Memory is fully inert.
- **Historical:** ZW `310bc72` B4 0.68494 / search 0.82176 (widened take, jun25 b2). ZN `ab2d08c` B4
  0.64805 / search 0.80025 (first defense keep, jun25 b1). WR `f5bb135` B4 0.64489 / search 0.79506
  (jun22 attack stack, saturated batches 102–113).

## Search mode

- Mode: **PIVOT (near ceiling, batch-5)** — EXPLORE (batch-4) found no productive new mechanism.
- Since: jun25 batch-4 — SA/SD proved the take is a hard unconditional optimum (no gate helps);
  SB/SC attack pile pair-keep inert. Defense/take and attack axes all closed.
- **Closed this run:** conservation take window (n_table/rank/deck corner); defense shape tie-breaks
  (harmful); take hand/opp gates (harmful); attack pile pair-keep (inert). Do not re-open these.
- Next batch type: **PIVOT** — only qualitatively new mechanisms, one per attempt, quick screen:
  1. **Throw-in pass discipline** — when piling on, sometimes stop early (`AttackDone`) to deny the
     defender a cheap cover that grows their hand we then can't punish. (Engine lets the attacker
     stop; jun22 tuned the trump-finish but not a non-trump early-stop.)
  2. **Endgame-specific defense** (`deck<=2`) — the take is off here; test a low-trump-cover-order or
     hold-a-cover-card rule for the closing exchanges where B4's counting bites most.
  3. **Open-from-longest-suit tie-break** — lead the lowest non-trump in our *longest* non-trump
     suit (deplete a long suit), only if it does not re-tread the jun22 shortest-suit result.
- Expect diminishing returns: QA already wins the majority vs B4 with zero memory. Keep the loop
  alive with periodic PIVOT probes; only escalate on a clear >= +0.003 quick signal.

## Open questions

- **(jun25 b3) The take subsumed the shape signals.** Pair-keep/rank-reuse were load-bearing on
  WR/ZN but became *harmful* once the take fired broadly — ablating both improved B4 +0.004. The
  defense is now minimal (cheapest beater + 8+ trump take). Is there *any* defense refinement left,
  or is the memoryless defense ceiling essentially "cover cheap, conserve high trumps"?
- **(jun25 b3) Memory is now perfectly inert (B3=B2, split 1.0).** The simplified defense leaves no
  memory-breakable tie, so the wired prior changes nothing. The "can memoryless compete with
  memory-counting?" question has a strong answer here: yes — B2 wins the majority vs B4 with zero
  memory. Remaining upside is on B4's residual 11% losses / 36% splits.
- **(jun25 b2) The take was the dominant lever, and the cap was hiding it.** Widening ZN's
  conservation take from `n_table==1`/rank≥10 to `any pile`/rank≥9 jumped B4 +0.037 and B1 to 0.973
  (win 0.956). The biggest waste was covering *multi-card* attacks with high trumps. Is the
  endgame-vs-conservation boundary (`deck>=5`) the next lever, or fully mapped at the deck>=5 corner?
- **(jun25 b2) B2 now wins the majority vs B4 (win 0.5215, split 0.371, loss 0.108).** The remaining
  37% splits and 11% losses — are they trump-starved defenses, or attack deals where conserving cost
  tempo? Need a per-deal breakdown (where does B2 take and then fail to convert?).
- **(jun25 b2) Are pair-keep/rank-reuse still load-bearing on the ZW base?** They were tuned on WR
  and never ablated against the broad take. Re-confirm and re-tune magnitudes (next EXPLOIT).
- **(jun25) Defense is the productive half now.** ~110 jun22 batches tuned only the attack path;
  `choose_defense` was the minimal rational base. ZN/ZW show defense card-selection lifts the ladder
  where attack micro-tweaks plateaued. How much more is there on this axis?
- **(jun25) Is there a B4-specific take trigger?** B4's own memory-take partially neutralizes the
  conservation; B1/B0 don't punish the tempo loss at all. A memoryless proxy (deck_count, opp_hand)
  for "B4 will punish this take" could squeeze more B4.
- Which local situations does B4 exploit most? **Deck==2 pair-promotion** (batch-82 ablation) — entire SD search lift; deck==1 inert; strip stays `deck==0`.
- Is the B2 weakness mostly attack choice, defense choice, take/pass threshold, or trump conservation? **Attack open/pile/strip** — defense EXPLORE batch-65–66 all neutral or catastrophic; HD strip `deck<=2` remains only strong signal.
- Are B1/B0 gains misleading relative to B4? B1/B0 rose with CZ (~0.956/0.971) but B4 delta is the keep signal.
- Does complexity reduction improve B4 parity? Still complexity 100; three timing windows, zero parameters.
- **WR keep (batch-101):** hand≥opp pile gate is the missing +0.0003 search lift over TQ ceiling; strip opp<=2 and total≤16 remain load-bearing.
- **WR ablation (batch-102):** removing hand≥opp drops to TQ level (search −0.0018); hand>opp and hand≥opp+1 catastrophic (−0.033).
- **WR ablation (batch-103):** strip opp≤2 −0.014 load-bearing; total≤16 −0.0006 mild; pile deck≤3 beats deck≤2 (−0.0006); pile opp≤4 −0.016.
- **WR mapped (batch-104):** total gate ≤16 optimal (14/15 −0.0006; 17 −0.00055); deck==2 pair −0.012 load-bearing; opp≤6 −0.0007; void pile −10 inert.
- **WR PIVOT (batch-105):** pile trump deck≤3 essential (XM deck==0 only −0.020); midgame pair min+1 −0.0016; rank-aware void inert.
- **WR PIVOT (batch-106):** pile-pass only-trump deck>0 −0.020 (same as XM); suit tie-break inert; endgame pair skip min+2 −0.0015.
- **WR PIVOT (batch-107):** ultra-endgame pass hand==1 −0.019; defense rank-match quick +0.0009 medium flat (0.79505); dual seeds stable.
- **WR PIVOT (batch-108):** softer pass hand==2 opp==1 inert; defense rank-match −2/−4 quick +0.0005.
- **WR PIVOT (batch-109):** XW −4 medium +0.00089; open trump hoard + void hand-gate inert.
- **WR PIVOT (batch-110):** YB dual agrees +0.00054 quick, medium 0.79595 reconfirms XW; YC strip opp==1 −0.015 (load-bearing opp≤2); YD midgame hand-gate −0.0005 inert.
- **WR PIVOT (batch-111):** YE pass n_table>=4 −0.016 (throw-in load-bearing); YF total≤18 −0.0006 inert (confirms ≤16 optimal).
- **WR ABLATE (batch-112):** pile trump −0.039; midgame pair −0.011; deck≤2 pair −0.012; strip −0.014; void penalty −0.0006 mild. **Stack minimal** — no simplification keep.
- **WR PIVOT (batch-113):** shortest-suit open −0.0003; pile depth / tight-beat / open pass inert. **Terminal plateau** — accept `f5bb135`.
- **Closure (batch-114):** B3 vs B2 **0.50000** (5M seeds); memory hook inert on WR stack. **Jun22 run complete.**

## Editable research directions

Next experiment ideas (**PIVOT, qualitatively new only, on QA base `8487eb7`**):

1. **Throw-in pass discipline.** When piling on, test stopping early (`AttackDone`) instead of
   dumping the lowest non-trump match — e.g. stop when the defender is card-light (`opp<=k`) so we
   don't hand them a cheap cover that fattens a hand we can't punish. jun22 tuned the trump-finish
   pile, not a non-trump early stop.
2. **Endgame-specific defense (`deck<=2`).** The conservation take is off here (deck>=5 gate), so the
   closing exchanges use the plain cheapest-beater. Test a cover-order or hold-a-cover rule for the
   endgame where B4's card counting bites hardest.
3. **Open-from-longest-suit tie-break.** Among equal-lowest non-trump opens, lead from our *longest*
   non-trump suit to deplete it. Only if it does not just re-tread the jun22 shortest-suit probe.
4. **Take vs cover when the attack itself is a trump.** Covering a trump attack burns an even higher
   trump; test a slightly more aggressive take (lower rank floor) gated to trump attacks only.
5. **Defense suit-void awareness.** When a non-trump cover would leave us void in that suit, weigh
   the future trumping value — endgame-gated to avoid the inert/ harmful generic shape result.

Rules: PIVOT one change per attempt, quick screen first; escalate medium/dual on >= +0.003 quick;
full only on the locked gate. **Do not re-open** the take window (n_table/rank/deck saturated, b2),
the defense shape tie-breaks (harmful, b3), take hand-count gates (harmful, b4), or the saturated
attack micro-axis (jun22 batches 102–113). Expect diminishing returns near the memoryless ceiling.

Rules for selecting ideas:

- Follow **`## Search mode`**: one-change in EXPLORE/PIVOT/ABLATE/EXPLOIT; two orthogonal in COMBO; grid cells in SWEEP.
- After a single-axis maybe ≥ +0.002 medium, meta must switch to **COMBO** or **SWEEP**, not more EXPLORE on the same knob.
- Prefer simplification when score is flat (ABLATE confirms load-bearing parts first).
- Prefer changes screenable by quick B4 (`triage.bat b4` or quick).
- Avoid retrying rejected directions unless a new mechanism is given.
- Do not force full eval below the locked gates; B4-first escalation rules unchanged.

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

- direction: pair-open deck>=5 / deck>=6 alone
  evidence: exp CI/CJ full B4 +0.0023/+0.0022 search +0.0015; lower_ci 0.62139/0.62130; below keep gate
  do not retry unless: new combo axis with measurable quick >= +0.003

- direction: skip endgame pair promotion
  evidence: exp CK quick −0.008 B4
  do not retry unless: —

- direction: pair deck>=5 opp>=4 / deck 5-15 / deck==5 only
  evidence: exp CM/CN/CO neutral quick
  do not retry unless: —

- direction: pile deck<=2 / pile deck<=4 / pair>=6|7 + pile<=3 vs CQ
  evidence: exp CR/CS/CT/CV quick −0.001..−0.005 vs CQ 7912e0c
  do not retry unless: —

- direction: pile deck==3 only (exact)
  evidence: exp CU quick B4 0.565 (−0.061 vs CQ)
  do not retry unless: —

- direction: pile opp<=4 + CQ combo (pile path)
  evidence: exp CW quick B4 0.606 (−0.020 vs CQ)
  do not retry unless: open-path opp tweak only (not pile)

- direction: void open -6/-7 + CQ
  evidence: exp CX/CY quick neutral vs CQ
  do not retry unless: —

- direction: pair cap min+1 + CQ
  evidence: exp DA quick −0.002 vs CQ
  do not retry unless: —

- direction: open strip opp<=1 / opp<=3 vs CZ
  evidence: exp DB/DC quick −0.012/−0.011 vs CZ; opp<=2 optimal
  do not retry unless: —

- direction: pile deck<=4 vs CZ / pair min+3 vs CZ
  evidence: exp DE −0.006; DF neutral (+0.0006 medium)
  do not retry unless: —

- direction: pile opp<=2 + CZ (pile path)
  evidence: exp DG quick −0.044 vs CZ (worse than CW opp<=4)
  do not retry unless: —

- direction: open strip >=2 trumps / pair deck>=4 + CZ
  evidence: exp DJ −0.009; DK −0.005 quick
  do not retry unless: —

- direction: void pile -9 / open strip high trump + CZ
  evidence: exp DH/DL neutral quick
  do not retry unless: —

- direction: endgame deck==0 without singleton gate
  evidence: exp DM quick +0.00005 medium +0.001 B4; below escalate/keep gates
  do not retry unless: paired with second axis showing >= +0.003 quick

- direction: skip midgame pair-open / skip endgame pair promotion on CZ
  evidence: exp DN/DO quick neutral −0.0007 (pair loop inert at quick resolution on CZ)
  do not retry unless: full ablation shows >= +0.005 B4 (unlikely)

- direction: open strip opp==1 on CZ
  evidence: exp DP quick −0.012 B4 (same class as DB opp<=1)
  do not retry unless: —

- direction: attack trump penalty +95 on CZ
  evidence: exp DQ quick neutral vs +100
  do not retry unless: —

- direction: skip pile trump dump (ablation)
  evidence: exp DR quick B4 0.578 (−0.059 vs CZ); pile deck<=3 path is load-bearing
  do not retry unless: —

- direction: skip endgame trump strip (ablation)
  evidence: exp DS quick −0.010 B4 (~full CZ gain over CQ from strip axis)
  do not retry unless: —

- direction: void open -10 / midgame pair opp>=4 / pile deck<=2 only
  evidence: exp DT/DU/DV quick neutral or −0.001
  do not retry unless: —

- direction: defense trump cost +40/+55 on CZ
  evidence: exp DW/EB quick neutral; prior BJ/BK neutral at AQ
  do not retry unless: —

- direction: void pile -10 / endgame strip before pair loop
  evidence: exp DX neutral; DY quick −0.0009
  do not retry unless: —

- direction: midgame pair deck upper bound <=12
  evidence: exp EA quick −0.003 B4
  do not retry unless: —

- direction: skip midgame pair-open (ablation)
  evidence: exp DZ medium −0.005 B4; DN quick neutral (resolution-dependent)
  do not retry unless: —

- direction: pile dump deck 1-3 / deck==3 only / no pile-on deck>=4
  evidence: exp EC −0.034; EE −0.058; EG −0.116 vs CZ; deck<=3 window load-bearing
  do not retry unless: —

- direction: endgame pair cap min+3 (narrow unbounded search)
  evidence: exp ED quick −0.005; endgame pair promotion wants wide rank search
  do not retry unless: —

- direction: defense voluntary take (table trump count)
  evidence: exp EF quick −0.025 B4
  do not retry unless: new take trigger unrelated to trump count

- direction: endgame strip-only / skip pair loop
  evidence: exp EI quick −0.009 B4; pair loop required before strip fallback
  do not retry unless: —

- direction: pile-phase trump +110 / pile highest trump dump
  evidence: exp EJ/EM neutral quick
  do not retry unless: —

- direction: midgame pair cap min+1
  evidence: exp EL quick −0.002 B4; min+2 optimal
  do not retry unless: —

- direction: throw-in table rank bonus global / deck<=3-only
  evidence: exp EN/ER neutral quick
  do not retry unless: bonus magnitude >= 12 or deck==3-only pile battles

- direction: endgame opp==1 highest non-trump open
  evidence: exp EQ quick −0.001 B4
  do not retry unless: —

- direction: pair deck>=5 or deck==3 only (exact)
  evidence: exp ES medium −0.0001; deck 1-3 window beats deck==3 alone (EO)
  do not retry unless: —

- direction: pair deck>=5 or deck==1 / deck 1+3 without 2 / deck==3 alone quick
  evidence: exp ET/EW/EV quick −0.0004..−0.0008; deck==2 is primary lift (EU)
  do not retry unless: paired as full EO 1-3 window

- direction: throw-in rank -12 deck==3 only
  evidence: exp EX neutral quick
  do not retry unless: —

- direction: deck==2 pair opp<=4/5 gate / singleton gate alone
  evidence: exp FA/FB neutral; FC +0.0006 same as EU (gate inert)
  do not retry unless: —

- direction: defense overkill rank penalty
  evidence: exp FE neutral quick
  do not retry unless: —

- direction: EO deck 1-3 full window vs FF deck 1/2
  evidence: FF medium +0.0013 beats EO +0.0012; deck==3 anti-synergizes pair extension
  do not retry unless: testing deck==3 removal only (FF axis)

- direction: PIVOT batch-25 attack timing (FG-FK)
  evidence: FG early-trump guard / FH rank-match pile / FI endgame pair cap+4 / FJ opp>=5 pile skip / FK opp==1 min open — all quick B4 0.63607 search 0.78896
  do not retry unless: new trigger geometry (not same guards/caps)

- direction: PIVOT batch-26 attack geometry (FL-FP)
  evidence: FL n_table>=4 pile pass −0.004 B4; FM-FP all quick 0.63607 neutral
  do not retry unless: —

- direction: ABLATE batch-27 simplification (FQ-FU)
  evidence: FQ void remove −0.001; FR midgame pair −0.005; FS open-only void neutral; FT endgame pair −0.010; FU pile dump −0.059 — CZ stack minimal
  do not retry unless: —

- direction: COMBO batch-28 (FV-FZ)
  evidence: FV void+pair>=6 −0.001; FW/FX/FY neutral; FZ strip opp<=3 −0.011 (reconfirms opp<=2)
  do not retry unless: new second axis with quick >= +0.003

- direction: PIVOT batch-29 suit-length / battle-state (GA-GE)
  evidence: GA longest-suit −0.001; GB-GE all quick 0.63607 neutral
  do not retry unless: —

- direction: SWEEP batch-30 attack trump penalty 92–108
  evidence: GF–GJ all b4 B4 0.63607 (−0.0007 vs full best); axis inert on CZ stack
  do not retry unless: paired with pile-phase separate penalty

- direction: COMBO batch-31 void-stripped (GK–GO)
  evidence: GK medium −0.00012; GL medium −0.00024; GM/GN neutral; GO opp==2 strip −0.002
  do not retry unless: void remove paired with new axis showing quick >= +0.003

- direction: SWEEP batch-32 void bonus grid (GP–GT)
  evidence: all b4 B4 ~0.63607; GR open5/pile6 −0.00068 best; axis inert on CZ
  do not retry unless: —

- direction: COMBO batch-33 pile/pair windows (GU–GY)
  evidence: GU pile<=2 −0.001; GV pile<=4 −0.006; GW/GX neutral; GY void+CZ medium −0.00012
  do not retry unless: new third axis with quick >= +0.003 (CZ pile<=3 pair>=5 locked)

- direction: PIVOT batch-34 endgame pressure (HA–HC)
  evidence: HA strip opp<=3 −0.011; HB pair opp<=3 −0.012; HC pile pass opp>=6 −0.0007 neutral
  do not retry unless: —

- direction: SWEEP batch-35 strip deck grid (HF–HJ)
  evidence: HH deck<=2 +0.006; HI deck<=3 +0.005 search +0.004; HG deck==1 −0.019; HJ deck<=1 opp<=1 −0.011
  do not retry unless: deck==1 or opp<=1 strip combos

- direction: EXPLOIT batch-36 strip refinements (HK–HM)
  evidence: HK deck==2 only −0.011; HL deck 1|2 −0.010; HM opp<=3 −0.005; deck==0 strip load-bearing
  do not retry unless: —

- direction: strip deck 0|2 only (HO)
  evidence: full B4 +0.0057 search +0.0039 — strictly worse than HD deck<=2 at full
  do not retry unless: combined with second axis

- direction: COMBO batch-39 pile on HD (HT–HZ)
  evidence: HT opp<=4 −0.008; HZ opp<=3 −0.021; HV/HY neutral; pile+strip no synergy
  do not retry unless: new non-pile second axis

- direction: SWEEP batch-41 pair delay on HD (IM–IQ)
  evidence: pair>=5 best (+0.0058); >=6/7/8 decline; >=4 −0.001; axis closed on HD base
  do not retry unless: new strip timing change

- direction: PIVOT batch-42 defense/pile/novel strip (IR–JA)
  evidence: all b4 flat ±0.001 except IY pile deck==0 −0.003; split pair/strip neutral
  do not retry unless: combined with HD strip as COMBO

- direction: EXPLOIT HD strip loop (batch-44 JE)
  evidence: medium search +0.0042 x3 reconfirms; full +0.00417; skip further HD unless COMBO quick >= +0.006
  do not retry unless: second axis clears +0.006 quick

- direction: PIVOT batch-45 defense rank cap (JF–JJ)
  evidence: JF–JI flat; JJ take opp<=2 deck<=1 −0.231; axis closed
  do not retry unless: —

- direction: EXPLORE batch-47 pile/hand (JK–JP)
  evidence: JK rank-match −0.079; JO hand==1 −0.026; JN hand<=3 −0.010; JP only-trump −0.010
  do not retry unless: —

- direction: PIVOT batch-48 scoring (JQ–JT)
  evidence: void/trump/pair-cap/pile-window all flat or regress; JT pile deck<=2 opp<=4 −0.018
  do not retry unless: —

- direction: PIVOT batch-49 endgame opp-hand (JW–JZ)
  evidence: JW opp==1 −0.012; JX pile deck<=1 −0.045; JY HD opp==1 −0.006; JZ −0.001
  do not retry unless: —

- direction: SWEEP batch-52 pair cap on HD (LC–LF)
  evidence: min+3 best B4 +0.0064; min+2 = HD search-best; min+4 decline; axis closed
  do not retry unless: combined with search-lift third axis

- direction: COMBO batch-53 KZ third-axis (LG–LL)
  evidence: void/pile/trump on KZ none beat HD search +0.0042; KZ B4 +0.0066 search +0.0039
  do not retry unless: mechanism lifts medium search >= +0.0045

- direction: PIVOT batch-54 open/split-strip (MA–MD)
  evidence: MA longest suit −0.031; MB soft rank-match −0.079; MC trump>=2 −0.016; MD split neutral
  do not retry unless: —

- direction: COMBO batch-56 HD second-axis (MO–MS)
  evidence: MO pair opp>=4 −0.007; MP/MQ/MR/MS tie HD +0.00577 quick; no search lift
  do not retry unless: mechanism unrelated to pile/deck/void/defense cost

- direction: legal only-trump pile pass (MT/MV)
  evidence: MT −0.059; MV −0.052 on HD base; JP only-trump −0.010 on CZ
  do not retry unless: —

- direction: PIVOT batch-57 pile pass / pair widen (MT/MX)
  evidence: MT/MV regress; MU deck 0|2 +0.0051 < HD; MX pair min+4 neutral
  do not retry unless: —

- direction: HD pile narrowing / defense take / second trump strip (NG–NK)
  evidence: NG pile deck<=1 −0.015; NH opp<=3 −0.021; NI broken; NJ ablate pile −0.052; NK second trump +0.002
  do not retry unless: —

- direction: HD pair cap tighten / strip opp==1 (NL–NP)
  evidence: NL min+1 search 0.79265; NM exact min 0.79136; NN/NO defense trump 35/65 neutral; NP opp==1 −0.006
  do not retry unless: —

- direction: ABLATE batch-60 CZ/HD simplification (NQ–NU)
  evidence: NQ pile off −0.059; NR pair off −0.005; NS void off −0.001; NT strip off −0.010; NU HD+pile off −0.052 — stack minimal
  do not retry unless: new keep candidate on different base

- direction: PIVOT batch-61 attack geometry (OA–OE)
  evidence: OA longest suit deck>=7 −0.025; OB rank-match pile −0.079; OC/OD/OE neutral or regress
  do not retry unless: rank-match with deck gate only

- direction: PIVOT batch-62–63 refinements (OF–OO)
  evidence: OF rank-match atk −0.058; OG/OK/OM/OO neutral; OL deck>=4 −0.005; ON opp<=3 −0.030
  do not retry unless: —

- direction: HD + new-suit pile bonus SWEEP (OY/PE–PG)
  evidence: −2/−3/−5/−8 all ~+0.0056 quick B4; medium search +0.00418 — ties HD, no search lift
  do not retry unless: combined with search-lifting third axis

- direction: EXPLORE batch-65–66 defense timing (PC–PM)
  evidence: PC all-trump take deck<=3 −0.553; PD skip trump vs NT −0.583; PF −0.012; PE/PG/PH–PM neutral
  do not retry unless: per-target trump conservation (not global all-trump check)

- direction: PIVOT batch-67 attack refine (PN–PR)
  evidence: PN/PQ strip opp<=3 −0.011/−0.005; PR pair opp<=4 −0.005; PP HD+pile deck<=2 +0.0055 (same as MP)
  do not retry unless: —

- direction: PIVOT batch-68–69 hand-count phase (PS–QC)
  evidence: PS hand<=3 strip −0.010; PT hand<=4 pile −0.062; PU/PW/QB neutral; PV −0.006; PZ/QA regress
  do not retry unless: hand gate AND deck gate conjunction

- direction: PIVOT batch-70 n_table (QD–QF)
  evidence: QD/QF neutral; QE pile n_table>=3 −0.050; PA-class regress
  do not retry unless: —

- direction: COMBO batch-71–72 HD search-lift (QG–QO)
  evidence: QG/QI medium search +0.0040; QH/QN tie HD +0.0058 quick; QK/OY +0.00418; triple COMBOs flat
  do not retry unless: mechanism outside void/pile/pass/new-suit/table-depth class

- direction: ABLATE batch-73 HD stack (QS–QV)
  evidence: QU pile off −0.052; QV pair-skip −0.010; QS pair −0.005; QT void off −0.001 — pile essential on HD
  do not retry unless: —

- direction: EXPLOIT batch-74–75 HD stability (RA–RE, RF–RJ)
  evidence: RA medium +0.00424 dual +0.00381 stable; RB 0|2 −0.0007 vs HD; RC deck==2 −0.011; RF additive deck==2 neutral; RJ/KZ B4 +0.0067 search +0.0040
  do not retry unless: search-lift axis outside pair-cap class

- direction: PIVOT batch-76–77 opponent-relative (RK–RT)
  evidence: RK strip opp==1 −0.012; RL pile deck<=2 opp<=2 −0.044; RM/RR hand-advantage pair −0.004; RN skip pile opp<=2 −0.008; RO strip deck<=2 opp<=1 −0.006; RP strip opp==2 −0.002; RQ pile deck<=2 opp<=3 −0.030; RS void opp<=3 −0.001; RT pile opp>=4 −0.017
  do not retry unless: conjunct with non-opp deck gate only

- direction: PIVOT batch-78 rank/deck structure (RU–RY except RW)
  evidence: RU pair deck>=4 −0.005; RV strip trump==1 only −0.060; RX void −11/−4 −0.001; RY pile hand>=3 −0.006
  do not retry unless: —

- direction: RW endgame pair deck<=1 at medium
  evidence: quick neutral; medium search +0.0004 B4 +0.0008 — below +0.003 escalate; sweep deck window before COMBO
  do not retry unless: SWEEP batch-79 finds deck cell >= +0.003 medium

- direction: SWEEP batch-79 endgame pair deck window (SA–SE except SD)
  evidence: SB deck==1 only −0.019; SC deck<=1 neutral; SE deck==2 only −0.011; SA control noise
  do not retry unless: —

- direction: HD strip deck<=2 as sole change
  evidence: SD deck<=2 pair + strip deck==0 ties HD full (B4 0.64318 search 0.79358); strip widening redundant
  do not retry unless: paired with search-lift second axis on SD base

- direction: EXPLOIT batch-80 SD COMBOs (SF–SJ)
  evidence: SF/KZ-class min+3 full B4 0.64337 search 0.79335; SG/SI flat vs SD; SH strip ablate −0.003; SJ skip deck==2 pair → neutral (deck==2 is lift)
  do not retry unless: search-lift axis outside pair-cap/pile/void-on-SD class

- direction: PIVOT batch-81 SD search-lift (SK–SO)
  evidence: SK midgame pair-off +0.002 search; SL void remove medium ties SD full search, full +0.0041; SM pile pass +0.003; SN endgame cap min+1 −0.011; SO pile off −0.052
  do not retry unless: —

- direction: ABLATE batch-82 SD stack (SP–ST, SU–SV)
  evidence: SP deck==2 pair off → CZ neutral; SQ deck==1 off = SD; SR midgame +0.002; SS strip −0.003; ST pile −0.052; SU deck==2 only +0.0004; SV additive +0.0035
  do not retry unless: —

- direction: EXPLOIT batch-83 deck==2 pair refinements (SW–TB)
  evidence: SX/SZ tie SD; SY/TB opp gates → CZ neutral; SW SV medium +0.0039 < SD +0.0042
  do not retry unless: —

- direction: PIVOT batch-84 deck window (TC–TG)
  evidence: TC deck<=3 +0.0031; TD deck==3 −0.001; TE 1|2 = SD; TF 2|3 +0.0028; TG midgame +0.002
  do not retry unless: —

- direction: PIVOT batch-85 SD triggers (TH–TL)
  evidence: TH total<=10 → CZ neutral; TI/TJ inert (=SD); TK pile<=2 +0.0036; TL strip trump>=2 −0.015
  do not retry unless: total-cards SWEEP batch-86

- direction: SWEEP batch-86 total threshold (TM–TQ)
  evidence: TM total>10 = SD; TN/TO neutral; TP +0.0038; TQ medium +0.0044 full +0.0043 — best unkept; lift needs total>10
  do not retry unless: EXPLOIT fine sweep 14–18 on TQ peak

- direction: EXPLOIT batch-87 fine total threshold (TR–TV)
  evidence: TR/TR medium 0.79373; TS/TQ medium 0.79376 tie; TT +0.0038; TU flat; TV dual agrees
  do not retry unless: —

- direction: COMBO batch-88 TQ second-axis (TW–UA)
  evidence: TW full B4 0.64351 search 0.79345; TX/TY flat; TZ +0.002; UA = TS; all below TQ medium 0.79376
  do not retry unless: —

- direction: ABLATE batch-89 TQ stack (UB–UG)
  evidence: UB=SD 0.79322; UC=CZ 0.78896; UE/UD=TQ 0.79329; UF split 0.79294; UH medium 0.79376 reconfirm
  do not retry unless: —

- direction: PIVOT batch-90 throw-in/pass (UI–UM)
  evidence: UI/UK/UL neutral; UJ sole-trump pass −0.012; UM n_table>=5 take −0.0026
  do not retry unless: —

- direction: EXPLORE batch-91 rank/ordering (UN–UR)
  evidence: UN/UO/UQ neutral; UP −0.00015; UR throw-in cap −0.019
  do not retry unless: —

- direction: PIVOT batch-92 trump/hand guards (UX–VB)
  evidence: UX/UY/UZ/VA regress −0.008..−0.019; VB deck>=6 pair neutral; trumps>=1 essential
  do not retry unless: —

- direction: SWEEP batch-93 pile opp threshold (VC–VG)
  evidence: opp<=5 optimum; opp<=4 −0.016; opp<=3 −0.022; opp>=6 −0.0014; deck<=2 −0.00065
  do not retry unless: —

- direction: PIVOT batch-94 rank-match/table-depth (VH–VL)
  evidence: VH/VI/VK/VL neutral; VJ n_table>=4 pass −0.014
  do not retry unless: —

- direction: n_table early pile pass (VJ–VP batch-94/95)
  evidence: n_table>=2 −0.060; >=3 −0.025; >=4 −0.014; >=5 −0.0023; throw-in depth essential
  do not retry unless: —

- direction: COMBO batch-96 TQ second-axis (VQ–VT)
  evidence: VQ ties TQ 0.79376; VR −0.011; VS 0.79371; VT −0.010; VU dual stable
  do not retry unless: new axis outside pile/strip/midgame on TQ

- direction: EXPLOIT batch-97 TQ deck>=6 x total gate (VV–VY)
  evidence: VY/VW medium 0.79371; VV/VX 0.79368; all below TQ 0.79376
  do not retry unless: —

- direction: PIVOT batch-98 defense/priors (WA–WE)
  evidence: WA rank cap −0.047; WE take threshold −0.311; WB/WD/WC neutral
  do not retry unless: new mechanism unrelated to take/cap

- direction: EXPLORE batch-99 CZ micro-tweaks (WF–WJ)
  evidence: WF/WG/WJ neutral; WH opp<=4 −0.016; WI trumps>=2 −0.011
  do not retry unless: —

- direction: PIVOT batch-100 trump hoard / void timing / pile deck (WL–WO)
  evidence: WL +200 open trump penalty neutral; WM void deck<=4 neutral; WO pile deck<=1 −0.019; WP rank-match ties TQ 0.79376
  do not retry unless: —

- direction: PIVOT batch-101 strip opp==1 / n_table pass / total gate (WQ/WS/WT/WU)
  evidence: WQ strip opp==1 −0.010; WS n_table>=3 −0.027; WT/WU total≤14/≤18 ≤ TQ 0.79376
  do not retry unless: —

- direction: EXPLOIT batch-102 WR hand gate SWEEP / COMBO (WX–XB)
  evidence: WX ablate −0.0018 (TQ level); WZ/XA hand>opp/+1 −0.033; WY rank-match −0.00055; XB deck>=6 −0.00056
  do not retry unless: —

- direction: EXPLOIT batch-103 WR finish-window / ablate (XC–XF)
  evidence: XD strip off −0.014; XE opp<=4 −0.016; XC total gate −0.0006; XF deck<=2 pile −0.0006
  do not retry unless: —

- direction: EXPLOIT/SWEEP batch-104 WR total gate / deck pair / opp (XG–XL)
  evidence: XG/XH total≤14/15 −0.0006; XI ≤17 −0.00055; XJ deck==0 only −0.012; XK void inert; XL opp<=6 −0.0007
  do not retry unless: —

- direction: PIVOT batch-105 WR pile-trump defer / pair shift / rank void (XM–XO)
  evidence: XM pile trump deck==0 only −0.020; XN pair min+1 −0.0016; XO rank-aware void inert
  do not retry unless: —

- direction: PIVOT batch-106 pile-pass / suit tie / pair skip (XP–XR)
  evidence: XP pile-pass only-trump −0.020 (=XM); XQ suit tie inert; XR pair skip min+2 −0.0015
  do not retry unless: —

- direction: PIVOT batch-107 ultra-endgame pass (XS)
  evidence: XS hand==1 deck==0 pass −0.019; XT defense rank-match medium 0.79505 flat vs WR
  do not retry unless: softer trigger (hand==2 opp==1)

- direction: SWEEP batch-108 defense rank-match bonus (XV–XX) + XY softer pass
  evidence: XV/XW quick +0.0005; XT/−3 medium flat; XX −6 regress; XY inert
  do not retry unless: —

- direction: PIVOT batch-109 open trump hoard / pile void gate (XZ/YA)
  evidence: XZ deck>=4 trumps>=3 +5 penalty inert; YA void hand-gate inert
  do not retry unless: —

- direction: COMBO WR+defense rank-match -4 (YB/XW)
  evidence: dual +0.00054 both seeds; medium 0.79595 reconfirmed; below keep bar and full gate
  do not retry unless: new defense mechanism unrelated to rank-match bonus

- direction: PIVOT batch-110 strip opp==1 / midgame hand-gate on WR (YC/YD)
  evidence: YC strip opp==1 −0.015 (opp<=2 load-bearing); YD midgame hand>=opp −0.0005 inert
  do not retry unless: —

- direction: PIVOT batch-111 throw-in pass / total gate widen (YE/YF)
  evidence: YE n_table>=4 −0.016; YF total<=18 −0.0006 inert (<=16 optimal)
  do not retry unless: —

- direction: ABLATE batch-112 WR stack decomposition (YG–YK)
  evidence: pile trump −0.039; midgame pair −0.011; deck<=2 pair −0.012; strip −0.014; void −0.0006 mild
  do not retry unless: —

- direction: PIVOT batch-113 new mechanism class (YL–YO)
  evidence: shortest-suit −0.0003; pile depth / tight-beat / open pass inert at quick
  do not retry unless: qualitatively different local feature hypothesis

- direction: (jun25) defense 3rd shape signal — void-suit bonus / keep-lowest-opener on ZC
  evidence: exp ZG void-suit −2 inert (+0.0002 vs ZC); ZH keep-opener +3 −0.001 quick
  do not retry unless: a different shape signal (not suit-void or opener-keep)

- direction: (jun25) high-trump conservation take — rank/deck extremes
  evidence: exp ZO take any-trump deck>=5 −0.022 search (low trumps must cover lone attacks); ZP
  rank>=3 −0.0001 search / −0.0019 B4 vs rank>=4; ZQ deck>=4 ties deck>=5 with lower B4
  do not retry unless: paired with n_table widen or a B4-specific trigger

- direction: (jun25) defense rank-reuse / pair-keep magnitude beyond the optimum
  evidence: exp ZD rank-reuse −6 worse than −4; ZE pair-keep +6 worse than +4 (both seed-0 quick)
  do not retry unless: re-tuned jointly on the ZN base at medium

- direction: (jun25 b2) high-trump conservation take window — n_table / rank / deck cells
  evidence: REOPENED the b1 take rejection via "n_table widen" → ZW keep. Sweep then closed it:
  n_table cap is monotone (==1<<=2<<=3<<=4<no-cap, each + search) so no-cap wins; rank floor peak
  at >=3 (rank>=2 flat search +loss, rank>=4 −0.003); deck>=5 optimal (deck>=4 −0.006, deck>=6
  −0.0006). Kept corner = no-cap / rank>=3 / deck>=5. NOTE: after b3 dropped the shape signals the
  rank floor re-tuned to >=2 (8+); deck>=5 still firm (deck>=4 −0.024). Take window now fully closed.
  do not retry unless: a 2nd conditioning feature (B4-take proxy), not n_table/rank/deck alone

- direction: (jun25 b3) defense shape tie-breaks (pair-keep, rank-reuse) — KEEP THEM
  evidence: load-bearing on WR/ZN but net-HARMFUL under the broad take. Ablating rank-reuse off
  +0.0015 search; ablating both off +0.0023q / +0.0029 full search, +0.0041 B4 (QA keep `8487eb7`).
  The take changes which card is "cheapest", so the shape biases mis-route it. Magnitudes also flat
  (rank-reuse −5 +0.0006, −6 −0.0003; both seed-0).
  do not retry unless: a fundamentally different defense surface (not cost tie-breaks on the beater)

- direction: (jun25 b3) defense rank-reuse / pair-keep magnitude re-tune on ZW base
  evidence: R5 (−5) +0.0006 search, R6 (−6) −0.0003 — flat noise; superseded by the ablation that
  removed both signals entirely (QA).
  do not retry unless: —

- direction: (jun25 b4) gating the conservation take on hand/opp counts
  evidence: SA take only when hand<=opp −0.038 search (take helps most when card-heavy); SD take only
  when opp_hand>=4 −0.020 search (hurts B1/B0). The take is a hard unconditional optimum.
  do not retry unless: a fundamentally different conditioning signal, not a hand-count gate

- direction: (jun25 b4) attack-side pile/throw-in pair-keep (mirror of defense pair-keep)
  evidence: SB/SC +2/+4 tie-break: +0.0009 quick but +0.0001 medium = noise; adds a sub-rule. Inert.
  do not retry unless: —

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

```text
date/window: jun22 batch-10 (CI–CO)
- attempts: 2 full discards (CI CD +0.0023, CJ BY +0.0022), 1 regression CK −0.008, 3 neutral; 0 keeps
- bottleneck: pair-delay best real signal since AQ but full eval still −0.003 short of keep gate on search
- what changed: closed pair-delay at full; endgame pair promotion required; CD deck>=5 wins tie-break
- result: d5bca3c B4 0.61938 search 0.77742 unchanged
- next bias: need qualitatively new axis; pair-delay alone insufficient for keep
```

```text
date/window: jun22 batch-11 (CP–CQ)
- attempts: 1 discard CP (+0.002 quick), 1 keep CQ full; escalated quick→medium→dual→full
- bottleneck: single-axis pair-delay capped at +0.0023; pile deck<=3 combo unlocks +0.007 B4
- what changed: exp CQ committed 7912e0c; B3vsB2 0.500 confirmed
- result: B4 0.62635 search 0.78125 (+0.007 B4 vs AQ); W/L/S win 0.392 loss 0.106 split 0.502
- next bias: refine pile deck window around 3; hold pair deck>=5; avoid defense axes
```

```text
date/window: jun22 batch-12 (CR–CV)
- attempts: 5 discards (1 regression CU pile==3 −0.061, 4 mild vs CQ); 0 full evals; 0 keeps
- bottleneck: CQ combo local optimum — pile<=3 beats <=2/4; pair>=5 beats >=6/7 on quick
- what changed: analysis.ipynb nbformat fixed; charts refreshed (progress/occam/score_alignment)
- result: 7912e0c B4 0.62635 search 0.78125 unchanged
- next bias: hold CQ; test pile opp narrow + CQ; avoid exact deck windows
```

```text
date/window: jun22 batch-13 (CW–DA)
- attempts: 3 discards (CW −0.020, CX/CY/DA mild), 1 keep CZ full; escalated on +0.010 B4 quick
- bottleneck: open strip opp<=2 synergizes with CQ; pile opp<=4 anti-synergy; void neutral
- what changed: exp CZ committed 167b02d; B3vsB2 0.500; split 0.481 win 0.418
- result: B4 0.63676 search 0.78941 (+0.010 B4 vs CQ)
- next bias: tighten open strip opp<=1 cautiously; hold pile deck<=3 pair>=5
```

```text
date/window: jun22 batch-14 (DB–DF)
- attempts: 5 discards (2 regressions DB/DC open opp, 2 mild DD/DE, 1 neutral DF); 0 full evals; 0 keeps
- bottleneck: CZ local optimum — open strip opp<=2 sharp; pile<=3 beats <=2/4; pair min+3 flat
- what changed: closed open opp sweep around 2; pile deck sweep around 3 at CZ baseline
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: hold CZ stack; need new axis for next keep (+0.005 gate)
```

```text
date/window: jun22 batch-15 (DG–DL)
- attempts: 5 discards (1 regression DG −0.044, 2 mild DJ/DK, 2 neutral DH/DL); 0 full evals; 0 keeps
- bottleneck: CZ fully saturated — pile opp narrow anti-synergizes; void/strip rank neutral
- what changed: closed pile opp<=2 on pile path; strip trump count; pair deck>=4 on CZ
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: hold CZ; no pile opp tweaks; need qualitatively new mechanism
```

```text
date/window: jun22 batch-16 (DM–DQ)
- attempts: 5 discards (1 regression DP −0.012, 1 maybe DM +0.001 medium, 3 neutral); 0 full evals; 0 keeps
- bottleneck: CZ simplifications inert at quick; singleton gate not binding; strip opp==1 re-confirms opp<=2
- what changed: closed endgame singleton / pair-skip / trump+95 axes on CZ; DM medium +0.001 below gate
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: CZ component ablations (pile dump vs endgame strip); void open pressure; midgame opp gate
```

```text
date/window: jun22 batch-17 (DR–DV)
- attempts: 5 discards (2 regressions DR −0.059 / DS −0.010 ablations, 3 neutral); 0 full evals; 0 keeps
- bottleneck: pile dump + endgame strip are load-bearing; micro void/pair/pile-window knobs flat
- what changed: ablation map — CQ combo value mostly pile path; CZ delta mostly endgame strip
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: defense trump cost; endgame strip reorder; pile void -10; confirm midgame pair inert at medium
```

```text
date/window: jun22 batch-18 (DW–EB)
- attempts: 6 discards (2 mild EA −0.003 / DY −0.001, 1 medium DZ −0.005, 3 neutral); 0 full evals; 0 keeps
- bottleneck: defense/void knobs inert; strip-before-pair and pair upper-bound hurt slightly; midgame pair load-bearing at medium
- what changed: closed defense cost +40/+55 and void pile -10; confirmed DZ ablation vs DN quick neutral
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: refine load-bearing path ordering/windows; attackDone early-trump guard; endgame-only pair cap
```

```text
date/window: jun22 batch-19 (EC–EH)
- attempts: 6 discards (4 regressions EC/EE/EF/EG, 1 mild ED −0.005, 1 neutral EH); 0 full evals; 0 keeps
- bottleneck: CZ path geometry locked — deck<=3 pile, deck>=4 pile-ons, unbounded endgame pair, no defense take heuristics
- what changed: closed pile window narrowing, endgame pair cap, defense trump-table take, deck>=4 AttackDone guard
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: attack-phase novelties only; DM-class strip timing at medium; simplification ablation strip-only endgame
```

```text
date/window: jun22 batch-20 (EI–EM)
- attempts: 5 discards (1 regression EI −0.009, 1 mild EL −0.002, 1 medium EK +0.001, 2 neutral); 0 full evals; 0 keeps
- bottleneck: endgame pair loop load-bearing; singleton gate DM +0.001 below gate; no pile-trump-rank lever
- what changed: closed strip-only simplification, pile trump penalty/rank, midgame min+1 cap, DM medium reconfirm
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: cross-rank combo or throw-in rank-matching; hold CZ stack; no further single-knob sweeps
```

```text
date/window: jun22 batch-21 (EN–ES)
- attempts: 6 discards (1 mild EQ −0.001, 1 maybe EO +0.0012 medium, 4 neutral); 0 full evals; 0 keeps
- bottleneck: first combo signal since CZ — pair-open on deck 1-3 synergizes with pile window but below +0.003 escalate
- what changed: closed global throw-in rank match and opp==1 open; EO dual agrees at +0.0008 B4
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: sweep deck==1/2/3 pair extension components; medium/full only if >= +0.003 B4
```

```text
date/window: jun22 batch-22 (ET–EX)
- attempts: 5 discards (1 maybe EU +0.0011 medium, 4 neutral/mild); 0 full evals; 0 keeps
- bottleneck: EO lift driven mainly by deck==2 pair extension (+0.0011 medium); deck==1/3 alone hurt; full 1-3 window still best (+0.0012)
- what changed: decomposed EO combo — deck==2 ≈ 90% of EO signal; throw-in rank -12 deck==3 inert
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: dual on EU/EO; deck==2 gated combos; full only if dual >= +0.003 B4
```

```text
date/window: jun22 batch-23 (EY–EZ)
- attempts: 2 discards (dual reconfirm EU/EO); 0 full evals; 0 keeps
- bottleneck: dual agrees but both below +0.003 escalate — EU +0.0006 quick / +0.0011 medium; EO +0.0008 dual / +0.0012 medium
- what changed: closed dual escalation path for EO-class until new combo axis
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: deck==2 gated pair (opp/singleton); or accept EO plateau and hunt new mechanism
```

```text
date/window: jun22 batch-24 (FA–FF)
- attempts: 6 discards (1 maybe FF +0.0013 medium best EO-class, 5 neutral/mild); 0 full evals; 0 keeps
- bottleneck: deck==3 anti-synergy in pair extension — FF (deck 1/2) beats EO (deck 1-3); still below +0.003 gate
- what changed: closed opp/singleton gates on deck==2; defense overkill neutral; FF new best maybe +0.0013 medium
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: refine FF deck 1/2 window; dual FF; hunt qualitatively new mechanism beyond pair extension
```

```text
date/window: jun22 meta-protocol (adaptive cadence + search modes)
- attempts: n/a (control-plane update)
- bottleneck: fixed 5+1 cadence + EXPLORE-only rule kept agent on CZ plateau (batch 3–24); keeps required COMBO
- what changed: adaptive meta triggers; Search modes (EXPLORE/COMBO/SWEEP/ABLATE/PIVOT/EXPLOIT); sweep batches; PIVOT directions for batch 25+
- result: best unchanged 167b02d B4 0.63676 search 0.78941
- next bias: PIVOT — early-trump guard, throw-in rank match, endgame-only caps; no pair-extension micro-tweaks
```

```text
date/window: jun22 batch-25 (FG–FK) PIVOT
- attempts: 5 discards (all neutral at quick); 0 full evals; 0 keeps
- bottleneck: first PIVOT batch invisible at 100k — all B4 0.63607 search 0.78896; build.bat fast blocked by web_server.exe lock
- what changed: build.bat fast builds simulate target only; adaptive cadence + search modes committed; results.tsv re-init
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: PIVOT batch-26 — table-depth pile pass, opp-gated pair-open, rank cap throw-in, open-only void bonus, desperate trump open
```

```text
date/window: jun22 batch-26 (FL–FP) PIVOT
- attempts: 5 discards (1 mild regression FL −0.004, 4 neutral); 0 full evals; 0 keeps
- bottleneck: second PIVOT batch flat — attack geometry changes invisible at quick except over-piling hurts
- what changed: none on best; search mode → ABLATE for batch 27
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: ABLATE batch — remove void/pair/pile/strip components one at a time; look for simplification wins
```

```text
date/window: jun22 batch-27 (FQ–FU) ABLATE
- attempts: 5 discards (3 regressions FR/FT/FU confirm load-bearing; FQ/FS mild/neutral); 0 full evals; 0 keeps
- bottleneck: plateau trigger (batches 25-27 zero keeps); CZ stack is minimal — no simplification win
- what changed: ablation map refreshed at quick — pile −0.059 / endgame pair −0.010 / midgame pair −0.005 / void −0.001
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: COMBO batch-28 — void-stripped base + timing tweak; or rank-match open combo
```

```text
date/window: jun22 batch-28 (FV–FZ) COMBO
- attempts: 5 discards (1 regression FZ −0.011, 4 neutral/mild); 0 full evals; 0 keeps
- bottleneck: 4th zero-keep batch; COMBO void/strip/pile combos flat — CZ windows locked
- what changed: FZ reconfirms open strip opp<=2 optimal vs <=3
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: PIVOT batch-29 — suit-length sort keys, table-trump pile gate, relative pressure
```

```text
date/window: jun22 batch-29 (GA–GE) PIVOT
- attempts: 5 discards (all neutral/mild); 0 full evals; 0 keeps
- bottleneck: 5th zero-keep batch (25–29); suit-length and battle-state triggers invisible at quick
- what changed: none on best
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: SWEEP batch-30 attack trump penalty 92–108 via b4 gate
```

```text
date/window: jun22 batch-30 (GF–GJ) SWEEP
- attempts: 5 discards (trump penalty 92/96/100/104/108); 0 full evals; 0 keeps
- bottleneck: 6th zero-keep batch; trump penalty axis flat on b4 gate — all 0.63607
- what changed: closed attack trump penalty sweep on CZ stack
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: COMBO batch-31 void-stripped + timing; void/pile bonus knobs
```

```text
date/window: jun22 batch-31 (GK–GO) COMBO
- attempts: 7 rows (GK medium, GL medium); 5 discards; 0 full evals; 0 keeps
- bottleneck: 7th zero-keep batch; void remove medium −0.00012 best — no simplification keep
- what changed: GK/GL medium reconfirm void-stripped sub-gate; GO opp==2 strip −0.002
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: SWEEP batch-32 void bonus open/pile grid via b4
```

```text
date/window: jun22 batch-32 (GP–GT) SWEEP
- attempts: 5 discards (void bonus grid); 0 full evals; 0 keeps
- bottleneck: 8th zero-keep batch; void open/pile bonuses inert on b4 — all ~0.63607
- what changed: closed void bonus sweep; GR open5/pile6 −0.00068 best cell
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: COMBO batch-33 CQ-class pile/pair window replay
```

```text
date/window: jun22 batch-33 (GU–GY) COMBO
- attempts: 6 discards (1 regression GV −0.006, 4 neutral/mild, GY medium); 0 full evals; 0 keeps
- bottleneck: 9th zero-keep batch; CZ pile<=3 + pair>=5 confirmed optimal vs <=2/<=4/<=6
- what changed: closed CQ-class window replay; GV pile<=4 strong regression
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: PIVOT batch-34 endgame pressure triggers (not pile/pair windows)
```

```text
date/window: jun22 batch-34 (HA–HD) PIVOT
- attempts: 4 b4 + HD medium/dual/full; 0 keeps
- bottleneck: 10th zero-keep batch broken by HD maybe — strip deck<=2 full B4 +0.006 search +0.004 below +0.005 keep bar
- what changed: HA/HB regress −0.011/−0.012; HC neutral; HD best signal since CZ at B4 but sub-gate on search
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: SWEEP batch-35 strip deck threshold grid
```

```text
date/window: jun22 batch-35 (HF–HJ) SWEEP
- attempts: 5 b4 + HI medium; 0 keeps; 1 prior full (HD=HH)
- bottleneck: strip deck<=2 best (+0.006 B4) but full search +0.004 below keep bar; deck==1 −0.019
- what changed: closed strip deck grid; HH optimal; HI <=3 slightly worse on search
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: EXPLOIT batch-36 refine deck<=2 strip (==2, 1|2, opp widen)
```

```text
date/window: jun22 batch-36 (HK–HM) EXPLOIT
- attempts: 3 b4 discards; 0 keeps
- bottleneck: refinements all regress — deck==0 strip required; deck==2 alone −0.011; opp<=3 −0.005
- what changed: closed EXPLOIT window grid on strip deck/opp; HD deck<=2 remains best cell
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: HO deck 0|2 test + COMBO batch-38
```

```text
date/window: jun22 batch-37 (HO) EXPLOIT follow-up
- attempts: 1 b4 + medium + full; 0 keeps
- bottleneck: HO deck 0|2 full B4 +0.0057 search +0.0039 — below HD deck<=2 (+0.0064/+0.0042)
- what changed: deck==1 in <=2 is mild drag; deck==0+2 without 1 slightly worse than full <=2
- result: 167b02d B4 0.63676 search 0.78941 unchanged; HD remains top sub-gate
- next bias: COMBO batch-38 hold deck<=2 strip + orthogonal axis
```

```text
date/window: jun22 batch-38 (HP–HS) COMBO
- attempts: 4 b4 + HR medium/full; 0 keeps
- bottleneck: HR deck<=2+pair>=6 full B4 +0.0063 search +0.0041 — still 0.0009 below keep bar; HS opp<=1 −0.006
- what changed: void/pile/pair COMBOs all ~HD level; no synergy beat single-axis HD
- result: 167b02d B4 0.63676 search 0.78941 unchanged; HD remains top probe
- next bias: COMBO batch-39 deck<=2 + pile widen synergy
```

```text
date/window: jun22 batch-39 (HT–IE) COMBO
- attempts: 5 b4 + HU dual + IE medium; 0 keeps
- bottleneck: pile COMBOs regress (HT −0.008, HZ −0.021); HV/HY neutral; HD dual +0.0058 both seeds
- what changed: closed pile+strip COMBO axis; IE additive deck==2 = HO class (+0.0051)
- result: 167b02d B4 0.63676 search 0.78941 unchanged; HD single-axis still top probe
- next bias: ABLATE batch-40 HD strip component map
```

```text
date/window: jun22 batch-40 (IF–IL) ABLATE
- attempts: 6 b4; 0 keeps
- bottleneck: HD strip +0.006 vs CQ; pile −0.052 on HD base; IH pair>=6 best quick +0.0057 (HR class)
- what changed: deck==1 mild +0.0007 vs 0|2; pair delay >=6 helps on HD base (opposite CZ-alone ablation)
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: SWEEP batch-41 pair delay grid on HD base
```

```text
date/window: jun22 batch-41 (IM–IQ) SWEEP
- attempts: 5 b4 discards; 0 keeps
- bottleneck: HD pair>=5 best (+0.0058 quick); pair delay >=6 monotonic decline — axis closed
- what changed: confirmed IH/HR pair>=6 was false lead vs HD alone at quick
- result: 167b02d B4 0.63676 search 0.78941 unchanged; HD remains top probe
- next bias: PIVOT batch-42 new mechanisms (strip/pair/pile exhausted)
```

```text
date/window: jun22 batch-42 (IR–JA) PIVOT
- attempts: 9 b4 (1 medium JA neutral); 0 keeps
- bottleneck: 16+ zero-keep batches; defense/pile/novel-strip all flat; HD still only +0.006 B4 sub-gate
- what changed: closed defense take, pile deck==0, high-trump deck==1, n_table pile cap, split pair/strip
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: COMBO batch-43 HD + ladder boost hunt
```

```text
date/window: jun22 batch-43 (HD/JB–JD) COMBO
- attempts: dual + 3 b4 + HD medium; 0 keeps
- bottleneck: HD stable sub-gate; JB/JD ~HD; JC pile deck<=5 −0.0004; search gap ~0.0008 below keep bar
- what changed: closed HD COMBO hunt; dual agrees +0.0058
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: EXPLOIT batch-44 HD final pass or axis pivot
```

```text
date/window: jun22 batch-44 (JE) EXPLOIT
- attempts: 1 medium; 0 full (search +0.0042 < +0.0045 variance threshold); 0 keeps
- bottleneck: HD sub-gate stable; closed HD EXPLOIT loop per plan
- what changed: JE medium B4 0.64323 search 0.79365 matches prior HD full class
- result: 167b02d B4 0.63676 search 0.78941 unchanged
- next bias: PIVOT batch-45 defense rank cap
```

```text
date/window: jun22 batch-45 (JF–JJ) PIVOT
- attempts: 5 b4; 0 keeps; 1 regression JJ −0.231
- bottleneck: defense rank cap / trump cost / take thresholds all flat on CZ
- what changed: closed defense rank-cap axis; JJ voluntary take catastrophic
- result: 167b02d unchanged; HD remains archived top probe
- next bias: EXPLORE batch-46 attack pile/hand pressure
```

```text
date/window: jun22 batch-46 (JL–JM) EXPLORE
- attempts: 3 b4 (JK broken skip); 0 keeps
- bottleneck: JL hand<=4 pair −0.012; JM strip opp==1 −0.006; no beat HD
- what changed: hand-pressure explore regress; pivot off HD re-runs
- result: 167b02d unchanged
- next bias: EXPLORE batch-47 pile rank-match + hand pressure
```

```text
date/window: jun22 batch-47 (JK–JP) EXPLORE
- attempts: 4 b4; 0 keeps; JK −0.079 strong regression
- bottleneck: pile rank-match catastrophic; hand-pressure all regress
- what changed: closed pile rank-match and hand-size pass axes
- result: 167b02d unchanged; HD archived top probe
- next bias: PIVOT batch-48 scoring micro-tweaks
```

```text
date/window: jun22 batch-48 (JQ–JT) PIVOT
- attempts: 4 b4; 0 keeps; JT pile window −0.018
- bottleneck: void/trump/pair-cap flat; no new signal
- what changed: closed scoring micro-tweak axis; JV HD+defense neutral
- result: 167b02d unchanged
- next bias: PIVOT batch-49 endgame opp-hand triggers
```

```text
date/window: jun22 batch-49 (JW–JZ) PIVOT
- attempts: 4 b4; 0 keeps; JX −0.045 regression
- bottleneck: opp==1 strip/pile all worse than opp<=2 CZ/HD class
- what changed: closed endgame opp-hand trigger axis
- result: 167b02d unchanged; HD archived top probe
- next bias: COMBO/ABLATE batch-50 simplification vs HD COMBO
```

```text
date/window: jun22 batch-50 (KA–KF) ABLATE/COMBO
- attempts: 4 CZ ablations + KE medium + KF HD full + KR/KS/KU; 0 keeps
- bottleneck: ablation map refreshed; HD full search +0.00417 x2; gap ~0.00083 to keep bar
- what changed: KD pile −0.059 KC strip −0.010 KB pair −0.005 KA void −0.001; KE/KS no beat HD
- result: 167b02d unchanged; HD remains archived top probe (one-line CZ delta)
- next bias: COMBO batch-51 HD structural synergy only if quick >= +0.006
```

```text
date/window: jun22 batch-51 (KV–KZ) COMBO
- attempts: 5 b4 + KZ medium/dual/full + LB ablate; 0 keeps
- bottleneck: KZ HD+pair min+3 full B4 +0.0066 but search +0.0039 (HD alone +0.0042 still closer to keep bar)
- what changed: pair cap min+3 alone neutral; synergy with HD strip lifts B4 not search; KW pair deck<=2 −0.014
- result: 167b02d unchanged; KZ new top B4 probe, HD top search probe
- next bias: SWEEP batch-52 pair cap grid on HD base
```

```text
date/window: jun22 batch-52 (LC–LF) SWEEP
- attempts: 4 b4 + LE medium; 0 keeps
- bottleneck: pair cap min+3 best B4 (+0.0064 quick); min+4 declines; HD min+2 still best search medium (+0.0042)
- what changed: closed pair cap grid on HD; B4 vs search tradeoff (KZ vs HD)
- result: 167b02d unchanged
- next bias: COMBO batch-53 search lift on KZ/HD stack
```

```text
date/window: jun22 batch-53 (LG–LL) COMBO
- attempts: 5 b4 + LG medium + HD dual/medium + LP; 0 keeps
- bottleneck: KZ third-axis (void/pile/trump) none beat HD search; HD medium +0.0042 best keep proximity
- what changed: closed KZ search-lift COMBOs; KZ B4-optimal (+0.0066 full), HD search-optimal (+0.0042)
- result: 167b02d unchanged
- next bias: EXPLOIT HD keep candidate or PIVOT new axis
```

```text
date/window: jun22 batch-54 (MA–LO) EXPLOIT/PIVOT
- attempts: 4 b4 + HD medium + LM prior; 0 keeps
- bottleneck: HD search +0.0042 stable ~0.0008 below keep bar; all new pivots regress
- what changed: closed open longest suit, soft rank-match, split-strip, trump>=2 strip gates
- result: 167b02d unchanged; HD remains archived keep candidate
- next bias: PIVOT batch-55 fresh axes (defense table-size, legal pile pass)
```

```text
date/window: jun22 batch-55 (ME–MH) PIVOT
- attempts: 4 b4; 0 keeps; MG −0.059 (pile trump pass = pile dump off class)
- bottleneck: 31+ zero-keep batches; no axis beats HD sub-gate
- what changed: closed hand==1 open, n_table defense cost, legal pile pass, table trump take
- result: 167b02d unchanged
- next bias: meta plateau review; HD archived as manual keep candidate pending search lift
```

```text
date/window: jun22 batch-56 (MO–MS) COMBO
- attempts: 5 b4 + HD medium control; 0 keeps
- bottleneck: HD second-axis (pair opp>=4, pile deck<=2, defend cost, void, high-trump) none beat HD search +0.0042
- what changed: closed HD COMBO second-axis sweep; MO pair-delay −0.007
- result: 167b02d unchanged; HD remains search-optimal probe
- next bias: PIVOT legal pile pass + fresh axes batch-57
```

```text
date/window: jun22 batch-57 (MT–MX) PIVOT/COMBO
- attempts: 5 b4 + MW medium; 0 keeps
- bottleneck: only-trump pile pass −0.059; KZ (MW) B4 +0.0064 search +0.00397 — still below keep bar
- what changed: closed legal trump-only pile pass; MU deck 0|2 worse than HD <=2
- result: 167b02d unchanged
- next bias: HD refinement batch-58
```

```text
date/window: jun22 batch-58 (NG–NK) COMBO/ABLATE
- attempts: 5 b4; 0 keeps; all regress or flat vs HD
- bottleneck: pile narrowing and defense take on HD base all hurt B4; second-lowest trump strip +0.002 only
- what changed: closed HD pile opp/deck narrowing and trump-rank strip variants
- result: 167b02d unchanged
- next bias: pair cap / defense sweep batch-59
```

```text
date/window: jun22 batch-59 (NL–NP) SWEEP/PIVOT
- attempts: 5 quick; 0 keeps
- bottleneck: HD pair tighten and strip opp==1 all below HD; defense trump penalty 35/65 neutral
- what changed: closed HD pair cap tighten and opp==1 strip gate
- result: 167b02d unchanged
- next bias: ABLATE batch-60 confirm stack minimal
```

```text
date/window: jun22 batch-60 (NQ–NU) ABLATE
- attempts: 5 quick; 0 keeps
- bottleneck: 35+ zero-keep batches; ablations match batch-50 map — CZ stack is load-bearing minimum
- what changed: confirmed pile −0.059, strip −0.010, pair −0.005, void −0.001; HD without pile −0.052
- result: 167b02d unchanged; HD ~0.0008 below search keep bar is structural not fixable by second-axis COMBO
- next bias: PIVOT batch-61 attack geometry (longest suit deck>=7, rank-match pile, table-depth pass)
```

```text
date/window: jun22 batch-61 (OA–OE) PIVOT
- attempts: 5 quick; 0 keeps
- bottleneck: rank-match pile −0.079; longest suit −0.025; table-depth pass / diversity / strip-gate neutral
- what changed: closed batch-61 attack geometry plan
- result: 167b02d unchanged
- next bias: batch-62 refinements
```

```text
date/window: jun22 batch-62–63 (OF–OO) PIVOT
- attempts: 10 quick; 0 keeps
- bottleneck: all neutral (±0.003) or regress; rank-match variants −0.058
- what changed: closed strip>=2, pair deck>=4, void tweak, pile opp narrow, defend same-suit
- result: 167b02d unchanged
- next bias: HD COMBO search-lift batch-64
```

```text
date/window: jun22 batch-64 (OX–PB, OY sweep) COMBO/SWEEP
- attempts: 5 b4 + OY medium/dual + new-suit −2/−5/−8; 0 keeps
- bottleneck: OY (HD+new-suit −3) medium search +0.00418 — ties HD, ~0.0008 below keep bar; PA skip pile trump −0.050
- what changed: closed HD+new-suit bonus sweep; table-depth pass on HD +0.0053 B4 only
- result: 167b02d unchanged; HD remains top unkept probe
- next bias: EXPLORE batch-65 defense timing
```

```text
date/window: jun22 batch-65–66 (PC–PM) EXPLORE defense
- attempts: 10 quick; 0 keeps
- bottleneck: PC/PD mis-implemented all-trump take −0.55; corrected PH neutral; trump penalty sweep neutral
- what changed: closed defense timing axis; rank-gap and same-suit neutral
- result: 167b02d unchanged
- next bias: batch-67 attack refine
```

```text
date/window: jun22 batch-67 (PN–PR) PIVOT
- attempts: 5 b4; 0 keeps
- bottleneck: HD+pile deck<=2 +0.0055 (known); strip opp<=3 and pair-delay regress
- what changed: closed batch-67 attack refinements
- result: 167b02d unchanged; HD remains top unkept probe ~0.0008 below search keep bar
- next bias: PIVOT batch-68 hand-count phase triggers
```

```text
date/window: jun22 batch-68–69 (PS–QC) PIVOT hand-count
- attempts: 10 quick; 0 keeps
- bottleneck: hand<=3 strip −0.010; hand<=4 pile −0.062; pair/opp gates neutral
- what changed: closed hand-count phase triggers; deck gates remain load-bearing
- result: 167b02d unchanged
- next bias: n_table batch-70
```

```text
date/window: jun22 batch-70 (QD–QF) PIVOT n_table
- attempts: 3 b4; 0 keeps; all neutral or regress
- bottleneck: 40+ zero-keep batches; HD ~0.0008 below search keep bar unchanged
- what changed: closed n_table void/pile/pair gates
- result: 167b02d unchanged
- next bias: COMBO batch-71 HD search-lift retries (OX/void/table only)
```

```text
date/window: jun22 batch-71–72 (QG–QO) COMBO HD
- attempts: 5 b4 + HD medium + QG/QI/QK medium + QK dual; 0 keeps
- bottleneck: HD medium search +0.00424 best; QK/OY +0.00418; all COMBOs below +0.0045 keep bar
- what changed: closed HD+pass/void/pile/new-suit/table triple COMBOs
- result: 167b02d unchanged
- next bias: HD ABLATE batch-73
```

```text
date/window: jun22 batch-73 (QS–QV) ABLATE HD
- attempts: 4 b4; 0 keeps
- bottleneck: 43+ zero-keep batches; HD search lift not reachable via second-axis COMBO
- what changed: HD pile −0.052; strip pair-skip −0.010; void −0.001 on HD base
- result: 167b02d unchanged; HD archived EXPLOIT-only sub-gate
- next bias: EXPLOIT stability + meta plateau review
```

```text
date/window: jun22 batch-74–75 (RA–RJ) EXPLOIT
- attempts: RA medium/dual + 8 b4 + RJ medium/dual; 0 keeps
- bottleneck: HD search +0.00424 reconfirmed; KZ/RJ best B4 (+0.0067) but search +0.0040 — tradeoff persists
- what changed: closed HD strip deck 0|2/==2/<=1 sweep; additive deck==2 strip neutral
- result: 167b02d unchanged; meta plateau documented (~0.0008 search gap)
- next bias: PIVOT batch-76 opponent-relative timing
```

```text
date/window: jun22 batch-76–77 (RK–RT) PIVOT opponent-relative
- attempts: 10 quick; 0 keeps; all regress or neutral
- bottleneck: 47+ zero-keep batches; opponent-relative strip/pile/pair gates all anti-synergize with CZ
- what changed: closed opponent-relative timing class (strip opp==1/2, pile opp narrow/widen, hand-advantage pair)
- result: 167b02d unchanged; best probe RP strip opp==2 −0.002 B4
- next bias: PIVOT batch-78 rank/deck structure on CZ
```

```text
date/window: jun22 batch-78 (RU–RY) PIVOT rank/deck + RW medium
- attempts: 5 quick + RW medium; 0 keeps
- bottleneck: RV strip trump==1 −0.060; RW endgame pair deck<=1 neutral at medium (+0.0004 search)
- what changed: closed pair deck>=4, trump==1 strip, void asymmetric, pile hand>=3; RW archived for SWEEP
- result: 167b02d unchanged
- next bias: SWEEP batch-79 endgame pair-promotion deck window
```

```text
date/window: jun22 batch-79 (SA–SE) SWEEP endgame pair deck window
- attempts: 5 quick + SD medium/dual/full; 0 keeps; 1 full eval
- bottleneck: SD deck<=2 pair (strip deck==0) full B4 +0.0064 search +0.0042 — ties HD, ~0.0008 below keep bar
- what changed: closed deck==1-only and deck==2-only pair paths; SD replaces HD as cleaner unkept top probe
- result: 167b02d unchanged
- next bias: EXPLOIT batch-80 SD base search-lift COMBOs
```

```text
date/window: jun22 batch-80 (SF–SJ) EXPLOIT SD COMBOs
- attempts: 5 quick + SF medium/full; 0 keeps; 1 full eval
- bottleneck: SF = KZ tradeoff (B4 +0.0066 search +0.0039); SJ confirms deck==2 pair is SD lift; SH strip still load-bearing (−0.003)
- what changed: closed SD+min+3, void/pile deck<=2 COMBOs; SD search ceiling ~0.7936 documented
- result: 167b02d unchanged
- next bias: PIVOT batch-81 search-lift outside pair-cap class on SD base
```

```text
date/window: jun22 batch-81 (SK–SO) PIVOT SD search-lift
- attempts: 5 quick + SL medium/full; 0 keeps; 1 full eval
- bottleneck: SL void remove medium search +0.0042 ties SD; full +0.0041 below keep bar; SN/SO regress −0.011/−0.052
- what changed: closed void remove, endgame cap min+1, pile pass hand==1 on SD; meta plateau trigger (3 batches 0 keeps)
- result: 167b02d unchanged
- next bias: ABLATE batch-82 SD stack decomposition (deck==1 vs deck==2 pair)
```

```text
date/window: jun22 batch-82 (SP–SV) ABLATE SD stack
- attempts: 5 ablate quick + SU/SV/SQ medium; 0 keeps
- bottleneck: deck==2 pair = entire +0.004 search lift; deck==1 inert; pile −0.052 midgame pair +0.002 strip −0.003
- what changed: SD ablation map complete; SV (CZ + deck==2 additive) +0.0035 quick, below unified SD
- result: 167b02d unchanged
- next bias: EXPLOIT batch-83 deck==2 pair refinements
```

```text
date/window: jun22 batch-83 (SW–TB) EXPLOIT deck==2 pair refine
- attempts: 5 quick + SW medium; 0 keeps
- bottleneck: SX/SZ gates inert; SY/TB opp gates kill deck==2 lift; SV medium +0.0039 below SD +0.0042
- what changed: closed hand/opp/rank gates on deck==2 pair; unified deck<=2 beats split SV form
- result: 167b02d unchanged
- next bias: PIVOT batch-84 deck window widen (deck==3) or simplification
```

```text
date/window: jun22 batch-84 (TC–TG) PIVOT deck window
- attempts: 5 quick; 0 keeps
- bottleneck: deck==2 sharp — TC/TF widen regress; TD deck==3 alone −0.001; TE split 1|2 ties SD
- what changed: closed deck window around deck==2; SD unified deck<=2 confirmed optimal formulation
- result: 167b02d unchanged
- next bias: PIVOT batch-85 new trigger class (total-cards, n_table) on SD base
```

```text
date/window: jun22 batch-85 (TH–TL) PIVOT SD triggers
- attempts: 5 quick; 0 keeps
- bottleneck: TH total<=10 kills deck==2 lift; TI/TJ inert; best = SD tie; TL strip trump>=2 −0.015
- what changed: closed n_table/opp>=3 gates; TH implies lift needs total>10 at deck==2
- result: 167b02d unchanged
- next bias: SWEEP batch-86 total-cards threshold for deck==2 pair
```

```text
date/window: jun22 batch-86 (TM–TQ) SWEEP total threshold
- attempts: 5 quick + TQ medium/full; 0 keeps; 1 full eval
- bottleneck: TQ total<=16 medium search +0.0044 best unkept; full +0.0043 ~0.0007 below keep bar
- what changed: TM total>10 = SD; lift requires total>10 at deck==2; TQ beats SD at medium
- result: 167b02d unchanged
- next bias: EXPLOIT batch-87 fine total threshold 14–18 + TQ dual
```

```text
date/window: jun22 batch-87 (TR–TV) EXPLOIT fine total threshold
- attempts: 4 quick + TV dual + TR/TS/TQ medium; 0 keeps
- bottleneck: TS/TQ medium search 0.79376 (+0.00435) tie peak; TR 0.79373; TU COMBO flat
- what changed: closed total threshold 14–18; ceiling ~0.00065 below keep bar
- result: 167b02d unchanged
- next bias: COMBO batch-88 search-lift on TQ base
```

```text
date/window: jun22 batch-88 (TW–UA) COMBO TQ second-axis
- attempts: 5 quick + TW medium/full; 0 keeps; 1 full eval
- bottleneck: TQ medium 0.79376 remains search peak; TW B4 0.64351 but search 0.79345 tradeoff
- what changed: closed TQ+min+3/void/pile/midgame COMBOs; meta plateau 59+ zero-keep batches
- result: 167b02d unchanged
- next bias: ABLATE batch-89 TQ stack decomposition vs SD
```

```text
date/window: jun22 batch-89 (UB–UG,UH) ABLATE TQ stack
- attempts: 6 quick + UH medium; 0 keeps
- bottleneck: TQ medium 0.79376 stable; total gate +0.00054 vs SD medium; deck==2 pair entire lift vs CZ
- what changed: closed TQ ablation map; unified deck<=2 beats split deck==2-only (UF); pivot to throw-in timing
- result: 167b02d unchanged
- next bias: PIVOT batch-90 throw-in/pass timing outside open-pile-strip
```

```text
date/window: jun22 batch-90 (UI–UM) PIVOT throw-in/pass
- attempts: 5 quick; 0 keeps
- bottleneck: all neutral or regress; UJ catastrophic; pile trump deck<=3 essential
- what changed: closed throw-in pass/take timing axis; return to rank/ordering EXPLORE
- result: 167b02d unchanged
- next bias: EXPLORE batch-91 rank/suit ordering outside timing windows
```

```text
date/window: jun22 batch-91 (UN–UR) EXPLORE rank/ordering
- attempts: 5 quick; 0 keeps
- bottleneck: all neutral or slight regress; UR throw-in rank cap −0.019; void open split inert (UQ)
- what changed: closed rank/suit tie-break and throw-in depth axes
- result: 167b02d unchanged
- next bias: PIVOT batch-92 trump/hand guards on CZ
```

```text
date/window: jun22 batch-92 (UX–VB) PIVOT trump/hand guards
- attempts: 5 quick; 0 keeps
- bottleneck: trumps>=1 and strip opp<=2 load-bearing; UX/UY/UZ/VA regress −0.008..−0.019
- what changed: confirmed CZ guard rails; closed hand-size pile gate; VB deck>=6 pair neutral
- result: 167b02d unchanged
- next bias: SWEEP batch-93 pile opp threshold on CZ
```

```text
date/window: jun22 batch-93 (VC–VG) SWEEP pile opp/deck
- attempts: 5 quick (corrected opp patch); 0 keeps
- bottleneck: opp<=5 sharp optimum; opp<=4/3 regress; opp>=6 slight regress; deck<=3 beats <=2
- what changed: closed pile opp 3–7 sweep on CZ; confirms CQ pile window
- result: 167b02d unchanged
- next bias: PIVOT batch-94 table-depth / rank-match throw-in
```

```text
date/window: jun22 batch-94 (VH–VL) PIVOT rank-match/table-depth
- attempts: 5 quick; 0 keeps
- bottleneck: VH/VI/VK/VL neutral; VJ n_table>=4 −0.014
- what changed: closed rank-match throw-in and table pass axis on CZ
- result: 167b02d unchanged
- next bias: TQ reconfirm + n_table pass fine sweep
```

```text
date/window: jun22 batch-95 (VM–VP) TQ reconfirm + n_table sweep
- attempts: VM quick/medium + 3 quick; 0 keeps
- bottleneck: TQ medium 0.79376 stable; n_table pass catastrophic below keep
- what changed: closed n_table 2–5 pass sweep; TQ still best unkept
- result: 167b02d unchanged
- next bias: COMBO batch-96 on TQ base
```

```text
date/window: jun22 batch-96 (VQ–VU) COMBO TQ second-axis
- attempts: 4 quick + VQ/VS medium + VU dual; 0 keeps
- bottleneck: VQ ties TQ 0.79376; VS 0.79371; VR/VT regress; dual agrees
- what changed: closed TQ+rank-match/pile-opp/strip-opp COMBOs; VS deck>=6 best COMBO −0.00005
- result: 167b02d unchanged
- next bias: EXPLOIT batch-97 deck>=6 x total gate on TQ
```

```text
date/window: jun22 batch-97 (VV–VZ) EXPLOIT TQ deck>=6 x total
- attempts: 5 quick + 4 medium; 0 keeps
- bottleneck: TQ 0.79376 peak; VY/VW 0.79371; VV/VX 0.79368; keep bar unreachable
- what changed: closed deck>=6×total COMBO on TQ; structural ceiling documented
- result: 167b02d unchanged
- next bias: PIVOT batch-98 outside TQ/CZ attack stack
```

```text
date/window: jun22 batch-98 (WA–WE) PIVOT defense/priors
- attempts: 5 quick; 0 keeps
- bottleneck: WA/WE catastrophic; WB/WD/WC neutral on CZ
- what changed: closed defense rank-cap and voluntary take; attack priors inert
- result: 167b02d unchanged
- next bias: EXPLORE batch-99 attack-only micro-tweaks on CZ
```

```text
date/window: jun22 batch-99 (WF–WJ) EXPLORE CZ micro-tweaks
- attempts: 5 quick; 0 keeps
- bottleneck: all neutral or regress; pile opp<=5 and strip trumps>=1 load-bearing
- what changed: closed pair-cap/void micro-sweeps on CZ; meta plateau 69+ zero-keep
- result: 167b02d unchanged
- next bias: meta review batch-100; halt CZ knob sweeps
```

```text
date/window: jun22 batch-100 (WL–WP) meta + PIVOT trump hoard / TQ reconfirm
- attempts: 5 quick + WN/WP medium; 0 keeps
- bottleneck: TQ 0.79376 peak reconfirmed; WL/WM neutral; WO pile deck<=1 −0.019; WP rank-match ties TQ
- what changed: TQ formula + Occam (+3 lines) documented; closed trump hoard and pile deck<=1 on TQ
- result: 167b02d unchanged; keep bar still ~0.00065 above TQ medium
- next bias: PIVOT batch-101 qualitatively new mechanisms on TQ base (strip opp==1, hand-size pile, n_table pass)
```

```text
date/window: jun22 batch-101 (WQ–WU) PIVOT TQ second mechanisms
- attempts: 5 quick + WR/WT/WU medium + WR full; **1 keep**
- bottleneck: WR hand>=opp pile gate breaks TQ ceiling; WQ/WS regress; WT/WU ≤ TQ
- what changed: committed f5bb135 WR; search mode → EXPLOIT; 71-batch plateau broken
- result: f5bb135 B4 0.64489 search 0.79506 lower_ci 0.64464 (+0.00813 B4 vs CZ)
- next bias: EXPLOIT batch-102 ablate hand>=opp; COMBO rank-match / deck>=6 on WR base
```

```text
date/window: jun22 batch-102 (WX–XB) EXPLOIT WR ablate/COMBO/SWEEP
- attempts: 5 quick; 0 keeps
- bottleneck: WX ablate confirms hand>=opp load-bearing (−0.0018 → TQ); WZ/XA hand gate too strict −0.033
- what changed: closed hand gate SWEEP; rank-match and deck>=6 inert on WR base
- result: f5bb135 unchanged; keep bar search≥0.80006
- next bias: EXPLOIT batch-103 ablate total gate / strip on WR; finish-window COMBOs
```

```text
date/window: jun22 batch-103 (XC–XF) EXPLOIT WR ablations + finish probes
- attempts: 4 quick; 0 keeps
- bottleneck: XD strip −0.014 load-bearing; XE opp<=4 −0.016; XC/XF mild −0.0006 each
- what changed: WR stack ablation map complete; pile opp≤5 and deck≤3 confirmed optimal
- result: f5bb135 unchanged
- next bias: SWEEP total gate 14–17; ablate deck==2 pair on WR
```

```text
date/window: jun22 batch-104 (XG–XL) SWEEP total gate + WR probes
- attempts: 6 quick; 0 keeps
- bottleneck: total≤16 and deck≤2 pair confirmed optimal; XJ deck==0 only −0.012; all deltas ≤0.001 below WR
- what changed: closed total-gate SWEEP and opp<=6 on WR; WR stack fully mapped
- result: f5bb135 unchanged; local optimum search 0.79506
- next bias: PIVOT batch-105 qualitatively new mechanisms on WR base
```

```text
date/window: jun22 batch-105 (XM–XO) PIVOT WR new mechanisms + Occam
- attempts: 3 quick; 0 keeps
- bottleneck: XM pile trump deck≤3 load-bearing (−0.020); XN/XO inert; Occam WR 194 lines (+5 vs CZ)
- what changed: closed pile-trump defer and rank-aware void; Occam documented in Current best
- result: f5bb135 unchanged; keep bar search≥0.80006 still ~0.005 away
- next bias: meta batch-106; pile-pass trump hoard; halt WR knob sweeps
```

```text
date/window: jun22 batch-106 (XP–XR) meta ablation map + PIVOT
- attempts: 3 quick; 0 keeps
- bottleneck: XP pile-pass −0.020 (=XM class); XQ inert; XR pair skip −0.0015
- what changed: WR ablation map consolidated in Current best; pile-pass trump hoard closed
- result: f5bb135 unchanged; structural local optimum at search 0.79506
- next bias: meta plateau batch-107; new trigger class or defense-side pivot only
```

```text
date/window: jun22 batch-107 (XS–XU) meta plateau + PIVOT + dual
- attempts: 2 quick + XT medium + XU dual; 0 keeps
- bottleneck: XS ultra-endgame −0.019; XT quick +0.0009 medium 0.79505 flat; dual seeds agree
- what changed: plateau summary in Current best; closed XS hand==1 pass
- result: f5bb135 unchanged; keep bar 0.80006 ~0.005 above WR
- next bias: SWEEP defense rank-match bonus; softer ultra-endgame
```

```text
date/window: jun22 batch-108 (XV–XY) SWEEP defense rank-match + softer pass
- attempts: 4 quick; 0 keeps
- bottleneck: XV/XW quick +0.0005 below medium gate; XX −6 regress; XY inert
- what changed: closed defense rank-match SWEEP and softer ultra-endgame pass
- result: f5bb135 unchanged
- next bias: meta batch-109; optional dual+medium −4; attack-side trump conservation
```

```text
date/window: jun22 batch-109 (XW/XZ/YA) medium −4 confirm + attack PIVOTs
- attempts: 1 medium + 2 quick; 0 keeps
- bottleneck: XW −4 medium 0.79595 (+0.00089) best unkept; XZ/YA inert
- what changed: defense rank-match −4 documented as top probe; attack trump hoard closed
- result: f5bb135 unchanged; keep bar still ~0.0041 above XW medium
- next bias: COMBO WR+def−4 dual; midgame hand gate on open
```

```text
date/window: jun22 batch-110 (YB/YC/YD) COMBO dual+medium + attack PIVOTs
- attempts: 1 dual + 1 medium + 2 quick; 0 keeps
- bottleneck: YB medium 0.79595 reconfirms XW; YC strip opp==1 −0.015; YD inert
- what changed: closed defense−4 COMBO path and strip opp==1 on WR; plateau at f5bb135
- result: f5bb135 unchanged
- next bias: meta batch-111; new attack timing class or accept plateau
```

```text
date/window: jun22 batch-111 (YE/YF) throw-in pass + total gate PIVOT
- attempts: 2 quick; 0 keeps
- bottleneck: YE n_table>=4 −0.016; YF total<=18 inert
- what changed: closed throw-in pass and total gate widen on WR
- result: f5bb135 unchanged; structural plateau confirmed
- next bias: meta halt or ABLATE simplification hunt
```

```text
date/window: jun22 batch-112 (YG–YK) ABLATE WR stack minimal confirm
- attempts: 5 quick ablations; 0 keeps; 0 simplification wins
- bottleneck: pile trump −0.039; midgame pair −0.011; deck<=2 pair −0.012; strip −0.014; void −0.0006 only trim
- what changed: WR stack declared minimal; halt further knob search on attack path
- result: f5bb135 unchanged
- next bias: meta halt; accept plateau unless new mechanism class
```

```text
date/window: jun22 batch-113 (YP/YL–YO) dual reconfirm + new mechanism PIVOT
- attempts: 1 dual + 4 quick; 0 keeps
- bottleneck: all new-class probes inert (±0.0006); dual quick 0.79451 stable vs full 0.79506
- what changed: closed suit geometry, pile depth, defense tight-beat, open pass; terminal plateau
- result: f5bb135 unchanged
- next bias: halt loop; human review or accept WR as final challenger
```

```text
date/window: jun22 batch-114 closure — post-plateau ablation + run complete
- attempts: 0 strategy edits; 1 ablation (5M seeds); engine/sim tests pass
- bottleneck: B4 edge not reached (lower_ci 0.64464 < 0.52); memory inert at 0.50000
- what changed: B3vsB2 row logged; search mode → closed; README results summary
- result: f5bb135 final; jun22 autoresearch run complete
- next bias: none — restart with new hypothesis only
```

```text
date/window: jun25 batch-1 (ZA–ZN) new run — EXPLORE→COMBO defense hand-shape — **1 keep**
- attempts: ~16 probes; 1 keep (ZN full). New hypothesis: the defense/card-selection half is the
  under-explored axis (jun22 tuned only attack); the only positive unkept jun22 signal (defense
  rank-match) already lived here.
- signal map: pair-keep +4 (+0.0010 search) and rank-reuse −4 (+0.0018) stack additively (ZC ≈
  +0.0031q / +0.0020 medium); high-trump conservation take (don't burn rank>=10 trump on a lone
  attack, deck>=5, n_table==1) adds +0.0013 more and lifts B1/B0 strongly. Take rank>=4 is the
  search peak; rank>=0 collapses; void-suit/keep-opener 3rd signals inert.
- what changed: committed `ab2d08c` (exp ZN); manifest comment updated (still 1 heuristic / 0 params);
  results.tsv rows; B3vsB2 0.49920 (memory still inert); charts refreshed.
- result: `ab2d08c` B4 **0.64805** search **0.80025** lower_ci 0.64779 (+0.00519 search / +0.00316 B4
  vs WR). Plateau broken on a fresh axis.
- correction: jun22 docs ("remains below B4", batch-114 "edge not reached") are wrong — B2 lower_ci
  0.648 >> 0.52, so **B2 dominates B4** and has since ~the CZ keep. README results need updating.
- next bias: EXPLOIT take window + re-tune shape magnitudes on ZN base; then EXPLORE more defense.
```

```text
date/window: jun25 batch-2 (ZS–ZZ) EXPLOIT take window on ZN base — **1 keep**
- attempts: 8 probes (n_table sweep ZS–ZV, rank/deck re-sweep ZW–ZZ); 1 keep (ZW full).
- signal map: widening ZN's take is monotone in n_table — `==1`(ZN) < `<=2` < `<=3` < `<=4` < no-cap,
  each step adds search. With the cap removed, re-sweeping the rank floor moved the peak from rank>=4
  (ZN base) to **rank>=3**; deck>=5 still optimal. Kept corner = no-cap / rank>=3 / deck>=5.
- key insight: the ZN `n_table==1` cap was hiding most of the gain — covering *multi-card* attacks
  with high trumps is the bigger waste. Removing it jumped B4 +0.037 (ZN take alone moved B4 only
  +0.003). B2 now wins the majority vs B4 (win 0.445→0.5215).
- what changed: committed `310bc72` (exp ZW); manifest comment simplified (dropped n_table clause —
  one fewer conditional, still 1 heuristic / 0 params); results.tsv rows; B3vsB2 0.49915 (memory
  inert); charts refreshed.
- result: `310bc72` B4 **0.68494** search **0.82176** lower_ci 0.68468 (+0.02151 search / +0.03689 B4
  vs ZN; +0.0267 / +0.0401 vs WR). B1 0.97260 (win 0.956), B0 0.98757 (win 0.978). Second plateau
  break in one run, and the result is *simpler* than the prior best.
- next bias: take window saturated (do not re-sweep). EXPLOIT-3 re-tunes pair-keep/rank-reuse on the
  ZW base (untuned there); then EXPLORE new defense/throw-in shape signals + a B4-take proxy.
```

```text
date/window: jun25 batch-3 (R5–R6, QB–QF, QA) EXPLOIT→ABLATE on ZW base — **1 keep (simplification)**
- attempts: 8 probes (magnitude R5/R6, ablations QB/QC, take re-sweep QD/QE/QF); 1 keep (QA full).
- the EXPLOIT magnitude re-tune was a dud (rank-reuse −5/−6 flat ±0.0006), but the **ablation** it
  motivated was the find: pair-keep + rank-reuse, load-bearing on WR/ZN, are **net-harmful** under
  the broad take. Ablate rank-reuse +0.0015; ablate both +0.0023q search.
- because the shape signals changed which beater is "cheapest", removing them shifted the take floor
  optimum from rank>=3 to **rank>=2** (8+). Re-sweep: rank>=2 +0.0027q over rank>=3; rank>=1 −0.0009
  +loss; deck>=5 firm (deck>=4 −0.024). Final QA = take-only defense, take rank>=2 / deck>=5 / no-cap.
- keep decision: Δsearch +0.00288 / ΔB4 +0.00409 vs ZW (both below the +0.005 add-gate) at EQUAL
  complexity_score. Kept anyway as an **Occam simplification** — the rule "removing a heuristic for
  equal-or-better score is a win" applies; B4 CIs are non-overlapping (robust reporting win), and the
  code is net −3 lines. This is the right call: never lock in known-harmful complexity.
- what changed: committed `8487eb7` (exp QA); manifest comment rewritten; results.tsv rows; B3vsB2
  **0.50000 split 1.0000** (memory now perfectly inert — no tie left to break); charts refreshed.
- result: `8487eb7` B4 **0.68903** search **0.82464** lower_ci 0.68877. B1 0.97519, B0 0.98782.
  Third keep of the run; the defense is now minimal.
- next bias: defense/take axes closed. EXPLORE genuinely new mechanisms — top pick is a **memoryless
  B4-take proxy** (recover the B4 the unconditional take leaves behind); then attack-side pair-keep.
```

```text
date/window: jun25 batch-4 (SA–SD) EXPLORE new mechanisms on QA base — **0 keeps**
- attempts: 4 probes; all fail or inert. The EXPLORE axis (B4-take proxy + attack pair-keep) is
  unproductive — the QA policy is at its memoryless ceiling on the surfaces reachable here.
- SA take gated `hand<=opp`: −0.038 search (catastrophic). The take is valuable *especially* when
  card-heavy; any hand/opp gate disables it where it helps.
- SD take gated `opp_hand>=4`: −0.020 search (hurts B1/B0 most). Confirms: **no gate on the take
  helps** — it is a hard unconditional optimum (gates hurt, lower rank hurts, deck>=5 firm).
- SB/SC attack-side pile pair-keep (+2/+4, pure tie-break): +0.0009q but **+0.0001 medium** = noise,
  and it adds a sub-rule. Inert, like the defense shape signals. Discard.
- result: best unchanged — QA `8487eb7` B4 0.68903 search 0.82464.
- next bias: the three productive axes (attack jun22; defense take jun25 b1/b2; defense shape jun25
  b3-removed) are all closed. Switch to **PIVOT** — only qualitatively new mechanisms (endgame-
  specific play, throw-in pass discipline) are worth trying; expect diminishing returns near ceiling.
```
