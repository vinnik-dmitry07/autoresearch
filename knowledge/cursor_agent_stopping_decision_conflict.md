# Agent stopping decision conflict
_Exported on 6/27/2026 at 00:49:00 PDT from Cursor (3.7.42)_

---

**User**

look at the current system and suggest improvements:
https://arxiv.org/html/2605.13821v1 
The main problem that I want to solve is:
Even with prompts encouraging long-horizon search, coding agents often stop early once local improvements become difficult, as seen in the early best rounds of Codex on Task 1 and Task 3. This suggests that an agent’s internal stopping decision can conflict with the external evolution budget. AEVO addresses this by placing the coding agent inside an explicit evolution harness, where rounds, candidate records, and evaluation feedback are maintained outside the agent’s local decision loop.

---

**Cursor**

I'll research the paper and your current system to understand both, then suggest improvements. Let me start by reading the paper and exploring the codebase.

Now let me read the control plane (`program.md`) and the key harness files to understand how the current autoresearch loop works.

Let me get the overall structure of `program.md` and look at the key durable sections.

This is a rich system. Let me examine the harness scripts and how the loop is actually driven, since that's central to the AEvo comparison.

Let me look at the evaluator interface (`triage.bat`) and the current strategy to ground the plan.

I've now studied both the paper and your system in depth. Here's my understanding before I draft a plan.

**Your system in AEvo's terms.** Your autoresearch loop is exactly the "agent-based evolution" AEvo critiques. You already have several AEvo-like ingredients: a locked/protected evaluator (`simulate.exe` + gated triage), a candidate ledger (`results.tsv`), durable process memory (`program.md` sections), a meta-review cadence, and search modes. But the loop is **prose-driven**: a human pastes a Cursor prompt, and one agent both runs experiments *and* decides when to stop. The `## Search mode` is currently `CLOSURE / PLATEAU` and `program.md` says *"NEVER STOP"* — which is precisely the "prompt encouraging long-horizon search" the paper shows is insufficient. The agent declared the memoryless space saturated (~0.689 vs B4) and halted.

**The gap vs AEvo.** Three things are missing: (1) an *external* process that owns rounds + budget so the agent can't end the run; (2) a structural split between a **meta-editing phase** (edit the mechanism Π) and an **evolution segment** (inner agent produces K candidates under a run plan); (3) true *mechanism* editing (de-anchoring prompts, Pass@K diverse sampling, restructured feedback, family maps) rather than just re-pointing which heuristic axis to try. Minor: the agent writes its own official scores into `results.tsv` (a reward-hacking surface AEvo explicitly protects).

Two forks change the plan significantly, so I want to confirm before drafting it.

**Scope of the AEvo-style improvements**

