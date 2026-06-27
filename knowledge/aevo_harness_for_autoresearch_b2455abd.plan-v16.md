---
name: AEvo harness for autoresearch
overview: Evolve the Durak loop into an external evolution harness whose FIRST deliverable is an authority-separation proof, not better performance. With stubbed agents (no Cursor SDK), Phase 0 proves the agent cannot stop the outer run, write official scores, preserve illegal edits, promote itself, or destroy the archive. Phase 1 attaches Cursor as a bounded patch generator; Phase 1.5 hardens search quality; Phase 2 adds optional measured layers (default OFF). Runtime artifacts live OUTSIDE the repo so git reset/clean cannot destroy them; candidate execution is stateless/snapshot-isolated while the harness is stateful/append-only; scores split into search/holdout/selection; artifacts are atomic and schema-versioned.
todos:
  - id: p0-scaffold
    content: "[P0] evolver/ package (cli.py: run|status|continue|stop; config.py) + run_dir OUTSIDE the repo (default ../.evolver_runs/<run_id>/) holding ALL runtime artifacts (state/candidates/archive/history/logs/scores) so git reset/clean can never destroy them; evolve/{manifest.yaml (evolvable_layers inner:durak/src/strategy_heuristic.cpp, else LOCKED, reload=cold), config.json (max_rounds,K,cost_cap,holdout banks,session knobs,run_dir,schema_version)} tracked in repo. NO cursor-sdk yet."
    status: pending
  - id: p0-protect
    content: "[P0] protect.py VersionControl: reset_all_but_allowlist(base)=git checkout base -- . ':(exclude)<allow>' + git clean -fd -e <allow> (defense-in-depth: negative pathspecs for any in-repo harness path); diff_versus_commit (NUL-aware untracked, Windows); commit_inline via git -c user.email=...; reset_to_base=git reset --hard base + git clean -fd in finally. CRITICAL: copy snapshot/diff to run_dir BEFORE any reset; the runtime store is outside the repo so resets touch only the sandbox. (Option B git worktrees = Phase 1.5.)"
    status: pending
  - id: p0-evaluate
    content: "[P0] evaluate.py harness-owned eval: durak/build.bat fast -> check_forbidden.cmake -> ctest -> scripts/triage.bat; parse search_score/point_rate/lower_ci (reuse run_batch114.py regexes); ATOMIC writes (*.tmp->fsync->os.replace) for scores.json/results.tsv; tag score_kind(search|holdout|full)+schema_version; cheap search bank -> search_alpha; holdout (dual)+full -> holdout_alpha + keep rule search_full>=best+0.005 AND lower_ci>=best_lower_ci. build/forbidden/test/empty-diff/crash => invalid."
    status: pending
  - id: p0-store
    content: "[P0] store.py append-only archive in run_dir (atomic archive.json + per-candidate meta.json/scores.json + model_patch.diff + snapshot.cpp); 3 statuses invalid|valid_stepping_stone|official_best (stepping_stone NEVER sets best_commit; official_best NEVER from search_alpha alone); meta schema {schema_version,id,parent_id,base_commit,round,status,search_alpha,holdout_alpha,selection_alpha,search_score,point_rate_b4,lower_ci,complexity,n_children,children_invalid_count,created_by,eval_bank,score_kind,tokens,eval_seconds}; never delete."
    status: pending
  - id: p0-loop
    content: "[P0] loop.py + StubAgent: driver owns rounds/budget/gate/termination; round = stub propose -> copy artifacts to run_dir -> reset sandbox -> evaluate (search_alpha) -> [promotion track] holdout_alpha+keep -> official_best (commit exp: + tag evo-N + advance best_commit) | else valid_stepping_stone -> store.add -> regenerate results.tsv view -> decrement budget/cost -> console progress; ALL resets in finally; selection = random over valid (score_child_prop is Phase 1). Terminates ONLY on max_rounds/cost_cap."
    status: pending
  - id: p0-validate
    content: "[P0] StubAgent simulates DONE/PLATEAU, illegal edit, scores.json/results.tsv write, crash, timeout, seed-overfit, valid regression. Prove invariants 1-8 (early-stop impossible; illegal edits reset; self-scoring impossible; crash/timeout safe; valid regression preserved+selectable; runtime store survives reset/clean; atomic artifacts crash-safe; archive append-only) with ZERO Cursor/API calls."
    status: pending
  - id: p1-agents
    content: "[P1] agents.py Cursor SDK Agent.prompt(...) (local, cwd=repo) bounded INNER session: max_turns + token cap + wall timeout, disabled_tools (no eval/git/web/shell), DONE ends the session ONLY, bare-text nudge, crash/truncation/empty-diff => invalid candidate, pass iterations_left+cost-used. STATELESS snapshot-isolated; zero stop/score authority. Add cursor-sdk to pyproject.toml."
    status: pending
  - id: p1-select
    content: "[P1] select.py default score_child_prop on selection_alpha (=holdout_alpha if available else search_alpha penalized for non-confirmation): s=sigmoid(10*(alpha-mean_top3)); h=1/(1+n_children); down-weight by children_invalid_count; p∝s*h; sample K over valid ONLY with replacement. random=ablation. Parent invalid ONLY if its own restore/eval fails or snapshot corrupted; a failed child marks ONLY the child (children_invalid_count++), never the parent."
    status: pending
  - id: p1-observe
    content: "[P1] observe.py compact bounded Φ (best curve, last-segment outcomes, plateau length, families tried/closed, rejected directions, cost, localized B4 residual) -> run_dir/observations/round_NNN.md; append-only memory.md + history.jsonl + cost.jsonl; flush-before-loss; NEVER dump the full archive into the prompt."
    status: pending
  - id: p1-mechanism
    content: "[P1] mechanism/evolve_skill.md (snapshot-isolated/stateless candidate contract + AEvo anti-stop rule: 'while budget remains you do not exit; if stuck, name the structural reason and submit from a different family') + memory.md (durable append-only). meta_skill.md/family_map.md = Phase 2."
    status: pending
  - id: p1-integrate
    content: "[P1] Wire Cursor into the proven Phase-0 loop; re-run invariants 1-8 with the REAL agent; tiny-budget live dry run (max_rounds=2,K=2,quick+dual) asserting invariants 9-13 (search/holdout split; failed-child != invalid-parent; best lineage pinned; cost cap halts externally; optional layers OFF). Read locked thresholds/rejected directions from program.md; regenerate the results.tsv view; touch only mutable docs."
    status: pending
  - id: p15-harden
    content: "[P1.5] Search-quality hardening: score_child_prop tuning; archive hygiene (pin best lineage, active+pinned selection pool, conservative archive of dead records, pre-run backup); parent usage counters (selection_count/last_selected/last_improvement/children_invalid_count); richer Φ; restart/resume durability (atomic state + crash-resume from run_dir); optional Option-B git worktrees for candidate isolation."
    status: pending
  - id: p2-measure-engine
    content: "[P2] Extract EvolutionEngine ABC from the Phase-1 seam (corrected A-Evolve engine/base.py): step(workspace, observations=Φ+harness-feedback, history)->StepResult{mutated,summary,metadata}; manages_own_evaluation LOCKED False (no trial arg, harness scores); NO StepResult.stop; on_cycle_end(accepted,score) advisory only. GreedyEngine = ONE-SHOT ablation reproducing the paper's 'greedy replace = little to no progress' on Durak (archive is mandatory, NOT gated on this)."
    status: pending
  - id: p2-qd
    content: "[P2] Quality-diversity behind the engine interface: descriptors.py (b(x) from --mode features), gridless novelty/curiosity, MAP-Elites grid, islands+migration, modifiable selection (select_policy.json). Each measured vs the Phase-1 baseline; kept only if it beats it on holdout-confirmed gain."
    status: pending
  - id: p2-cost-hygiene
    content: "[P2] Curator (LLM parts) + SweepEngine: curator.py LLM review pass (SUGGEST-ONLY, provenance-gated, never-delete) + auto-stale state machine + LLM memory consolidation + skill-library; FTS5 evolution.db; SweepEngine (engine/sweep.py, LLM-FREE: one sweep spec -> many parameter candidates, 0 Agent.prompt calls, maps to sweep_atk_trump.py + SWEEP mode, holdout-gated, created_by=sweep). Each measured vs the P1 baseline."
    status: pending
  - id: p2-meta-convergence
    content: "[P2] Meta-agent self-modification (agents.py meta path + meta_skill.md Pi-menu P0->P6 + family_map.md): bounded meta Agent.prompt every M rounds edits mechanism/**, reset all but the meta layer; kept only if it beats the fixed mechanism on holdout gain. Harness-owned evidence convergence GATED BEHIND a mandatory min_rounds FLOOR; harness-update attribution; optional parallel Pass@K via worktrees."
    status: pending
