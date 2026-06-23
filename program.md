# autoresearch: Durak local-heuristics lab

This is an experiment to have an LLM autonomously search for a strong **memoryless**
strategy for two-player *podkidnoy* Durak, under a locked rules engine, and measure how
far simple local heuristics can go against fixed baselines — including a memory-counting
opponent.

You edit exactly one file: `durak/src/strategy_heuristic.cpp` (the no-memory policy core
`choose_move_core` and its manifest). Everything else is the fixed harness.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `jun22`). The branch
   `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The project is small. Read these for full context:
   - `README.md` — research framing.
   - `durak/include/policy_core.hpp` — the fixed B2/B3 interface you implement against.
   - `durak/src/strategy_heuristic.cpp` — **the only file you modify**.
   - `program.md` — this file.
4. **Build and test**: run `durak\build.bat test` (Windows). All three tests
   (`engine_tests`, `simulation_tests`, `forbidden_check`) must pass before you start.
5. **Initialize results.tsv**: if it does not exist, create `results.tsv` with just the
   header row (see "Logging results"). The baseline is recorded after the first run.
6. **Confirm and go**: confirm setup looks good, then kick off the experiment loop.

## What you CAN and CANNOT do

**You CAN** edit `durak/src/strategy_heuristic.cpp`:
- Change the body of `choose_move_core` (add, remove, reorder heuristics; tune parameters).
- Update the manifest (`kHeuristicCount`, `kParameterCount`, `kComplexity`) to match.
- Use only `LocalFeatures` (always) and the optional `MemoryFeatures*` (memory branch).

**You CANNOT**:
- Change `policy_core.hpp` (the signature), the engine, the simulator, the RNG, the
  baselines (B0/B1/B3/B4), the tests, the CMake flags, or the stopping criteria.
- Use `static`/global mutable state to remember turns, cards, seeds, games, or opponent
  actions. The strategy must be a pure function of the current observation.
- Add I/O, files, networking, clock access, threading, or randomness inside
  `strategy_heuristic.cpp`. (`forbidden_check` enforces this; it must keep passing.)
- Add a new heuristic class that fires only when `memory != nullptr`. The memory branch
  (B3) may only refine tie-breaks/priors of the same heuristics the no-memory path uses.

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

Two stages. Do not stop on the first time a confidence interval crosses a threshold during
a batch — that is sequential peeking. Decide keep/discard **only** on the full stage.

- `quick_eval`: `--eval quick` (100k seeds). Smoke test / crash detection / rough signal.
- `full_eval`: `--eval full` (5M seeds). The only stage used for keep/discard.

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

1. Look at the git state: the branch/commit you are on.
2. Edit `durak/src/strategy_heuristic.cpp` with one experimental idea (and update the
   manifest). Keep changes minimal and Occam-friendly.
3. Rebuild: `durak\build.bat` (and `durak\build.bat test` if you touched anything subtle —
   the forbidden check and engine tests must pass).
4. `git commit` the change.
5. `quick_eval` first: `simulate --mode ladder --eval quick > durak\run.log 2>&1`. If it
   crashed or is clearly worse, discard early.
6. If promising, `full_eval`: `simulate --mode ladder --eval full > durak\run.log 2>&1`.
7. Read the summary from `durak\run.log`.
8. Record the row(s) in `results.tsv` (do NOT commit results.tsv). Re-run or execute
   `analysis.ipynb` to refresh `progress.png` and the Occam scatter plot.
9. Apply the keep rule. If improved, keep the commit and advance the branch. If equal or
   worse, `git reset --hard` back to where you started this step.
10. After any `keep`, run the memory ablation (`--mode ablate --eval full`) and log the
    `B3vsB2` row.

**Crashes**: if a run produces no summary, read the tail of `durak\run.log`. If it is a
trivial bug you introduced, fix it and re-run. If the idea is fundamentally broken, log
`crash` and move on.

**NEVER STOP**: once the loop has begun, do NOT pause to ask the human whether to continue.
The human may be away and expects you to keep iterating indefinitely until manually
stopped. If you run out of ideas, think harder: re-read the heuristics, try removing one
to simplify, try combining near-misses, reconsider the take/throw-in trade-offs, study
where B4's memory actually helps (via the ablation and the win/loss/split breakdown). The
loop runs until the human interrupts you.