> **What form should the solution take? (This is the core fork: only an external process that owns the budget truly fixes 'the agent's stopping decision conflicts with the external budget'.)**
> - (Recommended) Build a real external evolution-harness driver (e.g. scripts/evolve.py) that owns rounds+budget, spawns inner-agent and meta-agent sessions via the Cursor CLI/SDK, runs the protected eval itself, and records candidates to a structured store. The agent literally cannot stop early. ✔
> - Lighter: keep the Cursor-prompt-driven loop but harden it AEvo-style — external round-budget file the agent must honor, explicit meta-editing/segment phases, mechanism-editing + de-anchoring actions, structured candidate store, and replace 'NEVER STOP' with AEvo anti-stop skill rules. No new agent-spawning runtime.
> - Design doc only: write up the AEvo-aligned redesign + concrete recommendations now, implement later.

> **What should the harnessed loop actually search? (The memoryless contract is genuinely well-mapped, so where the harness spends its budget matters.)**
> - Stay strictly memoryless; use AEvo mechanism-editing/de-anchoring/Pass@K to attack the residual B4 losses (likely small upside, but keeps the existing contract intact). ✔
> - (Recommended) Allow the harness to open the already-authorized memory/stateful branch (B5) as a new mechanism class when the memoryless axis is closed — this is where real upside likely is, and it exercises AEvo's 'edit the mechanism, switch family' idea.
> - Build the harness as domain-agnostic infra and leave the search-target choice to the running loop / decide later.

==== Thinking ====
I need to build an external evolution-harness driver script that manages the full optimization loop—handling rounds and budget allocation, spawning both inner and meta-agent sessions through the Cursor CLI, running the protected evaluation itself, and persisting candidates to a structured store. The key constraint is that the agent can't exit early; it must complete its assigned work regardless of intermediate results. I'm also keeping the system strictly memoryless, relying on the AEvo framework.

Now I'm mapping the concrete architecture to the existing Windows/PowerShell setup: the harness owns the workspace, protects the locked evaluator (simulate.exe), records all candidates with their scores and traces, and exposes a CLI for initialization, launching evolution segments, checking status, and continuing runs. Each evolution segment runs the inner agent to generate multiple candidates, evaluates them through the protected evaluator, and logs everything with cost and provenance data. The meta-agent then observes the accumulated state to guide the next round of edits.

For this system, the mechanism (what the meta-agent edits) includes the inner agent's operating context—its skill prompt, the feedback format showing results and diagnostics, diversity policies like Pass@K and de-anchoring, and the family map. The candidate is a specific strategy_heuristic.cpp edit, and the evaluator is the locked simulate.exe accessed through triage gates. The driver script will initialize the harness workspace with a structured candidate store, snapshot the baseline strategy and its scores, and set up the mechanism files that guide the inner agent's proposals for the next segment.

The main loop owns the budget and runs in rounds: at each segment boundary, a meta-agent session reviews the observation summary (progress curve, recent failures, rejected directions, plateau status) and edits the mechanism files plus the run plan, but is forbidden from touching the strategy code or scores; then an inner-agent session uses the updated skill and goal to propose candidates by editing the strategy file, with Pass@K allowing multiple variants per round; finally the driver runs protected evaluation on each candidate through the build and triage pipeline. ent's mechanism-editing toolkit for this memoryless Durak search: de-anchoring forces the inner agent to explore a different family of heuristics when plateaued (using a family map of mechanism classes like attack-open, defense-take, tie-breaks), Pass@K diverse sampling generates multiple candidate variants per round and keeps the best after quick triage, and restructured feedback changes what evidence the agent sees—per-deal diagnostics, win/loss/split breakdowns, rejected directions. Since the user mandated strict memorylessness, the harness keeps editing the strategy file under that constraint while using these mechanism edits to guide how the inner agent searches.

The real tension is that the memoryless space is already declared saturated, yet the harness's job is to robustly re-attack the residual using AEvo-style mechanism editing to either extract it or confirm closure with much stronger evidence—many diverse families tried under external budget, rather than the agent's subjective stopping point. The upside on the memoryless contract is likely small, but the primary deliverable is the harness itself, which removes the agent's stopping authority and validates the mechanism-editing capability on this residual. Now I need to check the Cursor SDK to ground the agent-spawning mechanism correctly for the plan.
==== Thinking ====

You chose the external **driver** harness, staying **strictly memoryless**. Since the driver needs to spawn inner/meta agent sessions programmatically via the Cursor SDK, let me read the SDK skill to ground the plan in the correct API.

I have what I need on the SDK (Python `cursor-sdk`, `Agent.prompt(...)` local runtime, `CURSOR_API_KEY`). Let me confirm a few concrete integration points (Python project file, the build interface, and the strategy contract surface the inner agent edits) so the plan is accurate.

I now have a complete, grounded picture. Here's my plan.

---

**User**

check Hyperagents paper to make improvements to your plan: @c:\Users\Asus\AppData\Local\Temp\Rar$DIa41740.3932\paper.tex 

---

**Cursor**

Let me read the pseudocode, parent-selection details, and the qualitative meta-improvement sections, since those are the most actionable.

This paper changes my plan in one important way. Let me read the current plan file so I can revise it precisely.

This paper materially improves the plan. The key realization: my current plan's "keep the best, revert everything else" is **exactly the `DGM-H w/o open-ended exploration` baseline that HyperAgents proves fails to escape plateaus** (test-set 0.0–0.116, "little to no improvement"). Since your system's whole problem is *being plateaued*, greedy single-best hill-climbing is the wrong search structure.

HyperAgents contributes four things AEvo lacks that I'll fold in: (1) an **open-ended archive** of stepping stones (keep all valid candidates, not just the best); (2) **probabilistic parent selection** (sigmoid-of-performance × novelty `1/(1+children)`) so the search branches from diverse parents instead of the single stuck optimum; (3) **compute-aware planning** (agents get remaining budget; explore early, exploit late); (4) **persistent structured memory** (insights, causal hypotheses, forward plans, pathology/redundancy detection) plus **metacognitive self-modification** (the meta agent can edit its own skill). Parent selection and the evaluator stay fixed/locked, matching DGM-H's main-experiment choice and your locked contract.

Let me revise the plan file.

I've revised the plan to integrate HyperAgents. The headline change:

**Your current loop — and my v1 plan — use greedy single-best hill-climbing (keep the best, revert the rest). HyperAgents proves that exact structure (their `w/o open-ended exploration` ablation) gets stuck in local optima and shows "little to no improvement."** Since being plateaued is your whole problem, I swapped in their open-ended search structure.

What changed in [the plan](.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md):

- **Open-ended archive instead of revert-and-forget.** Every *valid* candidate (even regressions) is kept in `evolve/candidates/` as a branchable stepping stone. Only the *reported best* is still advanced by your locked keep rule + `git commit`.
- **Probabilistic parent selection** (`evolver/select.py`): branch from parents sampled by `sigmoid(performance) × novelty(1/(1+children))`, not always from the single stuck optimum — this is the mechanism that escapes plateaus. The algorithm stays fixed/locked, matching DGM-H's main experiments and your locked contract.
- **Compute-aware planning.** Agents receive remaining budget and shift from ambitious/de-anchoring early to refine/exploit late (this also subsumes your EXPLORE/EXPLOIT modes).
- **Persistent structured memory + pathology detection** (insights, causal hypotheses, forward plans, redundancy flags) in `evolve/mechanism/memory.md`, plus **metacognitive self-modification** — the meta agent may edit its own `meta_skill.md`. All harness-side; never inside the memoryless B2 policy.
- Added two todos (`parent-select`, `observe-memory`) and updated the architecture diagram, workspace layout, and loop accordingly.

The AEvo core is unchanged: an external driver owns the budget so the agent can't stop early, with protected scoring and meta-editing of the mechanism.

Two things worth flagging:
- I kept **parent selection and the evaluator fixed/locked** (DGM-H locks these in its main runs too; their appendix shows making parent-selection editable is feasible but riskier). If you'd rather let the harness eventually evolve its *own* parent-selection, that's a natural follow-on — say the word and I'll add it as an optional later phase.
- Everything HyperAgents-derived lives in the harness, so the strictly-memoryless B2 contract is untouched.

Want me to switch to agent mode and start building, or refine the plan further first?

---

**User**

check Hyperagents code to make improvements to your plan: https://github.com/facebookresearch/HyperAgents 

---

**Cursor**

I have the repo structure. Let me pull the actual implementation of the key files — the main loop, the meta agent, parent selection, and how the meta agent produces diffs — since those are what will sharpen the plan.

The released code reveals two things that differ from the paper and will simplify and harden the plan. Let me read the full main loop, plus the task agent and the git protection helpers.

This is the actual shipped implementation, and it sharpens several decisions. The most important discoveries from the code:

1. **Evaluator/contract protection is done by git-reset, not by trusting the agent.** In `run_meta_agent.py`, the agent runs with `tools_available='all'` (it can edit anything), then the harness calls `reset_paths_to_commit(git_dname, commit, paths=["domains/"])` to throw away any edits to protected paths before capturing the diff. This is far more robust than my "the inner agent only edits one file" assumption — the harness should give full tools, then **reset everything except an allowlist back to base**, guaranteeing the locked engine/baselines/metric/tests can never be altered by a candidate.
2. **A candidate is a git diff vs the base commit** (`diff_versus_commit`, which is already Windows-aware using `NUL`), and lineage is built by applying the parent's stack of patches. Empty diff → skip evaluation.
3. **Parent selection: the CLI default is `score_child_prop`** (the sigmoid×novelty I described), but the shipped editable-seed `select_next_parent.py` is literally `random.choice` over **valid parents only** ("keeping the search space open"). So it should be pluggable with choices `{random, latest, best, score_prop, score_child_prop}`, eligible over valid parents only, and parents whose children keep failing get marked `valid_parent=False`.
4. **Commits use inline `git -c user.email=...`** (never touches global config), and every container/agent run resets to base in a `finally` (survives crashes/Ctrl-C). `iterations_left = max_generation - current_genid` is passed to the agent (compute-aware).

Let me fold these into the plan.

I've revised [the plan](.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md) using the shipped code. The code changed three design decisions and confirmed one.

**Changed:**
- **Contract protection is now mechanical, via git-reset (the biggest change).** Instead of trusting the agent to edit only `strategy_heuristic.cpp`, the harness runs the agent with **full tools**, then resets every path outside an allowlist back to base — exactly HyperAgents' `reset_paths_to_commit(..., paths=["domains/"])` in `run_meta_agent.py`. The inner agent's allowlist is `durak/src/strategy_heuristic.cpp`; the meta agent's is `evolve/mechanism/**`. This makes it *physically impossible* for a candidate to alter the engine/baselines/metric/simulator/tests/`forbidden_check`, which is stronger than my v2 and closes reward-hacking concretely. Added a new `protect-reset` todo.
- **Candidates are git diffs vs base** (their `diff_versus_commit`, already Windows-aware with `NUL`), with empty-diff → skip eval, and a full-file snapshot for branching. Lineage = parent snapshot + new diff.
- **Parent selection is pluggable over *valid* parents only**, with the exact CLI choices `{random, latest, best, score_prop, score_child_prop}`. Parents whose children keep failing get `valid_parent=False` and drop out. (`best` is retained only as the ablation that reproduces today's greedy behavior.)

**Confirmed / refined:**
- The paper's sigmoid×novelty *is* the default (`score_child_prop`); the simpler `select_next_parent.py` uses uniform `random.choice` over valid parents "to keep the search open." I made it configurable rather than committing to one.
- Adopted their operational niceties: **inline `git -c user.email=...` commits** (never touches global config — also satisfies your git-safety rules), **always-reset-in-`finally`** (survives crashes/Ctrl-C), and **`iterations_left`** passed to the agent for compute-aware behavior.

**One philosophical note worth your call:** HyperAgents' meta agent uses a *deliberately minimal* instruction (`"Modify any part of the codebase"`) and lets memory/performance-tracking *emerge*, whereas AEvo prescribes a structured meta-skill. I leaned toward **lean skills** (contract + anti-stop + how to read the archive, not over-prescriptive) to avoid prematurely constraining the search. If you'd rather I write a heavily-specified meta-skill instead, say so.

Want me to switch to agent mode and start building, or refine further?

---

**User**

Check ralph loop code https://github.com/snarktank/ralph 
what is computational cost?
prevent reward collapse?
quality-diversity via MAP-Elites or something else?

---

**Cursor**

==== Thinking ====
I need to examine the Ralph loop code to address three specific questions about computational cost, preventing reward collapse, and the quality-diversity approach being used.

Ralph operates as a minimal autonomous loop: a bash script spawns a fresh AI instance each iteration with clean context, while memory persists through git history, an append-only progress file, and a task list tracking which stories have passed quality checks. Each cycle picks the highest-priority incomplete story, implements it in one context window, runs typecheck and tests, commits on success, and repeats until all stories pass or the iteration budget exhausts. The key insight is that fresh context each iteration prevents drift and keeps tasks small enough for a single window, with feedback loops from CI checks driving progress.

Now I'm working through the three analytical questions about my plan. For computational cost, I need to break down the expenses: the meta-editing phase costs one agent session, the evolution segment costs K inner agent sessions for Pass@K sampling, and each candidate incurs build time plus triage gate evaluation (which is CPU-bound, not LLM-bound). With K=4, that's roughly five agent sessions per round, and scaling to 100 rounds means the LLM cost dominates, though the actual gate evaluation depends on how many candidates escalate through the triage pipeline.

I should make cost tracking explicit in my harness—recording per-candidate token usage and eval time in the metadata, surfacing this in the observation summary, and enforcing a budget cap. The key insight is that Durak's eval is CPU-cheap (it's a C++ simulator, not an LLM call), so unlike HyperAgents or AEvo, my bottleneck is almost entirely the coding-agent sessions, which means the width K and number of rounds are the primary cost levers.

To keep costs down, I'll keep K modest (2-4 candidates per round), leverage prompt caching for efficiency, and cap total rounds or spending. There's a tradeoff between fresh context per candidate (which avoids drift but loses caching benefits) and persistent cached context (which enables cheaper reuse but risks drift)—I'll lean toward fresh-per-candidate but use the compact observation summary to bound token growth.

Now I need to think through reward collapse and reward hacking: whether the agent games the metric itself, or whether the population prematurely converges to a single mode or loses diversity.

My design already guards against reward hacking through three layers—the harness owns the scoring so the agent can't write fake scores, the git-reset allowlist physically prevents the agent from modifying the evaluator or tests, and the locked simulator with forbidden checks block cheating. This matches AEvo's isolated-evaluator approach and directly addresses the vulnerability HyperAgents found in their ablation.

For diversity collapse and premature convergence, Ralph's greedy hill-climbing is weak here, but I'm addressing it through the open-ended archive, probabilistic parent selection to avoid collapsing to a single best, and de-anchoring prompts. The user's MAP-Elites suggestion points toward explicit quality-diversity maintenance—keeping a diverse population rather than just performance-weighted selection. I should also add explicit diversity-collapse detection in observe.py to flag when candidates become too similar or the agent keeps re-proposing the same family.

The Occam penalty and keep rule already prevent overfitting to noise, and the harness respects the locked keep rule to avoid sequential peeking. For MAP-Elites specifically, the question is what behavior descriptors to use—complexity score (heuristic count), win/split/loss profiles against B4, and the family mechanism (attack-open, pile, strip, defense-take, etc.) are natural candidates from the existing diagnostics.

MAP-Elites would bin candidates by these descriptors and keep the best search_score in each cell, maintaining diversity across the memoryless policy space. However, since the Durak search is essentially single-objective over a small, well-mapped space with noisy metrics (~0.0016 SE at 100k samples), MAP-Elites might be overkill compared to the simpler HyperAgents archive. That said, given the goal of escaping the plateau, a lightweight MAP-Elites approach keyed on a couple of behavioral dimensions—like complexity bucket × W/L/S profile or family × deck-window—could be a pragmatic middle ground.

The key insight is that the --mode features harness already emits cheap, meaningful behavioral stats (role-normalized challenge columns), which are perfect MAP-Elites descriptors. Combined with complexity_score, a small 2-3D coarse-binned archive would leverage existing infrastructure and directly combat premature convergence by forcing parent selection to sample across cells. The main risk is that with a noisy scalar objective and small space, cells could fill with noise rather than genuine behavioral diversity.

I should answer the three questions directly and concretely since they're design forks that could reshape the plan, then offer MAP-Elites as a concrete upgrade to the archive/parent-selection strategy with caveats about noise mitigation (admit candidates only on lower_ci, keep bins coarse).
==== Thinking ====

Let me read the actual Ralph loop and prompt to ground the cost analysis before answering.

Got it. Ralph is the minimalist end of this design space, and it sharpens the three questions well. Quick synthesis, then your answers.

**What Ralph validates / where it's weak.** `ralph.sh` is just `for i in $(seq 1 $MAX_ITERATIONS)` spawning a **fresh** agent each iteration (`cat prompt.md | amp` / `claude --print`), with memory in files + git (`prd.json` task list, append-only `progress.txt` with a consolidated "Codebase Patterns" section at the top, `AGENTS.md`). It confirms two pillars of our plan: an **external loop owns the budget**, and **fresh context per iteration prevents drift**. But Ralph is **greedy and converges by design** — it hill-climbs a finite PRD and *stops* on a `COMPLETE` sentinel. That stop condition is exactly what we must NOT copy for open-ended optimization, and Ralph has **no population, no diversity, no protected scoring** — so it's the right skeleton but the wrong search dynamics for escaping a plateau ([ralph.sh](https://github.com/snarktank/ralph/blob/main/ralph.sh), [prompt.md](https://github.com/snarktank/ralph/blob/main/prompt.md)).

## 1. Computational cost

Cost splits cleanly because **our evaluator has no LLM in it** — `simulate.exe` is pure C++/CPU, unlike HyperAgents where evaluation itself calls FMs. So:

- **Agent (LLM) cost — dominant.** Per round = `1 meta + K inner` sessions (Pass@K). At K=4, 100 rounds ≈ **500 fresh agent sessions**. The knobs are K, rounds, and tokens/session. Ralph's "small task + fresh context" + our compact Φ summary (not the full archive) keep tokens/session bounded. Ballpark, with a cached static skill/contract prefix, ~$0.05–0.30/session → **~$0.25–1.50/round, ~$25–150 for a 100-round run** — in line with AEvo's reported $/R of 0.3–1.5.
- **Eval (CPU) cost — nearly free.** Staged triage means most candidates die at the quick gate (~6–10s); only candidates clearing the delta gate hit the 5M full eval (~1.7 min). Typical round ≈ well under a minute of CPU. This is the DGM-H staged-eval / Ralph feedback-loop pattern you already have.
- **The real tension is caching vs. drift.** Fresh-per-candidate (Ralph) avoids drift but loses prompt caching; AEvo notes agent-based evolution stays cheap precisely *because* of prompt caching + persistent context. Resolution in the plan: fresh context per candidate, but **cache the static prefix** (skill + locked contract) and only vary the small Φ/parent — keeps cost down without reintroducing drift.

Cost controls I'll add: per-candidate token + eval-time recorded in `meta.json`, surfaced in Φ, and a hard `cost_cap` the driver enforces alongside `max_rounds`.

## 2. Preventing "reward collapse"

There are three distinct failure modes; the plan needs all three, and only the first was fully covered:

- **Reward hacking** (agent games the metric) — already the strongest part: harness-owned scoring + the git-reset allowlist means a candidate *physically cannot* touch the simulator/metric/tests/`forbidden_check` (only `strategy_heuristic.cpp` survives). This is exactly the protection whose absence made 2/3 HyperAgents "w/o harness" runs reward-hack. Plus the locked full-eval keep rule (no sequential peeking) blocks keeping a noise-inflated candidate.
- **Diversity collapse** (population converges to one mode = the plateau) — partially covered by the open-ended archive + probabilistic parent selection + de-anchoring. I'll **add explicit collapse detection** in `observe.py`: track distinct families / behavioral signatures / candidate-diff similarity, and when diversity drops or a family is re-proposed, force de-anchor toward an under-explored region (the analog of HyperAgents' bias/pathology detection).
- **Reward saturation** (the scalar flattens and stops giving gradient — literally your current state) — I'll make the plan fall back, when the scalar is flat, to the **non-scalar diagnostic signal** (`--mode features`: the deck-empty initiative residual) plus diversity, so the search keeps making *meaningful* moves instead of noise-chasing. The composite `search_score` (B4+B1+B0) already smooths the gradient; the diagnostics extend it when even that saturates.

## 3. Quality-diversity: MAP-Elites or something else?

**MAP-Elites fits unusually well here, because the descriptors already exist.** Your `--mode features` harness emits role-normalized behavioral stats (voluntary/forced-take rates, high-trump-conservation rate, deck-empty trump-attack rate, pile/attack aggressiveness), and `complexity_score` + the W/L/S-vs-B4 profile are natural axes. A **coarse 2–3D grid keeping the best `search_score` per cell** would maintain a diverse population of memoryless policies and give de-anchoring a concrete target ("fill an empty/sparse cell") — directly attacking both the plateau and diversity collapse. Parent selection becomes "sample a cell, take its elite," which preserves diversity better than flat performance-weighted selection.

**Caveats (why it's a real decision, not a free win).** The space is small and already well-mapped, and the metric is noisy (SE≈0.0016 at 100k). Plain MAP-Elites can over-fragment and let noise flip a cell's elite. Mitigations: keep bins **coarse** (few cells), admit/replace a cell's elite only on a **robust** signal (medium/full + `lower_ci`), and keep the **single reported best** governed by the locked keep rule (the map is the *search engine*, not the deliverable). Lighter alternatives exist (novelty-weighted selection over the flat archive) if you'd rather not commit to a grid.

This last one changes the archive/selection design, so I want your call before I rewrite that section. (Cost model + the two new anti-collapse mechanisms I'll fold in regardless.)

**Quality-diversity design for the archive**

> **Which quality-diversity structure should the archive + parent selection use?**
> - (Recommended) Lightweight MAP-Elites as the default: a coarse 2-3D grid keyed on --mode features behavioral descriptors + complexity, best search_score per cell, noise-robust cell admission (full + lower_ci), single reported best under the locked keep rule. Best fit for escaping the plateau and preventing collapse.
> - Keep the flat HyperAgents archive + pluggable parent selection (random/score_child_prop) now; add MAP-Elites later as an optional selection mode only if the flat archive also plateaus.
> - Novelty-weighted selection over the flat archive (lighter than MAP-Elites): weight parent sampling by behavioral distance, no grid to maintain.
>
> Answer: Add all of them: flat HyperAgents archive, pluggable parent slection (random/score_child_prop/modifiable parent selection), MAP-Elites with coarse 2-3D grid and without grid (weight parent sampling), island-based population models

==== Thinking ====
The user wants a unified framework where different quality-diversity strategies—flat archives, MAP-Elites variants with and without grids, island models—can all plug into a common population and parent selection system that's easily modifiable.

I'm designing a pluggable population subsystem with two independent axes: container types (flat archive, MAP-Elites grid, island model) that all expose the same interface for adding candidates and sampling parents, and selector strategies (random, latest, best, score-based, novelty-weighted, cell-sampling, migration, and meta-agent-modifiable) that determine how parents are chosen from whichever container is active.

The meta-agent can switch or tune both the container and selector based on compute and plateau detection, and can directly edit the modifiable selection policy. Behavioral descriptors computed from challenge statistics and complexity are shared across MAP-Elites griding, novelty calculation, and island speciation. Admission to the container is strict—only valid, fully-evaluated candidates are added—and replacement of elites or best candidates follows a locked lower-confidence-interval rule to ensure noise robustness.

For the island model, each island maintains its own flat archive with a selector, and migration happens periodically via ring topology to copy top candidates between islands, providing coarse-grained diversity and parallelization. I need to restructure the plan around a clean population package that unifies all these backends, update the config schema to include container, selector, descriptor, island, and migration parameters, add the modifiable selection policy file to the meta-agent's allowlist, enhance observe.py with diversity-collapse detection and QD statistics, and incorporate the cost and anti-collapse mechanisms from earlier sections.

I'm checking which plan file to update — the canonical aevo_harness_for_autoresearch_b2455abd.plan.md is the one CreatePlan manages, so I should edit that directly rather than the user's manual copies.

Let me read the current plan file and search the codebase for the feature descriptors used in MAP-Elites mode so I can make the updates concrete.
==== Thinking ====

The user wants all of them, unified behind a pluggable interface (including a meta-agent-modifiable selector and island models). Let me read the current plan and ground the behavioral descriptors in the actual `--mode features` output before rewriting the population section.

Let me ground the behavioral descriptors in the actual feature columns the simulator emits.

This grounds it well. The `--mode features` harness already emits per-game behavioral aggregates (e.g. `chal_voluntary_takes`, `chal_trump_attack_cards_deck_0`, `chal_deck0_high_trump_attacks`, `chal_cards_taken`) and the policy has a `complexity_score`/`kComplexity` manifest — so batch-mean behavioral descriptors for MAP-Elites/novelty/islands are essentially free. Let me rewrite the plan to add the unified pluggable population subsystem (all of: flat archive, pluggable+modifiable selection, MAP-Elites grid, gridless novelty, islands) plus the cost and anti-collapse sections.

Done. The plan now incorporates Ralph plus your three answers, with the population layer made fully pluggable per your "add all of them" instruction.

**What changed in the plan**

- **Ralph added as the 4th source.** We copy its skeleton (external `for`-loop owning a hard budget, fresh context per iteration, file/git memory) but explicitly **reject its greedy `COMPLETE` early-stop** — our driver has no stop sentinel and a population, not a checklist.
- **New "Population & quality-diversity (pluggable)" section** with two orthogonal plug-ins, both meta-switchable:
  - **Container**: `flat` (HyperAgents keep-all) · `map_elites` (coarse 2–3D grid, elite per cell) · `islands` (K subpopulations + ring migration).
  - **Selector**: `random` · `latest` · `best` · `score_prop` · `score_child_prop` · `novelty` (gridless QD = MAP-Elites without a grid) · `curiosity` (cell sampling) · `modifiable` (meta agent edits `select_policy.json`, the DGM-H `--edit_select_parent` idea).
  - **Descriptors `b(x)`** are free from the existing `--mode features` harness: defense voluntariness (`chal_voluntary_takes`), endgame trump aggression (`chal_trump_attack_cards_deck_0` / `chal_deck0_high_trump_attacks`), card intake (`chal_cards_taken`), and `complexity_score` (the `kComplexity` manifest) as an Occam axis — so a complexity grid axis *illuminates the score-vs-Occam frontier directly*.
- **New "Computational cost" section** (your Q1): cost is dominated by `1 meta + K inner` agent sessions/round because the C++ evaluator has **no LLM**; eval CPU is near-free via staged triage; controls = compact Φ, cached static prefix, per-candidate token/eval logging, and a hard `cost_cap`. Ballpark ~$25–150 per 100-round run.
- **New "Preventing reward collapse" section** (your Q2) covering all three modes: reward *hacking* (harness-owned scores + reset allowlist), diversity *collapse* (QD + coverage/distance/entropy detection → force curiosity/novelty/new island), and reward *saturation* (fall back to the B4 residual guided by `b(x)` when the scalar flatlines).
- **Noise-robust admission** threaded throughout: candidates enter the population on any valid eval, but a **cell elite / reported best only changes under the locked keep rule** (full eval + `lower_ci`), so a lucky `+eps` can't flip elites.
- **Todos restructured** into `population-containers` + `selectors` + `evaluate-archive`/`descriptors`, and the diagram, workspace layout (`evolver/population/`, `select_policy.json`, `b_descriptor` in `meta.json`), loop, and validation all updated (dry run now asserts every container/selector loads, coverage grows, noise doesn't flip an elite, and `cost_cap` halts).

Direct answers to your three questions: **cost** = agent-session-bound, not eval-bound, capped via `cost_cap` + caching; **reward collapse** = prevented on all three fronts above; **quality-diversity** = MAP-Elites *and* gridless novelty *and* islands *and* flat, all behind one pluggable, meta-editable interface rather than picking just one.

The plan is updated and ready to implement whenever you want to switch to agent mode — or tell me what to refine.

---

**User**

Check this code to improve your plan:
https://github.com/A-EVO-Lab/a-evolve 

---

**Cursor**

Let me read the uploaded a-evolve doc and pull the repo structure in parallel.

A-Evolve is a much larger, more general framework than the others ("PyTorch for Agentic AI"), so the high-value ideas are architectural. Let me pull its design doc and the engine interface, and verify locally how our triage seeds work (to judge the holdout-gate idea).

This is the richest of the four. Two things stand out: (1) A-Evolve makes the *entire evolution algorithm* a single plug-in (`EvolutionEngine.step(workspace, observations, history, trial)`) with named shared primitives (`TrialRunner`, `EvolutionHistory`, `VersionControl`), and (2) its 5-phase loop has an explicit **Gate** that validates on holdout and **rolls back regressions via git** with `evo-N` tags. Crucially, our `triage.bat` already has the seed-disjoint primitive for this — the `dual` stage runs seed-bank 0 then seed-bank 1 and only escalates if **both agree**. Let me fold these in.

Done. A-Evolve contributed the most structural upgrades yet, and the plan now integrates them.

**What A-Evolve added (and how the plan changed)**

- **The whole algorithm is now one plug-in.** Adopted `EvolutionEngine.step(workspace, observations, history, trial) -> StepResult` (with `manages_own_evaluation` + `on_cycle_end`). Everything you asked for last turn (flat / MAP-Elites / islands / novelty / modifiable selection) becomes the internals of the **default `QDEngine`**; a `GreedyEngine` ships only as the DGM-H ablation baseline. The loop never changes when you swap algorithms.
- **Named shared primitives** so module boundaries match a proven framework: `VersionControl` (`protect.py`), `TrialRunner` (`engine/trial.py`), `EvolutionHistory` (`engine/history.py`), and `AgentWorkspace`/`manifest.yaml`.
- **Manifest of evolvable layers.** The allowlist is now declared in `evolve/manifest.yaml` (`evolvable_layers`: inner → `strategy_heuristic.cpp`, meta → `evolve/mechanism/**`; everything else locked) — "change what's evolvable = edit the manifest," cleaner than hard-coded paths.
- **The big one — Gate on a seed-disjoint holdout + git rollback + `evo-N` tags.** This is A-Evolve's Solve→Observe→Evolve→**Gate**→Reload, and it maps perfectly onto something you already have: `triage.bat`'s `dual` stage runs `seed_base=0` then `seed_base=1` and only escalates if **both agree**. So the plan now *selects/escalates on the search bank but only keeps (cell elite or reported best) after a candidate also clears a disjoint holdout bank*, rolling back anything that doesn't generalize. Combined with `lower_ci`, this makes "reward collapse via noise" structurally hard.
- **Harness-owned convergence (EGL analog).** The **driver** computes a convergence signal (holdout-confirmed improvement rate + seed-fold stability + coverage saturation) and owns termination with the budget — turning "PLATEAU/CLOSURE" into an evidence-backed verdict, never the agent's feeling.
- **Harness-update attribution** (from their "Harness Updating Is Not Harness Benefit" line): log which meta-edits precede holdout-confirmed gains and periodically run a no-meta-edit control, so mechanism churn that doesn't cause gains gets throttled.
- **Cost refinements** from their design: description-first skills (cheap description in prompt, body on-demand) + append-only JSONL memory keep the meta prompt lean; optional parallel Pass@K via per-candidate git worktrees (their ProcessPool-with-workspace-copy pattern).

The 5-phase framing, the new engine/primitives section, the holdout-Gate section, the convergence/attribution section, the diagram, workspace layout, loop, todos, and validation are all updated. The dry-run validation now explicitly asserts a seed-overfit `+eps` **fails the holdout and is rolled back**, the engine swaps cleanly, and harness convergence can halt the run.

Net effect across all four references: an **external, budget-and-convergence-owning driver** runs a **pluggable evolution engine** that searches a **quality-diverse population** with **meta-editable selection**, protected by a **manifest allowlist reset**, and keeps nothing until it survives a **seed-disjoint holdout** — directly targeting your plateau without letting the agent stop early or fool itself on noise.

The plan is ready to implement whenever you want to switch to agent mode, or I can keep refining.

---

**User**

Check this code to improve your plan:
https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md 

---

**Cursor**

==== Thinking ====
I'm looking at the ALE Claw harness to understand its approach—it's a minimal single-agent loop designed for long-horizon tasks that emphasizes how a small, well-structured harness with the right components for tools, memory, and context management can still achieve strong performance.

The key insight is that ALE Claw reaches comparable accuracy to much larger harnesses while using significantly fewer tokens, dollars, and minutes. It does this through a repeating action cycle with a hard turn budget, and crucially, through context compaction paired with disk-backed memory—when the transcript grows too large, it flushes important information to persistent memory before compacting, then uses memory search and retrieval tools to access that information later. The harness also includes typed tools for files, shell, web, vision, GUI, memory operations, and subagent delegation.

This creates an interesting tension with my increasingly elaborate harness design, and I'm starting to see how the "Does the Harness Matter?" philosophy might push back against over-engineering. But if a candidate generation pulls in many archived candidates, diagnostics, and trial evaluations, the session could grow long—so I'd apply ALE Claw's principle of flushing key findings to disk-backed memory before compacting context. Since I'm using fresh context per candidate anyway, the real payoff is at the meta layer: my durable memory (memory.md / episodic.jsonl) already serves as that flush-before-compaction target across rounds, which validates the pattern for my EvolutionHistory.

The bigger takeaway is adopting a strict minimalism discipline: the harness should stay as lean as possible with every component opt-in (defaulting to flat archive + random/score_child_prop, no islands or MAP-Elites unless explicitly enabled), and I need to measure whether each piece actually delivers value. Start with the bare essentials—Ralph + anti-stop + holdout gate—and only layer on QD or islands if they demonstrably outperform the baseline.

I should also add explicit config knobs for per-session turn caps and tool-call limits to bound inner-agent cost and prevent a single candidate generation from spiraling. For the inner agent's tool surface, I can restrict it to only what's necessary: reading and editing the strategy file, plus reading history and diagnostics—deliberately disabling tools that could enable reward-hacking or let it escape the harness's control.

There's a tension between HyperAgents' finding that full tools + reset-protection enables capability, and ALE Claw's minimal typed tool surface approach. The resolution is to keep the mechanical reset-allowlist as the correctness guard (so full tools stays safe), but use disabled_tools as a cost and focus optimization—turning off tools irrelevant to editing a C++ heuristic like web, GUI, vision, and delegation, plus the evaluator which the harness owns. This frames reset-protection as the safety guard and disabled_tools as tuning.

The real takeaway from ALE Claw is the minimalism and cost discipline: a minimal MVP harness (external budget, anti-stop, reset-protection, holdout gate, flat archive, simple selection) as Phase 1, with QD, islands, MAP-Elites, attribution, and convergence as opt-in Phase 2 layers, each validated against the baseline. I should also be direct that ALE Claw is mostly an inner-loop single-task harness—its biggest lesson is the cost discipline, not new evolution machinery—and the user will appreciate that intellectual honesty rather than overstating what it adds to the outer-loop structure.

The README is detailed enough to extract these lessons, but I should fetch agent_loop.py to ground the loop mechanics, compaction, and budget claims with actual code, since the user's pattern suggests they value checking code to refine the plan.
==== Thinking ====

I have the ALE Claw README from the search results. Let me ground the loop/compaction/budget mechanics in the actual code before updating the plan.

This one is different in kind: ALE Claw is an *inner-loop, single-task* harness (context compaction, memory-flush-before-compaction, durable memory, bounded turns), and its headline finding — from the companion "[Does the Harness Matter?](https://agents-last-exam.org/blogs/harness-matters)" — is that a **minimal** harness matches much bigger ones at far fewer tokens/dollars/minutes when the model is held fixed. The code confirms the mechanics: a mutable message loop with proactive+reactive compaction, `_maybe_flush_memory()` *before* compaction, byte-stable post-compaction re-anchoring for cache hits, and **DONE-based termination with a bare-text nudge** (never "stop when tool calls stop"). Let me fold these in — and use them to restructure the plan into a measured minimal core plus opt-in layers.

Done. ALE Claw is the inner-loop counterpart to everything else (single long-horizon task, not evolution), so its biggest gift is a discipline rather than new search machinery — and it prompted the most useful restructuring yet.

**What ALE Claw changed**

- **The plan is now phased into a measured minimal core + opt-in layers.** This is the direct consequence of "[Does the Harness Matter?](https://agents-last-exam.org/blogs/harness-matters)" (minimal harness ≈ big harness at far fewer tokens/$/min) plus A-Evolve's "Harness Updating Is Not Harness Benefit":
  - **Phase 1 core (must work first):** external budget + anti-stop, manifest-allowlist reset, protected eval + seed-disjoint holdout Gate, **flat** archive, **random/score_child_prop** selection, durable memory, harness convergence, the `EvolutionEngine` interface with a `GreedyEngine` control. This alone fixes "agent stops early / writes its own scores / keeps noise."
  - **Phase 2 opt-in (default OFF, each measured vs the core):** MAP-Elites, islands, gridless novelty, curiosity/modifiable selection, attribution. A layer stays only if it beats the minimal baseline on holdout-confirmed gain — so complexity has to earn its place.
- **New "Inner-session contract" section** adopting ALE Claw's loop hygiene for each `Agent.prompt(...)`: minimal tool surface (read/edit the allowed file + `memory_search`/`memory_get`; no evaluator/git/web — scoring stays harness-owned), `max_turns`/`thinking_level` caps, **explicit DONE termination + bare-text nudge** (never "stop when tool calls stop"), a **byte-stable cached prefix** re-anchored after the run, and **robust failure capture** (agent crash/timeout/truncation → invalid candidate, loop continues — crash-proof with the `finally` reset).
- **Memory sharpened** to ALE Claw's pattern: append-only durable memory with **flush-before-loss** and `memory_search`/`memory_get` access, and history given to the agent via search tools rather than full dumps (cost).
- **Cost section** now lists the per-session knobs (`max_turns`, `thinking_level`, `disabled_tools`) and states plainly that the minimal core is the cheapest config while opt-in layers must justify their spend.
- **Validation** now asserts the minimal baseline runs with all opt-in layers off, an **inner-session crash becomes an invalid candidate without killing the loop**, and the engine swaps cleanly — then each opt-in layer is enabled and confirmed.

Honest read: ALE Claw added no new evolution structure (it's a within-task loop), but its minimalism evidence is the right corrective to a plan that had been accreting machinery across AEvo → HyperAgents → QD → A-Evolve. The plan now leads with the smallest thing that solves your actual problem and treats the fancy QD/island/attribution parts as measured upgrades.

Across all six references the design is stable: an external, budget-and-convergence-owning driver runs a pluggable evolution engine (minimal flat-archive core, optional QD/islands) in bounded, DONE-terminated agent sessions, protected by a manifest-allowlist reset, keeping nothing until it survives a seed-disjoint holdout. Ready to implement on your word, or I can keep refining.

---

**User**

Check this code to improve your plan:
https://github.com/NousResearch/hermes-agent 

---

**Cursor**

Let me read the uploaded Hermes doc and pull the repo in parallel.

Hermes is a large personal-assistant platform, so most of it (messaging gateways, TUI, multi-backend) is irrelevant to an evolution harness — but its **closed learning loop** is the transferable core. Let me ground that in two repo files before updating.

The **Curator (skill lifecycle)** is the directly transferable piece. Let me read that section and the surrounding memory/state details.

The Curator is the standout transferable idea — a background skill-lifecycle manager with usage telemetry, active→stale→archived auto-transitions, **never-delete (archive + restorable + backups)**, **pinning**, and **provenance gating** (`created_by: agent` only). None of the other five references covered lifecycle/GC of a growing archive. Let me re-read the current canonical plan, then fold in Hermes' learning-loop ideas.

Now I'll fold Hermes' learning-loop ideas into the plan via targeted edits. Starting with the overview, title, and sources.

Now the new lifecycle-curation/learning-loop section, inserted before the workspace layout.

Now update the workspace layout, cost section, todos, and validation to reflect the curator, sweeps, and FTS history.

Now the todos: engine SweepEngine, observe FTS5/two-tier memory, mechanism skills library, a new curator todo, and validation.

Let me verify the new section renders cleanly.

I reviewed the Hermes Agent repo (it's a 204k-star *personal-assistant platform* — gateways, TUI, voice, multi-backend — so ~90% doesn't transfer). The one part that genuinely applies to an evolution harness is its **closed learning loop**, and the standout is something none of the previous five sources covered: **lifecycle management of a growing archive**. I folded four ideas into the [plan](.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md).

What I took from Hermes and added:

- **Curator / lifecycle GC** (`agent/curator.py` → new `evolver/curator.py` + section). An open-ended archive + a self-editing mechanism grows unbounded, bloating cost and diluting parent selection. Hermes' curator is the missing garbage-collector: per-item usage telemetry (`selection_count`, `children`, `last_improvement`, `state`, `pinned`), `active→stale→archived` transitions, **never-delete (archive + restorable + pre-run backup)**, **pinning** of the best lineage, and **provenance gating** (`created_by: agent` only). I split it cleanly into our phasing — pin + never-delete + provenance are cheap **core hygiene**; telemetry auto-transitions + LLM review are **opt-in**.
- **Zero-context-cost `SweepEngine`** (a cost lever, which you keep asking about). Hermes lets the agent express multi-step work as one script = "zero-context-cost turns." Mapped to an opt-in **non-LLM** `EvolutionEngine`: the meta agent expresses a sweep/ablation once, the harness expands it to N candidates with **no per-candidate agent call** (CPU eval only) — reserving expensive agent sessions for *structural/novel* proposals. Ties directly into your existing SWEEP/ABLATE modes.
- **FTS5-searchable history** (`hermes_state.py` SessionDB). `evolution.db` becomes searchable so the agent can ask "have we tried X? why did family F fail?" — powering de-anchoring and pathology/redundancy detection, with LLM-summarized recall to stay cheap.
- **Two-tier curated memory + skills-from-experience.** Memory becomes episodic-append-only **plus** a curated semantic tier consolidated on a periodic nudge; the meta agent distills reusable search tactics into an opt-in `mechanism/skills/` library (description-first).

Also updated: overview/title/sources (now "seven sources"), the missing-list, workspace layout (`curator.py`, `engine/sweep.py`, `candidates/.archive/`, FTS `evolution.db`, `skills/`), the cost section, the todos (new `curator` task; `SweepEngine`/FTS/skills annotations), and validation (curator pins-best/archives-stale/never-deletes, FTS query returns a prior attempt, SweepEngine yields candidates with zero agent calls).

Net effect: this is mostly a **cost + hygiene + anti-collapse** layer — it keeps the active population and prompt bounded so the open-ended archive doesn't become its own scaling problem, with zero risk to the locked contract.

Want me to keep refining the plan, or is it ready to start building the Phase-1 minimal core?