isProject: false
---

# AEvo harness for the Durak autoresearch loop — executable authority contract (vNext)

**The first deliverable is not better Durak performance. It is an authority-separation proof:** the agent may generate patches, but it cannot stop the outer run, cannot write official scores, cannot preserve illegal edits, cannot promote itself, and cannot destroy the archive. **Only after this proof passes with stubbed agents do we attach the real Cursor agent.** This sentence governs every decision below; vNext does not add sophistication — it makes the invariants executable and removes ambiguous authority boundaries.

**Problem (one line):** today the agent owns the loop, the stop decision, and `results.tsv`; `program.md:416` says `NEVER STOP` yet the agent declared PLATEAU and halted. Prose cannot bind the budget — an external driver can.

**Named failure modes closed:** agent stops early; agent-local DONE vs external budget; reward hacking; self-written scores; evaluator/test modification; reward saturation; diversity collapse; noise-overfitting; context bloat; archive bloat; cost blow-up; stale ideas resurfacing; untestable meta-churn. **vNext additions:** harness destroying its own artifacts; selecting official best on noisy search wins; over-aggressive parent invalidation; half-written artifacts corrupting restarts.

## The 5 non-negotiable invariants (Phase-0 proof targets)

Prove all five with **stub agents and zero Cursor/API calls** before any SDK integration:
1. agent emits `DONE`/`PLATEAU` -> the outer loop continues to budget;
2. agent edits locked files -> discarded by the reset before eval;
3. agent writes `scores.json`/`results.tsv` -> harness regenerates them, agent values ignored;
4. a crashing/timing-out candidate -> marked invalid, never fatal;
5. a valid regression -> stays in the archive and remains selectable.

