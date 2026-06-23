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

- Commit: `167b02d`
- B4 point_rate: 0.63676
- Search score: 0.78941
- Lower CI: 0.63652
- Complexity: 100
- Why it is best: CQ combo (pair `deck>=5` + pile `deck<=3`) plus endgame open trump-strip when `opp<=2`; +0.010 B4 vs CQ at full. Ablation: pile −0.059, strip −0.010, pair −0.005 medium.
- **Top probe (unkept):** exp HD strip `deck<=2` — medium B4 0.64323 (+0.0065), search 0.79365 (+0.0042), full B4 0.64318; ~0.0008 below search keep bar. One-line delta from CZ: `deck==0` → `deck<=2` on open strip path.

## Search mode

- Mode: **EXPLORE**
- Since: batch-44/45/46 — HD loop closed (medium search +0.0042 stable, skip full); defense rank cap flat (JJ −0.23); attack explore JL/JM regress
- Next batch type: EXPLORE pile rank-match fix + hand-pressure triggers; HD archived as top probe pending keep-bar breakthrough
- After next keep: **EXPLOIT** on kept stack

## Open questions

- Which local situations does B4 exploit most? **Strip deck<=2** (HD) +0.006 B4 full, search +0.004 — must keep `deck==0` strip; `deck==2` adds signal; `deck==1` drags (HO 0|2 slightly worse than HD <=2).
- Is the B2 weakness mostly attack choice, defense choice, take/pass threshold, or trump conservation? **Attack open/pile/strip** — batch-42 defense/pile pivots flat; HD strip `deck<=2` remains only strong signal.
- Are B1/B0 gains misleading relative to B4? B1/B0 rose with CZ (~0.956/0.971) but B4 delta is the keep signal.
- Does complexity reduction improve B4 parity? Still complexity 100; three timing windows, zero parameters.

## Editable research directions

Next 5 experiment ideas (**EXPLORE** batch 47 — pile/hand pressure):

1. **Pile rank-match throw-in** — prefer legal card matching table rank (JK fix/retry).
2. **Pair-open when hand<=3 cards** — tighter JL variant.
3. **Pile pass when hand has 1 card left** — endgame pass trigger.
4. **AttackDone when only trump left and deck==0** — dump avoidance.
5. **HD strip** — do not re-run unless new quick >= +0.006 from another axis COMBO.

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
