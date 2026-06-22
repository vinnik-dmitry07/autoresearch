# autoresearch: local heuristics vs memory in Durak

An autonomous-research lab for a single question in an imperfect-information card game.

## What are we testing?

Can a **memoryless** local heuristic policy compete with a fixed **memory-counting**
baseline in two-player *podkidnoy* Durak? The challenger strategy may look only at its own
hand and the cards currently on the table — it is forbidden from remembering the discard
pile or any history. The benchmark opponent (B4) tracks what has left play and what the
opponent is known to hold.

## Why is it interesting?

It isolates how much of the strength in two-player Durak comes from **local hand/table
structure** (which suit to break, when to take, which trump to spend) versus
**belief-state inference over hidden cards**. An LLM agent searches the space of small
heuristic rules, and we measure the result against a ladder of fixed baselines plus a
direct memory ablation.

This project is not trying to solve Durak globally. It tests whether a memoryless local
heuristic policy can approach or beat fixed memory-based baselines under a locked rules
engine.

## What counts as a win?

- **Reporting metric**: paired `point_rate` of the challenger (B2) against the
  memory-counting baseline (B4). Around 0.50 is parity; `lower_ci > 0.52` is a real edge.
- **Search metric**: a composite ladder score across B0/B1/B4 to give the agent a smoother
  gradient.
- **Simplicity**: fewer rules win ties. The strategy declares a `complexity_score`
  (`100 * heuristics + 10 * parameters`); among near-equal strategies the simpler one is
  preferred.
- **Memory value**: measured separately (post-keep) as B3 vs B2 — the *same* policy core
  with memory enabled vs disabled.

## The baseline ladder

| Level | Strategy | Role |
|-------|----------|------|
| B0 | random legal | sanity floor |
| B1 | basic no-memory (lowest card, minimal defense) | "are the heuristics doing anything?" |
| B2 | heuristic no-memory (`strategy_heuristic.cpp`) | the agent-edited challenger |
| B3 | B2's core + memory features | memory ablation (fixed wrapper) |
| B4 | independent memory-counting baseline | reporting opponent |

B2 and B3 share one function, `choose_move_core`: B2 calls it with no memory, B3 with
memory. So the only difference between them is access to memory, which makes the ablation
honest no matter how the agent rewrites the core.

## Rules (locked)

Two-player *podkidnoy*, no transfer (perevod). 36 cards (6–A), 6-card hands, trump is the
bottom card. The holder of the lowest trump attacks first. Throw-ins must match a rank
already on the table (attack *or* defense card); total attack cards per battle are capped
at `min(6, defender's hand size at battle start)`. A successful defense sends the table to
the discard and passes the attack to the defender; taking keeps the attacker and the
defender skips its attack. After each battle both draw to six, attacker first. The player
left holding cards once the deck is empty is the loser; simultaneous empty hands is a draw.

## Quick start

Requirements: a C++23 compiler and CMake. On Windows the bundled Visual Studio toolchain is
used by the helper script.

```bat
:: Windows: configure, build, and run the test suite
durak\build.bat test

:: Run the baseline ladder (challenger B2 vs B4 / B1 / B0)
durak\build\simulate.exe --mode ladder --eval full --batch 500000 > durak\run.log 2>&1
```

Generic CMake (any platform):

```bash
cmake -S durak -B durak/build -DCMAKE_BUILD_TYPE=Release
cmake --build durak/build
ctest --test-dir durak/build --output-on-failure
./durak/build/simulate --mode ladder --eval full
```

`simulate` modes: `ladder` (B2 vs the ladder + search_score), `match --challenger X
--opponent Y`, `ablate` (B3 vs B2), `selfplay --strategy X`. Eval sizes: `--eval quick`
(100k seeds) or `--eval full` (5M seeds); override with `--seeds N`.

## Running the agent

Point your agent at `program.md` and let it iterate:

```
Have a look at program.md and let's kick off a new Durak experiment. Do the setup first.
```

The agent edits only `durak/src/strategy_heuristic.cpp`, rebuilds, evaluates, and keeps or
reverts based on the protocol in `program.md`.

## Project structure

```
durak/
  include/        cards.hpp, move.hpp, engine.hpp, policy_core.hpp, strategies.hpp, eval.hpp
  src/            engine.cpp, strategies.cpp, strategy_*.cpp, simulate.cpp
  tests/          engine_tests.cpp, simulation_tests.cpp (golden + sanity), test_util.hpp
  cmake/          check_forbidden.cmake (no static/IO/clock/random in the heuristic file)
  CMakeLists.txt
  build.bat       Windows build/test helper
program.md        agent instructions and the experiment loop
results.tsv       experiment log (untracked)
```

## Legacy LLM experiment

This repo began as a single-GPU LLM training autoresearch loop. Those files (`train.py`,
`prepare.py`, `pyproject.toml`, `analysis.ipynb`) remain for reference but are not part of
the Durak experiment.

## License

MIT