## Phases

### Phase 0 — authority proof (stubs only, NO Cursor SDK)
Build `config.py`, `protect.py`, `evaluate.py`, `store.py`, `loop.py`, `cli.py` + a `StubAgent`. No mutation intelligence; selection is random over valid; Φ is a stub. **Goal: prove the 5 invariants.** Closes: agent stops early; DONE-vs-budget; reward hacking; self-scoring; evaluator/test edits; crash-fatality; archive destruction.

### Phase 1 — real candidate generation (attach Cursor)
Add `agents.py` (Cursor SDK bounded inner session), `select.py` (score_child_prop on `selection_alpha`), `observe.py` (compact Φ + memory), `mechanism/evolve_skill.md`, `history.jsonl`, `cost.jsonl`. **Goal: real bounded sessions generate candidates — still with no scoring or stop authority.** The Phase-0 invariant tests must still pass with the real agent. Closes: context bloat; local-optimum lock-in.

### Phase 1.5 — search-quality hardening
`score_child_prop` tuning; archive hygiene (pin best lineage, active+pinned selection pool, conservative archive of dead records); parent usage counters; richer Φ; restart/resume durability (atomic state, crash-resume from `run_dir`); optional Option-B git worktrees. **Goal: make the search productive, not merely safe.** Closes: archive bloat; diversity collapse; stale ideas resurfacing.

### Phase 2 — optional measured layers (default OFF)
EvolutionEngine ABC + GreedyEngine; gridless novelty; MAP-Elites; islands; modifiable selector; curator agent; non-LLM SweepEngine; skill library; meta-agent + attribution; FTS5; evidence-based convergence (behind a `min_rounds` floor). Each kept only if it beats the Phase-1 baseline on **holdout-gain per dollar**. Closes: untestable meta-churn.

## Mechanical contracts (the vNext corrections)

**1. Runtime store lives OUTSIDE the repo (reset/clean can never destroy it).** `git reset --hard <base>` + `git clean -fd` delete untracked files — which would wipe `candidates/`, `state.json`, `history.jsonl`, logs, and scores. Fix: the harness runtime store is `run_dir` **outside the repo working tree** (default `../.evolver_runs/<run_id>/`). The repo working tree is only the candidate sandbox. Snapshots/diffs are copied OUT to `run_dir` **before** any reset. `evolve/{manifest.yaml, config.json, mechanism/}` stay tracked in the repo (inputs, restored by reset, never lost). `results.tsv` is a **regenerated view** of `run_dir`; if clean deletes it, the harness rewrites it. Defense-in-depth: every clean carries negative pathspecs for any in-repo harness path. **Phase-1.5/2 upgrade: Option B git worktrees** — generate candidates in a throwaway worktree, copy only the diff/artifacts back into the protected store.

**2. Stateless candidate / stateful harness (do NOT say "memoryless").** Candidate execution is **snapshot-isolated and stateless** (each starts from a restored parent snapshot, no in-memory carryover). The **harness is stateful and append-only** (`memory.md`, `history.jsonl`, archive, `state.json`). The agent receives only **bounded Φ, never the full archive**.

**3. Three scores (split alpha).** `search_alpha` = cheap search-bank score, computed for **every valid candidate**, used for **exploratory parent selection only**. `holdout_alpha` = disjoint-seed holdout score, computed **only on the promotion track**, **required for official-best promotion**. `selection_alpha` = `holdout_alpha` if available, else `search_alpha` **penalized** by an uncertainty/non-confirmation factor. Official best is **holdout-locked**; the archive still explores cheaply on `search_alpha`.

**4. Three candidate statuses (never confuse best with stepping stone).** `invalid` (failed build/test/eval/protection, empty diff, crash). `valid_stepping_stone` (builds + evaluates, may be worse, **selectable**). `official_best` (passed the locked holdout keep rule and advanced `best_commit`). Hard rules: a `valid_stepping_stone` **never** updates `best_commit`; an `official_best` is **never** chosen by `search_alpha` alone.

**5. Parent/child invalidation (correct the HyperAgents rule).** A failed child marks **only the child** invalid. A **parent** becomes invalid **only** if restoring/replaying/evaluating the parent itself fails or its snapshot/diff is corrupted. Repeatedly-bad parents are **penalized** via `children_invalid_count` (selection down-weight), **not removed** from the pool.

**6. Atomic artifacts + schema versions (crash-safe restarts).** All official artifacts are written `*.tmp -> fsync -> os.replace(final)`: `scores.json`, `archive.json`, `results.tsv`, `state.json`. Every record carries `schema_version`; e.g. `{schema_version, candidate_id, parent_id, eval_bank, score_kind: search|holdout|full, created_by: harness}`. A half-written file never corrupts a restart.

## Final architecture

**Module layout**

```
<repo>/
  evolver/                  # harness code (in repo)
    cli.py loop.py config.py protect.py evaluate.py store.py select.py observe.py agents.py
    # P2: engine/ population/ descriptors.py curator.py
  evolve/                   # tracked INPUTS (restored by reset, never lost)
    manifest.yaml  config.json  mechanism/{evolve_skill.md, memory.md}   # P2: meta_skill.md, family_map.md
  durak/src/strategy_heuristic.cpp     # the ONLY allowlisted mutable file
  results.tsv               # regenerated VIEW of run_dir (rebuilt if cleaned)
../.evolver_runs/<run_id>/  # run_dir: runtime store OUTSIDE the repo (git cannot touch it)
  state.json  archive.json  history.jsonl  usage.json  cost.jsonl  evolve.log  backups/
  candidates/candidate_NNNN/{model_patch.diff, snapshot.cpp, meta.json, scores.json}
  observations/round_NNN.md
```

**Data model** — `meta.json` (harness-written, atomic): `schema_version, id, parent_id, base_commit, round, status(invalid|valid_stepping_stone|official_best), search_alpha, holdout_alpha, selection_alpha, search_score, point_rate_b4, lower_ci, complexity, n_children, children_invalid_count, created_by, eval_bank, score_kind, tokens, eval_seconds`. `scores.json` = official numbers, harness-only, atomic. `usage.json` (sidecar): `pinned, state(active|stale|archived), selection_count, last_selected, last_improvement`.

**Run loop** (per round until `max_rounds`/`cost_cap`): `observe (Φ) -> select K valid parents (selection_alpha) -> K inner sessions (restore parent snapshot, edit strategy file) -> copy snapshot/diff to run_dir -> protect.reset_all_but_allowlist + capture diff (skip empty) -> evaluate search bank -> search_alpha -> if promotion candidate: holdout+full -> holdout_alpha + keep rule -> official_best (commit 'exp:' + evo-N + advance best_commit) | else valid_stepping_stone (stays selectable) -> store.add (atomic) -> regenerate results.tsv (atomic) -> decrement budget/cost -> print progress`. All resets in `finally`; the run_dir store is untouched by resets.

**Candidate lifecycle** — propose -> copy artifacts to run_dir -> reset sandbox -> evaluate -> status ∈ {invalid, valid_stepping_stone, official_best}; valid records append-only, never deleted; dead records (unpinned, 0 children) -> `state=archived` (restorable); best lineage pinned; selection samples active+pinned only.

**Parent-selection interface** — `Selector.select(container, k, rng) -> list[id]`; `Container.parents_pool()` valid-only; reads `selection_alpha`; cannot write scores. P0: `RandomSelector` over valid. P1 default: `ScoreChildPropSelector` (`s=sigmoid(10*(α−mean_top3)); h=1/(1+n_children); p∝s*h`, α=`selection_alpha`, down-weighted by `children_invalid_count`).

**Evaluation pipeline** — `build.bat fast` -> `check_forbidden.cmake` -> ctest -> `triage.bat <gate>`; any failure or empty diff -> invalid. Cheap `quick` (search bank) -> `search_alpha` for every valid candidate; `dual`+`full` (holdout) -> `holdout_alpha` only on the promotion track.

**Holdout Gate** — escalate on seed 0; official best advances only after the candidate clears `search_full ≥ best+0.005 AND lower_ci ≥ best_lower_ci` on the disjoint seed-1 holdout + full. Returns `Verdict(accept, rollback, reason)`. Fail -> not promoted (stays `valid_stepping_stone`), sandbox reset to best; `selection_alpha` = `holdout_alpha` if computed else penalized `search_alpha`.

**Memory system** — append-only `memory.md` (episodic, never rewritten); compact bounded Φ per round; `history.jsonl` + substring search (FTS5 P2); flush-before-loss before any compaction; the prompt never receives a full archive.

**Cost policy** — caps at session / round / total (`cost_cap` USD), checked by the driver before spending; static prefix prefix-cached; only compact Φ + snapshot vary; opt-in layers OFF and judged per dollar.

**Convergence policy** — Phase 0/1: budget-only, harness-decided; no agent "done" read. Phase 2: holdout-confirmed improvement-rate + coverage/diversity behind a mandatory `min_rounds` floor; `StepResult.stop` does not exist.

## Rejected (or deferred)

- prompt-only "NEVER STOP"; agent-owned scoring / appending `results.tsv`; greedy best-only as the search (GreedyEngine ablation only); `COMPLETE`/DONE sentinel for the outer run; unprotected evaluator access; full archive dumps in the prompt; complex QD before the flat baseline; personal-assistant platform features; engine-managed evaluation / `StepResult.stop` / agent-editable selector in core / B5 stateful memory.
- **vNext rejects:** storing runtime artifacts where `git clean` can delete them; promoting official best on `search_alpha`; marking a parent invalid on one failed child; non-atomic artifact writes; calling the whole system "memoryless."

## Acceptance tests

**Phase-0 invariants (stub agents, no API):**
1. **early stopping impossible** — stub emits DONE/PLATEAU + a flat-scoring evaluator -> all `max_rounds` run.
2. **illegal edits reset** — stub edits `simulate.cpp`/`tests/*`/`triage.bat` -> gone after reset; diff touches only the strategy file.
3. **self-scoring impossible** — stub writes `scores.json`/`results.tsv` -> overwritten/regenerated; selection reads harness scores only.
4. **crash/timeout safe** — stub raises / hangs -> invalid candidate; `finally` resets; loop proceeds; remaining K continue.
5. **valid regression preserved & selectable** — a worse-but-valid candidate is stored `valid_stepping_stone`, never updates `best_commit`, stays in `parents_pool()`.
6. **runtime store survives reset/clean** — after `reset --hard` + `clean -fd`, `run_dir` (candidates/state/history/scores) is intact; `results.tsv` is regenerated.
7. **atomic artifacts** — a simulated crash mid-write leaves the previous `scores.json`/`archive.json`/`state.json` valid (tmp+rename); restart resumes.
8. **archive append-only** — records only appended; a restart preserves them.

**Phase-1+ (real agent / search quality):**
9. **search vs holdout split** — every valid candidate has `search_alpha`; only promotion-track candidates have `holdout_alpha`; official best required `holdout_alpha`.
10. **failed child ≠ invalid parent** — a child crash/illegal-edit marks only the child invalid; the parent stays selectable with `children_invalid_count++`.
11. **best lineage pinned** — promotion pins the lineage; pinned is exempt from archive transitions.
12. **cost cap enforced** — a low `cost_cap` halts mid-run; a budget-spent report is written.
13. **optional layers OFF by default + measured** — P2 layers disabled and the core completes a run; enabling one runs the same loop and emits a holdout-gain-per-$ delta vs Phase 1.

## Implementation order (smallest authority-proving slice first)

**Phase 0 (no Cursor):** `p0-scaffold` (config + cli + run_dir outside repo) -> `p0-protect` (safe reset; runtime outside repo) -> `p0-evaluate` (atomic scores; score_kind) -> `p0-store` (3 statuses; atomic archive) -> `p0-loop` (driver + StubAgent) -> `p0-validate` (prove invariants 1–8). 

**Phase 1 (attach Cursor):** `p1-agents` -> `p1-select` (search/selection alpha; child-only invalidation) -> `p1-observe` -> `p1-mechanism` -> `p1-integrate` (re-run invariants 1–8 with the real agent + tiny live dry run for 9–13).

**Phase 1.5:** `p15-harden`. **Phase 2:** only after the baseline is measured: `engine/GreedyEngine -> novelty -> MAP-Elites/islands -> curator+sweep+FTS -> meta-agent+attribution+evidence-convergence`.

## Cursor prompt (paste into Agent mode)

```text
Implement this evolution harness for the Durak repo in PHASES, exactly as specified in
.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md. The FIRST deliverable is an
authority-separation PROOF with STUB agents — NOT better Durak performance and NOT a Cursor
integration. Do not write agents.py or call the Cursor SDK until Phase 0 passes.

PHASE 0 (no Cursor SDK, stub agents only). Build config.py, protect.py, evaluate.py, store.py,
loop.py, cli.py + a StubAgent. The StubAgent must be able to simulate: DONE/PLATEAU text; an illegal
evaluator/test edit; a scores.json/results.tsv write attempt; a crash; a timeout; a seed-overfit
candidate; and a valid regression. The full loop MUST pass these with ZERO Cursor/API calls:
  1. DONE/PLATEAU -> the outer loop still runs all max_rounds;
  2. illegal edit -> discarded by the reset before eval;
  3. scores.json/results.tsv agent write -> regenerated by the harness, agent values ignored;
  4. crash/timeout -> invalid candidate, never fatal, finally-reset, loop continues;
  5. valid regression -> stored valid_stepping_stone, never updates best_commit, stays selectable.

HARD INVARIANTS (never violate):
- The driver owns rounds, budget, scoring, the gate, and termination; the agent is a bounded patch
  generator with ZERO loop/stop/score authority. Terminate only on max_rounds or cost_cap.
- Scores are harness-only: only evaluate.py writes scores.json and regenerates results.tsv, written
  ATOMICALLY (write *.tmp -> fsync -> os.replace). Same for archive.json and state.json. Every
  record carries schema_version, candidate_id, parent_id, eval_bank, score_kind(search|holdout|full),
  created_by=harness.
- DO NOT store candidate/runtime artifacts where git can delete them. Put the runtime store OUTSIDE
  the repo working tree at run_dir (default ../.evolver_runs/<run_id>/). Copy snapshot/diff out to
  run_dir BEFORE any reset. Keep evolve/{manifest.yaml,config.json,mechanism/} tracked in the repo.
  results.tsv is a regenerated VIEW of run_dir; rebuild it if it is cleaned. Defense-in-depth: pass
  negative pathspecs to git clean for any in-repo harness path.
- Protection is mechanical: after every candidate, reset everything except the allowlist
  (durak/src/strategy_heuristic.cpp) via
  `git checkout <base> -- . ":(exclude)durak/src/strategy_heuristic.cpp"` then
  `git clean -fd -e durak/src/strategy_heuristic.cpp`; full reset `git reset --hard <base>` +
  `git clean -fd` in a finally block. These touch only the repo sandbox; the run_dir store is
  unaffected.
- Candidate execution is STATELESS and snapshot-isolated (restore the parent snapshot first; no
  in-memory carryover). The HARNESS is stateful and append-only. Do NOT call the system memoryless.
  The agent sees only bounded Phi, never the full archive.
- Success = subprocess exit_code == 0, never the agent's self-report. Empty diff / crash / timeout
  => invalid candidate.
- A failed child marks ONLY the child invalid. A parent becomes invalid ONLY if restoring/evaluating
  the parent itself fails or its snapshot/diff is corrupted; otherwise keep it in the pool and just
  increment children_invalid_count.
- Three statuses: invalid | valid_stepping_stone | official_best. valid_stepping_stone NEVER updates
  best_commit; official_best is NEVER chosen by search-bank score alone.
- Three scores: search_alpha (cheap search bank, every valid candidate, exploratory selection only);
  holdout_alpha (disjoint seed, promotion track only, required for official best); selection_alpha
  (holdout_alpha if available else search_alpha penalized for non-confirmation). Official best
  advances only on the keep rule search_full >= best+0.005 AND lower_ci >= best_lower_ci.

PHASE 1 (only after Phase 0 passes): add agents.py (Cursor SDK Agent.prompt, cwd=repo, bounded:
max_turns + token cap + wall timeout; tools = read repo + edit the strategy file only, no
git/eval/web/shell; DONE ends the session only; bare-text nudge once; catch all exceptions ->
invalid), select.py (score_child_prop on selection_alpha, valid-only, child-only invalidation),
observe.py (compact Phi + append-only memory.md + history.jsonl + cost.jsonl, flush-before-loss),
mechanism/evolve_skill.md (stateless/snapshot-isolated contract + the AEvo anti-stop rule). Add
cursor-sdk to pyproject.toml. Re-run all Phase-0 invariant tests with the real agent, then a
tiny-budget live dry run (max_rounds=2, K=2, quick+dual).

PHASE 1.5 / PHASE 2: do not implement now (search hardening; then optional measured layers, OFF).

Style: PEP8, pathlib (not os), single quotes, type hints. Show console progress for anything slow
using macro point_rate/search_score. Do not touch the locked column of program.md or the
evaluator/tests/metric/thresholds.
```
