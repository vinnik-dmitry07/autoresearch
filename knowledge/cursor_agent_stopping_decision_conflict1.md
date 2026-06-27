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

---

**User**

add this to meta agent

---

**Cursor**

Let me look at the file you have open to find the meta agent section before I add this.

This is the AEvo Figure showing the **meta-agent's procedure (Π) evolving over rounds** (P0→P6), with each meta-edit producing a generation of candidates and the best score climbing 0.15→0.25→0.30→0.35 — and notably P5–6's aggressive de-anchoring *regressing* from P4. You want this worked example baked into the meta agent. Since `meta_skill.md` doesn't exist yet, I'll add it to the meta-agent spec in the plan. Let me grab the exact current text first.

I'll add a dedicated "Meta-agent procedure evolution" section seeding the worked example, and reference it from the `mechanism-files` todo.

Let me verify the new section renders cleanly.

Added. I baked the figure into the meta agent's spec in the [plan](.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md) as a new **"Meta-agent procedure evolution (AEvo worked example)"** section, since `meta_skill.md` doesn't exist yet.

What I encoded from the figure:

- **The trajectory as a few-shot menu.** The meta agent edits the *procedure Π itself* (not the strategy), and Π improves as a lineage of edits with the best score climbing 0.15→0.25→0.30→0.35. Each P-step is listed as an example move **mapped to our domain**: P0 best-parent rewrite → `GreedyEngine`/`best`; P1 Pass@K + local scoring → bounded Pass@K + quick-gate scoring; P2 fix observation parsing → make `observe.py`/`feedback_spec.md` surface actionable signal; P3 extend refinement horizon → more inner turns; P4 drop stale feedback + diversify → de-anchor via `novelty`/`curiosity` + Curator pruning.
- **The cautionary half — P5–6 regress from P4.** This is the most useful part: aggressive de-anchoring (task-profile/skeleton prompts, fresh final sampling) made things *worse*. So I tied it to two lessons:
  1. **Meta-edits are first-class candidates, gated like any strategy** — the holdout Gate + harness-update attribution decide whether a Π-edit precedes a real gain, and the driver **rolls back / throttles** ones that don't (exactly why P5–6 wouldn't survive).
  2. **It's a menu, not a script** — the meta agent picks/combines moves based on Φ (plateau, coverage, diversity, attribution), consistent with the lean-skill choice.

I also updated the `mechanism-files` todo so `meta_skill.md` is seeded with this Π-evolution menu (including the "P5–6 de-anchor REGRESSES" note).

One judgment call: I kept it as a textual menu rather than copying the image into the repo, since the meta agent reads prose skills. If you'd rather I also drop the figure into `evolve/mechanism/` as a visual reference (or save it under the repo `assets/`), say so and I'll add it when we build.

---

**User**

You are the MetaAgent.

Look at the current system and the AEvo paper:

https://arxiv.org/html/2605.13821v1

Main problem to solve:

Even with prompts encouraging long-horizon search, coding agents often stop early once local improvements become difficult. The agent’s internal stopping decision can conflict with the external evolution budget. AEvo addresses this by placing the coding agent inside an explicit evolution harness, where rounds, candidates, records, and evaluation feedback are maintained outside the agent’s local decision loop.

Do not summarize the paper. Use it to evolve the current system.

Your task:

Map the current system into AEvo terms:
candidate
evaluator
archive / ledger
mutation mechanism
feedback signal
external budget owner
agent-local stopping point
Identify the exact gap between the current system and AEvo:
what is still controlled by the coding agent
what is controlled externally
where early stopping can still happen
where reward hacking or self-scoring can happen
Propose the smallest architectural change that makes early stopping impossible:
the external driver owns rounds
the agent only receives bounded tasks
candidates are recorded outside the agent
evaluation is run by the harness
the agent cannot declare the run finished
Split the result into:
Phase 1 minimal core
Phase 2 optional upgrades
rejected ideas
For every proposed component, specify:
exact file/module to add or edit
what failure mode it closes
how to test it
what new risk it introduces
End with:
revised canonical plan
decision log
implementation checklist

Important constraints:

Do not add architecture for its own sake.
Do not let the coding agent own stopping.
Do not let the coding agent own evaluation.
Do not let the coding agent write official scores.
Prefer a small external harness over stronger prompts.
The output must be an implementation-grade plan, not a literature summary.

---

**Cursor**

I'll act as the MetaAgent and produce an implementation-grade revision. First I need exact ground truth on the current system so every component cites real files. Let me explore the repo and key contract files in parallel.

Now the contract details: how scores get written to `results.tsv`, the locked keep rule, the stop language, and `forbidden_check`.

Let me read the core contract sections of `program.md` and locate `forbidden_check`.

Found `forbidden_check` at `durak/cmake/check_forbidden.cmake`. Let me read it and the candidate surface of the strategy file.

I now have full ground truth. Key facts that shape the implementation-grade plan:

- **Candidate surface:** `durak/src/strategy_heuristic.cpp` (the only agent-edited file; carries the `kComplexity` manifest at lines 26–28).
- **Evaluator:** `durak/build/simulate.exe` via `scripts/triage.bat` (gates smoke/b4/quick/medium/**dual**/full); build `durak/build.bat fast`; `forbidden_check` = `durak/cmake/check_forbidden.cmake`; tests = ctest.
- **Self-scoring today:** the agent / `scripts/run_batch*.py` append rows to `results.tsv` themselves (e.g. `run_batch114.py:51-59`), and "locked" files are only **policy**-locked (`program.md:157-166`), not write-protected. `NEVER STOP` is prose (`program.md:416`) and `## Search mode` is now CLOSURE/PLATEAU.
- **Keep rule (full only):** `program.md:246-251`.

Let me rewrite the canonical plan as an implementation-grade document.

Let me verify the rewritten plan is well-formed.

Done — I rewrote the canonical [plan](.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md) as an implementation-grade document, grounded in the real files. Here is the MetaAgent output.

## Current system in AEvo terms
- **Candidate** = an edit to `durak/src/strategy_heuristic.cpp` (only agent-edited file; complexity manifest at lines 26–28) — today it lives in the working tree, not a record.
- **Evaluator** = `durak/build/simulate.exe` via `scripts/triage.bat`; build `durak/build.bat fast`; guard `durak/cmake/check_forbidden.cmake`; tests via ctest — locked **by policy only**.
- **Archive/ledger** = `results.tsv` (schema `program.md:294-311`) — append-only, **agent-written**.
- **Mutation mechanism** = prose modes EXPLORE/PIVOT/ABLATE/EXPLOIT/COMBO/SWEEP in `program.md`.
- **Feedback** = `durak/triage.log` + `results.tsv` + `--mode features` (`scripts/diagnose_b4_features.py`).
- **External budget owner** = **none** (`LOOP FOREVER`/`NEVER STOP` are prose).
- **Agent-local stopping point** = the CLOSURE/PLATEAU verdict (~0.689 vs B4).

## The exact gap
- **Agent-controlled:** the loop, the stop decision, the mutation choice, **writing official scores** (`run_batch114.py:51-59`), the keep decision, commits.
- **External but policy-only:** simulator/metric/thresholds/`forbidden_check`/tests (`program.md:157-166` says "may NOT edit" — but the agent has write access).
- **Early stopping:** the agent declares closure; `NEVER STOP` (`program.md:416`) can't prevent it because it's a prompt.
- **Reward hacking / self-scoring:** the agent appends its own numbers to `results.tsv` and could edit the "locked" evaluator.

## Smallest change that makes early stopping impossible
One external process `evolver/` that: (1) **owns rounds+budget** (`loop.py`); (2) gives the agent **one bounded task per call** (`agents.py`, `Agent.prompt`, DONE-terminated, no eval/git tools); (3) **records candidates outside the agent** as git diffs (`protect.py` → `evolve/candidates/`); (4) **runs eval itself** and writes `scores.json` (`evaluate.py`), regenerating `results.tsv`; (5) has **no stop sentinel** — an inner "we're done" just ends that session, the driver starts the next round. Termination = `max_rounds`/`cost_cap` only.

## Phase 1 — minimal core
Eight components, each with file / failure-mode-closed / test / new-risk in the plan: **C1** driver (`loop.py`/`cli.py`/`config.py`), **C2** bounded sessions (`agents.py`), **C3** allowlist git-reset (`protect.py`+`manifest.yaml`), **C4** harness-owned eval+scores (`evaluate.py`), **C5** candidate store + flat archive + selection (`store.py`/`select.py`), **C6** seed-disjoint holdout (`triage.bat dual`) + locked keep rule, **C7** observation + durable memory (`observe.py`, **no convergence stop**), **C8** lean mechanism files (anti-stop + Π-evolution menu).

## Phase 2 — optional (default OFF, measured vs core)
EvolutionEngine interface + GreedyEngine control (to *prove* the archive helps) → QD (MAP-Elites/islands/novelty/curiosity/modifiable) → cost/hygiene (SweepEngine, Curator, FTS5+two-tier memory+skills) → convergence (behind a `min_rounds` floor) + attribution + parallel worktrees.

## Rejected
Stronger prompts only; agent-written scores; an agent `COMPLETE` sentinel; convergence that stops before a budget floor; agent-editable evaluator/metric/selection; greedy-as-default (control only); the B5 memory branch.

## Decision log (key)
External driver over prompts · strictly memoryless · mechanical reset over trust · holdout gate kills noise · flat archive (not greedy) in core · **no convergence stop in Phase 1 so early stopping is impossible** · all QD/curator deferred and measured.

## Implementation checklist
`scaffold → protect → evaluate → store-select → observe → agents → mechanism-files → loop → integrate-validate`, then Phase 2.

One deliberate tightening from the prior plan, per your "no architecture for its own sake": I demoted the pluggable `EvolutionEngine` interface, MAP-Elites, islands, curator, sweep, and FTS out of the core into measured Phase-2 layers, and **removed convergence-based stopping from Phase 1 entirely** (budget is the sole terminator) so the core cannot re-introduce the very early-stop it's meant to kill.

Want me to switch to agent mode and build the Phase-1 core?

---

**User**

You are the MetaAgent.

Check the HyperAgents paper and use it to improve the current AEvo-style harness plan.

Paper path:

@c:\Users\Asus\AppData\Local\Temp\Rar$DIa41740.3932\paper.tex

Do not summarize the paper. Treat it as adversarial evidence against the current plan.

Focus on:

open-ended exploration
archive design
parent selection
whether greedy best-only hill-climbing is wrong
population diversity
stepping-stone candidates
meta-agent self-improvement
compute-aware planning
failure modes from ablations

Your task:

Identify which current plan assumptions the paper contradicts.
Identify which current plan assumptions it confirms.
Decide whether the plan should:
keep only the best candidate
keep all valid candidates
use a branching archive
use population-based parent selection
Compare:
greedy best-parent search
random valid-parent search
score-weighted parent search
novelty-weighted parent search
child-count-penalized parent search
Produce exact plan edits:
archive data model
parent selection policy
candidate lineage representation
meta-agent mechanism-editing scope
evaluation / rollback policy
Split additions into:
Phase 1 mandatory
Phase 2 optional
not worth copying
Add validation tests:
plateau does not force stop
archive keeps valid regressions as possible stepping stones
parent selection does not collapse to the single current best
official best still follows locked evaluation rules

Important:

Do not blindly add every HyperAgents feature. Adopt only mechanisms that directly solve plateau escape, early stopping, or diversity collapse.

---

**Cursor**

I'll re-read the HyperAgents paper as adversarial evidence, targeting the exact sections the task names. Let me locate the key claims and ablation numbers first.

The attached temp path isn't resolving (the RAR temp likely got cleaned). Let me locate the paper elsewhere — there's a `knowledge/paper.txt` in the repo and an uploads folder.

`knowledge/paper.txt` is the FAIR/Meta paper (the HyperAgents source). Let me extract the adversarial evidence — ablations, archive/parent-selection design, open-endedness, compute-awareness.

Let me pull the exact ablation evidence and the parent-selection formula.

Let me get the parent-selection formula and the ablation outcome numbers.

Let me read the exact parent-selection formula and the "modifying parent selection" caution.

Let me read the "modifying parent selection" result (the caution on editable selection) to ground that risk precisely.

I have the decisive evidence. The most important adversarial finding: HyperAgents' **"w/o open-ended exploration" ablation is exactly greedy replace-the-best hill-climbing, and it produces "little to no progress"** (`paper.txt:199,150`). The paper also **selects parents on the validation/holdout score, not the training score** (`paper.txt:208`), and **keeps parent-selection + evaluator fixed for "stability and safety"** (`paper.txt:324,913-915`). Let me read the current plan body to make precise edits.

The evidence is decisive and adversarial in one specific way: my current plan still hedged on the archive (a Phase-2 `p2-measure-engine` todo to "measure whether the flat archive beats greedy"). The paper **already ran that ablation** — greedy replace-the-best = "little to no progress" — so the archive must be **mandatory**, not measured. Let me make the precise edits.

Now the two affected todos and the validation section.

Let me verify the densest edit (C5/C6) renders cleanly.

Done — I treated `knowledge/paper.txt` (the HyperAgents/DGM-H source) as adversarial evidence and tightened the [plan](.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md). The decisive finding is that the paper **already ran the experiment my plan was deferring**.

## What the paper contradicts in the current plan
- **It contradicts treating the archive as something to "measure vs greedy" in Phase 2.** DGM-H's *w/o-open-ended* ablation **is** greedy "replace the predecessor, make it the next parent," and it yields *little to no progress* (`paper.txt:199,150`). So the open-ended branching archive is **mandatory Phase-1**, and `GreedyEngine` drops to a **one-shot ablation** that reproduces the known failure — not a gate. (Edited C5, the `p2-measure-engine` todo, decision log.)
- **It contradicts selecting parents on the search-bank score.** The paper measures the selection performance term on the **validation set** precisely because the judge overfits (`paper.txt:208`). So `alpha_i` must be the **holdout-confirmed** score, not the seed-0 search bank. (Edited C5/C6 + decision log.)
- **It contradicts listing `random` and `score_child_prop` as co-equal.** Evidence ranks **score_child_prop (0.532) > modifiable (0.491) > random (0.428)** (`paper.txt:915`). `score_child_prop` is the default; `random` is an ablation. (Edited C5 + `store-select` todo.)
- **It contradicts MAP-Elites/islands being "HyperAgents-derived."** DGM-H uses a **flat** probabilistic archive (`paper.txt:374-425`); grids/islands are cited QD literature, not its method. I demoted them to Phase-2 "not from this paper."

## What it confirms
- External, population-based open-ended loop to avoid premature convergence/local optima (`paper.txt:187`).
- **Keep all valid candidates** (IsValid = compiled child added to archive, regressions included — `paper.txt:447-448`).
- **Branching archive + probabilistic parent selection** with child-count novelty.
- **Compute-aware planning** — meta agent gets remaining iterations (`paper.txt:192`) → our `iterations_left`.
- **Lock parent-selection + evaluator** "for stability and safety"; modifiable selection is preliminary and doesn't beat handcrafted (`paper.txt:324,913-915`).
- **Lean initial agent** to avoid prematurely constraining search (`paper.txt:192`) → lean skills.
- **Seed durable memory + performance tracking** — these were *emergent* over 100 iterations in the paper (`paper.txt:287-290`); we have one domain and a smaller budget, so we seed them rather than wait for emergence.

## Decisions (your four questions)
- Keep only the best candidate → **No** (it's the ablation that fails).
- Keep all valid candidates → **Yes** (mandatory, regressions included).
- Branching archive → **Yes** (mandatory).
- Population-based parent selection → **Yes**, `score_child_prop` default on the holdout score.

## Selection comparison
- **Greedy best-parent** = the *w/o-open-ended* ablation → local-optimum trap, little/no progress. **Reject** (ablation only).
- **Random valid-parent** → 0.428; robust, keeps search open, weak. **Keep as ablation/sanity.**
- **Score-weighted** (sigmoid perf vs top-3 frontier) → exploits; alone it drifts toward greedy. **Half of the default.**
- **Child-count-penalized** `1/(1+n)` → the exploration term that stops collapse onto the best. **Other half.**
- **score_child_prop = score × child-penalty** → 0.532, the winner. **Default.**
- **Novelty-weighted (behavioral b(x))** → not in the paper's method; QD extension → **Phase 2** only if flat still plateaus.

## Exact plan edits (now in the plan)
- **Archive data model** — `meta.json{id,parent_id,base_commit,round,valid,n_children,alpha,search_score,point_rate_b4,lower_ci,complexity,status}`; never delete in Phase 1.
- **Parent-selection policy** — `alpha_mid=mean(top-3 alpha)`, `s=sigmoid(10·(alpha−alpha_mid))`, `h=1/(1+n)`, `p∝s·h`, sample K with replacement over valid; `alpha` = holdout.
- **Candidate lineage** — diff vs `base_commit` + snapshot; branch = restore parent snapshot then run; chain via `parent_id`.
- **Meta mechanism-editing scope** — meta edits only `evolve/mechanism/**`; parent-selection + evaluator locked (manifest-excluded); `select_policy.json` editable only as Phase-2 opt-in.
- **Evaluation / rollback** — IsValid = build+forbidden+ctest+non-empty; select on holdout; reported best advances only via the locked keep rule; **rollback resets the tree but never deletes the candidate** (it stays a stepping stone).

## Phase split
- **Phase 1 mandatory (from this paper):** open-ended branching archive (keep all valid), `score_child_prop` on the holdout, lineage tracking + `n_children`, `iterations_left`, seeded durable memory/performance-tracking.
- **Phase 2 optional:** gridless behavioral novelty/curiosity, `modifiable` UCB/softmax selection, full metacognitive self-modification, MAP-Elites/islands (explicitly *not* from this paper).
- **Not worth copying:** multi-domain co-optimization, co-evolving the task distribution, agent-editable evaluator/selection in core, Turing-complete "edit any code" scope, waiting for memory/tracking to *emerge*.

## Validation tests added
The four you named are now first-class: (1) plateau doesn't force stop (stubbed flat evaluator still runs full budget); (2) archive keeps valid regressions as selectable stepping stones (never deleted); (3) selection draws ≥2 distinct parents and never always-the-best; (4) official best advances only under the locked holdout keep rule (+`evo-N` tag).

One honest caution, per your "don't blindly add everything": the paper's headline gains (0→0.71) come from a **fresh, wide search space** over 100 iterations; our space is memoryless and already well-mapped, so the archive's job here is mainly **plateau escape + much stronger closure evidence**, not a large score jump. That's why everything beyond the mandatory archive stays measured and opt-in.

Want me to switch to agent mode and build the Phase-1 core?

---

**User**

You are the MetaAgent reviewing the actual HyperAgents codebase.

Repo:

https://github.com/facebookresearch/HyperAgents

Inspect implementation, not only README or paper.

Focus on:

main loop
git handling
candidate representation
parent selection
protected paths
rollback
diff generation
agent tool permissions
crash handling
how evaluation is isolated
how invalid candidates are handled

Your task:

List the concrete implementation patterns the code proves.
For each pattern, classify it:
MUST ADOPT
ADOPT WITH MODIFICATION
OPTIONAL EXPERIMENT
DO NOT COPY
IRRELEVANT
Pay special attention to:
git reset / path protection
diffs versus base commit
applying parent patches
empty diff handling
valid parent filtering
parent selection modes
inline git config
reset in finally blocks
Update the current plan with exact edits:
protection module
version-control module
parent-selection module
candidate metadata format
lineage format
failure recovery logic
Add acceptance tests:
candidate cannot modify evaluator
candidate cannot modify tests
candidate cannot modify metric
empty diff is skipped
crash still resets workspace
invalid parent is removed from parent pool
official score is harness-owned
End with:
revised architecture diagram in text
implementation checklist
decision log

Important:

Do not trust agent instructions for safety. Prefer mechanical safety through git reset, allowlists, and harness-owned evaluation.

---

**Cursor**

I'll inspect the actual HyperAgents implementation. Let me pull the core files (main loop, git utils, parent selection, meta-agent runner) in parallel.

`generate_loop.py` is the 1184-line main loop. Let me grep it for the exact patterns the task targets.

Rich implementation detail. Let me read the three core regions: container reset/lineage helpers, the `generate()` function, and the main loop.

Now the `generate()` function — the core candidate generation, protection, and valid_parent logic.

The `generate()` function confirms the two-layer protection (`reset_paths_to_commit(paths=["domains/"])` inside the agent run + `git reset --hard` + `clean -fd` in `finally`) and empty-diff skip. Let me read the main loop orchestration.

I now have the actual implementation patterns. Two findings sharpen the plan materially: (1) HyperAgents protects via a **denylist** (`reset_paths_to_commit(paths=["domains/"])`) because its agent edits *everything but* the evaluator — our case is the inverse, so we need an **allowlist** reset; and (2) `valid_parent` is set `False` when the child agent's **process exit code ≠ 0** (`generate_loop.py:923-924`, `595`), i.e. success is the process result, never the agent's self-report. Let me read the current end of the plan to make precise edits.

I have the full picture. Now I'll fold the code-proven patterns into the plan with exact edits. Starting with the protection component (C3) — adding the precise git mechanism and the denylist→allowlist inversion.

Now refining the `protect` todo with the exact primitives the code proves.

Now the store/select todo — adding `valid_parent` pruning and the exit-code success rule.

Now let me find where Phase-1 components end so I can insert the consolidated "exact module specs" section.

The Phase-1 components are detailed. Now I'll insert a consolidated, code-grounded "exact module specs" section (the six modules the task asks for) right before Phase 2.

Now adding the code-specific decision-log entries.

Now the text architecture diagram (the task asks for a text version), placed before the decision log.

Let me verify the inserted sections render cleanly.

I inspected the actual implementation (`utils/git_utils.py`, `generate_loop.py`, `run_meta_agent.py`, `select_next_parent.py`), not just the paper, and folded the findings into the plan. Here's what the code proves, classified.

## Concrete patterns the code proves (classified)

**MUST ADOPT**
- **Reset in `finally` (crash/Ctrl-C safe).** Every container op wraps `try/except Exception` + `finally: git reset --hard root_commit; git clean -fd` (`generate_loop.py:687-696`, `:164-173`, `:284`). This is the crash-proof workspace guarantee.
- **Success = process exit code, not self-report.** `parent_agent_success = exec_result.exit_code == 0` (`:595`). The agent's claim is never read.
- **Empty-diff skip.** `run_eval = file_exist_and_not_empty(model_patch.diff)` (`:610-611`) — no diff, no eval.
- **Diff vs base, Windows-correct.** `git diff <commit>` + untracked via `git diff --no-index NUL <f>`, already branching `devnull='NUL' if os.name=='nt'` (`git_utils.diff_versus_commit`).
- **Inline git identity.** `git -c user.name=… -c user.email=… commit`; "nothing to commit" → returns current hash; never touches global config (`git_utils.commit_repo`).
- **Invalid-parent pruning.** Selection skips `valid_parent==False`; on child failure the *parent* is marked invalid (`:923-924`, `select_next_parent.py`).
- **Validity gate before eval.** `run_commands_to_check_compilation` runs before scoring (`:614`) → our `build.bat fast`/`forbidden`/`ctest`.

**ADOPT WITH MODIFICATION**
- **Path protection is a *denylist*** (`reset_paths_to_commit(git_dir, base, paths=["domains/"])`, `run_meta_agent.py`) because their agent edits everything *except* the evaluator. Our agent edits one file → **invert to an allowlist**: `git checkout <base> -- . ':(exclude)strategy_heuristic.cpp'` + `clean -fd -e …`.
- **Lineage via patch-replay** (`get_patch_files` → `apply_diffs` → `git apply --reject`). `--reject` can leave partial state → we **branch by restoring the full-file snapshot** (exact), keep the patch for lineage only.
- **Staged eval** (small sample → full only if `all(score>0)`, ThreadPool with cancel-all-on-failure, `:634-680`) → maps to our `quick → dual → full` gates.
- **Eval isolation = Docker container per generation** with `timeout NNN` → our evaluator has no network/LLM, so allowlist reset + locked CPU binary + subprocess timeouts replaces it.

**OPTIONAL EXPERIMENT**
- Parallel candidates via git worktrees (Phase-2 analog of their per-generation containers).
- `modifiable` parent selection (paper's preliminary result; beats random, not handcrafted).

**DO NOT COPY**
- `no_archive → parent_selection='latest'` greedy default (`:737`) — this is our **ablation**, never a runtime path.
- `DONOTTOUCH_<repo>` double-copy — a `no_selfimprove` baseline artifact.

**IRRELEVANT**
- Polyglot per-task container, DGM `problem_statement` plumbing, ensemble-scoring container.

## Two findings that changed the plan
1. **Denylist → allowlist inversion.** HyperAgents keeps everything but `domains/`; we must keep *only* the allowlist file. Smaller trusted surface, stricter.
2. **Exit-code success.** Validity is the subprocess result, never the agent's word — now explicit in the candidate metadata and selection.

## Exact plan edits made
Updated `aevo_harness_for_autoresearch_b2455abd.plan.md`:
- **New section "HyperAgents code — exact module specs"**: protection, version-control, parent-selection, candidate-metadata, lineage, failure-recovery, eval-isolation — each grounded with code line refs and a classification.
- **C3** now states the exact allowlist git commands and the denylist→allowlist rationale; **`protect` todo** lists `reset_all_but_allowlist` / `diff_versus_commit` (NUL) / `commit_inline` / `reset_to_base` / `tag_evo`.
- **C5 / `store-select` todo**: `meta.json` mirrors HyperAgents `metadata.json` fields; selection skips `valid_parent==False`; `parent_agent_success = exit_code==0`; child-fail → parent invalid.
- **New "Acceptance tests (mechanical safety)"**: the 7 you listed (evaluator/tests/metric immutable, empty-diff skipped, crash resets, invalid-parent pruned, harness-owned score).
- **New "Architecture (text)"**: ASCII loop with protection points `[P]`.
- **Decision log**: added allowlist-not-denylist, exit-code-success, snapshot-over-patch, Docker→git-reset.

The plan is still in plan mode (only the markdown was edited). Want me to switch to agent mode and start building Phase 1 (`scaffold` → `protect` → `evaluate`), or refine the plan further first?

---

**User**

You are the MetaAgent.

Check Ralph loop code:

https://github.com/snarktank/ralph

Use it to improve the current evolution-harness plan.

Questions to answer directly:

What is the computational cost model?
How do we prevent reward collapse?
Should quality-diversity use MAP-Elites, gridless novelty, island populations, or something else?

Inspect the code, especially:

external loop
iteration budget
fresh agent context
persistent files
git commits
task selection
stopping condition
progress memory
test/typecheck loop

Your task:

Identify what Ralph validates:
external loop owns budget
fresh context per iteration
memory through files and git
simple feedback loop
Identify what Ralph must not be copied for our system:
greedy checklist completion
COMPLETE sentinel
no open-ended archive
no diversity mechanism
no protected scoring
no population
Build the cost model:
LLM sessions per round
meta-agent sessions per round
inner-agent sessions per round
evaluator CPU cost
prompt/cache cost
cost of Pass@K
cost of MAP-Elites/islands if enabled
Design anti-collapse protections:
reward hacking prevention
diversity collapse prevention
reward saturation handling
noise-overfitting prevention
archive bloat prevention
Decide quality-diversity architecture:
flat HyperAgents archive
pluggable parent selection
gridless novelty selection
coarse MAP-Elites
island populations
meta-editable selector
Do not force one QD method prematurely. Design a pluggable population interface:
container API
selector API
descriptor API
admission policy
replacement policy
migration policy if islands are enabled
Split into:
Phase 1 minimal core
Phase 2 optional measured QD upgrades
rejected Ralph ideas
Add validation tests:
budget cannot be ended by agent
reward-hacking edit is reset
archive diversity does not collapse silently
scalar plateau triggers novelty/de-anchor mode
cost cap halts externally
reported best still requires locked full evaluation

Important:

Ralph is a skeleton, not the final search algorithm. Copy its external-loop discipline, not its greedy stop condition.

---

**Cursor**

I'll inspect the actual Ralph code to ground the cost model and QD decisions. Let me pull the loop script, prompt, and README.

`prompt.md` is lowercase. Let me fetch it to see the inner-loop task selection, stop condition, and feedback loop.

I have the full Ralph implementation. Let me check the current plan's section structure so I place the new sections (cost model, anti-collapse, QD interface) correctly.

Let me read the current Validation and Decision-log tail to get exact anchors for the additions.

I have everything needed. Now I'll fold the Ralph findings into the plan. First, the pluggable population interface (the QD decision), inserted before Rejected ideas.

Now the cost model and anti-collapse sections (the two direct questions), inserted before the text architecture.

Now the Ralph-specific rejected ideas, attached to the existing COMPLETE-sentinel rejection.

Now the Ralph decision-log entries.

Finally, the Ralph-driven validation tests.

Let me verify the new sections are well-formed.

Inspected the actual Ralph code (`ralph.sh`, `prompt.md`, `README.md`) and folded it into the plan. Direct answers first.

## What Ralph's code proves (copy this)
- **External loop owns the budget** — `for i in $(seq 1 $MAX_ITERATIONS)` in bash, default 10; the agent is a subprocess inside it (`ralph.sh`). This is our driver.
- **Fresh context per iteration** — each loop pipes `prompt.md` into a brand-new CLI process; the only memory is files + git. This is our memoryless `Agent.prompt` per candidate.
- **Memory through files + git** — `prd.json` (state), `progress.txt` (append-only learnings + a "Codebase Patterns" header), git history, `AGENTS.md`. Maps to our `state.json` / `observations/` / `mechanism/memory.md` / candidate store.
- **Simple feedback loop before commit** — typecheck/test, "do NOT commit broken code… broken code compounds across iterations" (`prompt.md`, README). Maps to our build+forbidden+ctest+triage gate.

## What Ralph must NOT be copied (reject)
- **`COMPLETE` sentinel** — `ralph.sh` exits when it greps `" COMPLETE "` in agent output (`prompt.md` "Stop Condition"). That is the agent-owned stop AEvo forbids.
- **Greedy checklist** — pick highest-priority `passes:false`, mark `passes:true`, finish when all pass. Assumes a finite task list; our search is open-ended.
- **Agent self-marking + `--dangerously-allow-all`/`--dangerously-skip-permissions`** — the agent scores itself with unrestricted tools = self-scoring, zero protection.
- **No archive / no population / no diversity** — one feature branch, linear `progress.txt`.

## Three direct answers
- **Cost model** (new `## Cost model`): LLM sessions/run = `R*K + ceil(R/M)` (K inner + meta every M rounds); evaluator is CPU-only = `K*c_quick + n_adv*(c_dual+c_full)` (staged, most candidates pay only the cheap gate); static prefix is cache-served so Pass@K is sublinear in $ / linear in CPU; **MAP-Elites/islands add CPU (descriptor extraction) and rounds, not tokens**; `cost_cap` + `R` enforced externally each round, invisible to the agent.
- **Reward collapse** (new `## Anti-collapse protections`): five modes mapped to mechanisms — reward hacking → allowlist reset + harness scores [P1]; diversity collapse → flat archive + `1/(1+n_children)` + a `b(x)` spread monitor in `Phi` (never silent) [P1]; reward saturation → de-anchor mode after `P` flat rounds [P1 prompt / P2 novelty]; noise/overfit → seed-disjoint holdout + `lower_ci` [P1]; archive bloat → active-set cap [P1] then Curator [P2].
- **QD architecture** (new `## Pluggable population interface`): **don't force one method.** Phase-1 = flat archive (only scheme the paper validates). Everything else implements one interface (container/selector/descriptor + admission/replacement/migration) and is a measured Phase-2 upgrade. **Recommended order: gridless novelty → coarse MAP-Elites → islands → meta-editable** (novelty needs no bins, so it's robust to noisy descriptors; grids/islands fragment noisy cells; meta-editable doesn't beat handcrafted per `paper.txt:913-915`).

## Plan edits made
- New sections: **Cost model**, **Anti-collapse protections**, **Pluggable population interface**.
- **Rejected ideas**: added Ralph's `COMPLETE` sentinel, greedy checklist, self-marking + dangerous flags, single-branch memory.
- **Decision log**: "adopt Ralph's external-loop discipline, reject its stop"; "QD pluggable, default flat, ordered novelty→MAP-Elites→islands→meta-editable".
- **Validation**: added 4 Ralph-driven tests (agent can't end budget, diversity doesn't collapse silently, scalar plateau triggers de-anchor, cost cap halts externally); the reward-hacking-reset and locked-full-eval tests were already present.

Still plan-only (markdown edits). Want me to switch to agent mode and start Phase 1 (`scaffold` → `protect` → `evaluate`), or keep refining the plan?

---

**User**

You are the MetaAgent.

Check this code to improve the current plan:

https://github.com/A-EVO-Lab/a-evolve

Do not summarize the framework. Extract architectural primitives that should change our harness.

Focus on:

evolution engine interface
workspace abstraction
trial runner
history
version control
solve / observe / evolve / gate / reload loop
rollback
holdout validation
plugin architecture
how regressions are rejected
how experiments are recorded

Your task:

Identify which parts of our current plan should become shared primitives:
EvolutionEngine
TrialRunner
EvolutionHistory
VersionControl
AgentWorkspace
Gate
Reload
Decide whether the current loop should be hard-coded or engine-based.
Define the engine interface:
inputs
outputs
candidate records
evaluation ownership
whether engine can manage its own evaluation
cycle-end hooks
Add a manifest of evolvable layers:
what the inner agent may change
what the meta-agent may change
what is locked
how allowlists are enforced
Add a holdout Gate:
search-bank evaluation
holdout-bank evaluation
seed-disjoint confirmation
rollback on failed holdout
official best update only after holdout confirmation
Add convergence owned by the harness:
budget exhaustion
holdout-confirmed improvement rate
coverage saturation
diversity collapse
no agent-local “done” signal
Split into:
Phase 1 mandatory primitives
Phase 2 optional engines
rejected complexity
Add acceptance tests:
engine swap works
holdout failure rolls back
seed-overfit candidate is not kept
manifest prevents illegal edits
convergence is decided by harness, not agent
history is append-only and queryable

Important:

The output should be a corrected implementation plan. Every abstraction must have a concrete reason to exist.

---

**Cursor**

I'll ground this in the actual A-Evolve code. Let me locate any local copies and pull the repo's file tree in parallel.

Let me find the key module paths in the repo tree, and read the local A-Evolve doc.

The tree is a single JSON line. Let me parse it to list the Python/Markdown module paths.

Found the core primitives under `agent_evolve/engine/` and `agent_evolve/contract/`. Let me read the engine interface, the loop, manifest, versioning, and history.

I have the engine, loop, versioning, and history. The base loop notably **delegates gate/rollback to engines, not the core** — important for us. Let me get the contract (manifest/workspace), trial runner, types, and the gating/rollback that engines use. (Re-fetching manifest, which timed out.)

I now have all the A-Evolve primitives in code. The decisive insight: A-Evolve's **loop owns shared primitives while the engine owns only `step()`**, but it lets engines own evaluation (`manages_own_evaluation`), end the run (`StepResult.stop`), and gate via pluggable verifiers — the exact authorities we must keep in the harness. Let me read the current acceptance/decision sections to anchor precise edits.

I have everything grounded in code. Now I'll fold the A-Evolve primitives into the plan. First, the consolidated shared-primitives mapping with the corrected engine interface, inserted before Phase 2.

Now the A-Evolve-driven acceptance tests.

Now the A-Evolve decision-log entries.

Finally, the rejected A-Evolve complexity.

Now let me sharpen the Phase-2 convergence bullet to enumerate the harness-owned signals (the user listed them) and tie to A-Evolve's `egl_window`.

Let me refine the two affected todos so the manifest-enforcement and corrected engine interface are captured there too.

Let me verify the structure is intact and the new section renders.

Inspected the actual A-Evolve code (`agent_evolve/engine/{base,loop,versioning,history,trial}.py`, `contract/{manifest,workspace}.py`, `types.py`, `unified/verifiers/stagnation_rollback.py`) and corrected the plan. The framework's real architecture is cleaner than the docs suggest — and three of its choices are too permissive for us.

## The core architectural lesson (and where we diverge)
A-Evolve splits responsibilities precisely: the **loop owns the expensive shared primitives** (versioning, observation, history, trial runner, snapshot, reload, convergence) and the **engine owns only `step()`** (`engine/base.py`, `engine/loop.py`). We adopt that split. But A-Evolve hands the *strategy* three authorities we must keep in the harness:
- `EvolutionEngine.manages_own_evaluation` lets an engine score itself → **we lock it `False`**.
- `StepResult.stop` lets the engine end the run (`loop.py` honors it) → **we drop the field**.
- Gate/rollback are *opt-in engine verifiers* (`stagnation_rollback.py`), not central → **we centralize the holdout gate in the harness**.

Plus: `contract/manifest.py`'s `evolvable_layers` is a **declaration honored by convention — it enforces nothing**. That's the biggest correction: we feed it into the allowlist git-reset so it's *mechanically* enforced.

## Direct answers
- **Which parts become shared primitives** (new `## Shared primitives (A-Evolve)` section): VersionControl→`protect.py`; Gate+TrialRunner→`evaluate.py` (harness-owned, mandatory); EvolutionHistory→`store.py`+`observe.py` (append-only, queryable); AgentWorkspace+Manifest→`manifest.yaml`+`protect.py` (enforced); Reload→snapshot-restore in `loop.py`. Each has a one-line concrete reason; none added without one.
- **Hard-coded or engine-based loop?** **Hard-coded in Phase 1 behind an engine-shaped seam; extract the `EvolutionEngine` ABC only in Phase 2** when a second strategy (Greedy/QD) exists. One strategy doesn't justify the ABC.
- **Engine interface** (corrected, with a code block in the plan): `step(workspace, observations, history) -> StepResult{mutated, summary, metadata}` — no `trial`, no `stop`; `manages_own_evaluation = False` (locked); `on_cycle_end(accepted, score)` advisory only; candidate records appended to history; **evaluation ownership = harness**.
- **Manifest of evolvable layers**: inner→`strategy_heuristic.cpp`; meta→`mechanism/**`; everything else locked; `reload_strategy=cold`; enforced by reset (declaration + mechanism).
- **Holdout Gate** (already C6, now tied to A-Evolve's `Verdict(accept, rollback, reason)`): search-bank → seed-disjoint holdout → confirm → rollback-on-fail (candidate preserved, à la A-Evolve's history-preserving `rollback`) → official best updates only after holdout.
- **Harness-owned convergence** (Phase-2 bullet, now enumerated): budget exhaustion [P1]; holdout-confirmed improvement rate (A-Evolve `_is_score_converged(window, epsilon)` on the *holdout* curve); coverage saturation; diversity collapse (flags/switches mode, doesn't stop); **no agent-local "done"**; all behind `min_rounds`.

## Plan edits made
- New section **Shared primitives (A-Evolve)** with the primitive→module→reason mapping and the corrected engine interface code block.
- **Rejected ideas** += engine-managed eval, `StepResult.stop`, `git config` on the main repo, full workspace surface / hot reload / branch-merge tree, engine ABC in Phase 1.
- **Decision log** += loop/engine split with eval+gate+convergence pulled into harness; ABC is Phase 2; manifest = declaration+enforcement; rollback preserves rejected candidate.
- **Acceptance tests** += engine swap works, manifest prevents illegal edits, history append-only/queryable, holdout-failure rolls back (candidate preserved), convergence is harness-decided.
- Sharpened the **Phase-2 convergence** bullet and the `scaffold`/`p2-measure-engine` todos.

Still plan-only (markdown). Want me to switch to agent mode and start Phase 1 (`scaffold` → `protect` → `evaluate`), or keep refining?

---

**User**

You are the MetaAgent.

Check this code to improve the current plan:

https://github.com/rdi-berkeley/agents-last-exam/blob/main/ale_run/agents/ale_claw/README.md

Use it as a minimalism and inner-loop discipline check.

Do not add complexity unless it clearly beats the minimal harness.

Focus on:

bounded agent loop
turn budget
context compaction
memory flush before compaction
durable memory
tool surface
done signal
nudge behavior
cost efficiency
minimal harness philosophy

Your task:

Identify what ALE Claw contributes to our plan:
bounded inner sessions
max turns
explicit DONE termination
memory flush before compaction
compact context
durable searchable memory
minimal tool surface
cost controls
Identify what ALE Claw does not solve:
outer evolution
population search
parent selection
reward hacking by evaluator edits
open-ended plateau escape
Use ALE Claw to simplify the plan:
define Phase 1 minimal core
move nonessential components to Phase 2
reject expensive machinery until measured
Define the inner-session contract:
allowed tools
disabled tools
max turns
timeout behavior
DONE protocol
bare-text nudge protocol
crash/truncation handling
what happens when no diff is produced
Define memory:
append-only episodic memory
compact summaries
searchable history
flush-before-loss rule
no full archive dumps into prompt
Add cost policy:
per-session cap
per-round cap
total cost cap
token logging
eval-time logging
opt-in layers must prove value
Add validation tests:
inner session timeout becomes invalid candidate
crash does not kill harness
context compaction does not lose key state
no agent can end outer run with DONE
Phase 1 runs with all optional layers off

Important:

Use ALE Claw as a corrective against over-engineering. The plan should become smaller, not larger, unless a feature closes a named failure mode.

---

**Cursor**

I'll ground this in the actual ALE Claw code. Let me pull the README and the repo tree to find the harness loop.

The README confirms the minimal philosophy and points to the loop. Let me read the actual main loop and config to ground the inner-session contract (turn budget, DONE, nudge, compaction, flush).

Config confirms the minimalism (default `disabled_tools=["web_search"]`, cheap `summary_model` for compaction/flush, per-phase thinking levels, and crucially "the episode wall-budget is orchestration-owned"). Let me grep the main loop for turn budget, DONE, nudge, compaction, and flush.

The loop confirms the exact inner-session discipline: **DONE ends only the inner session** ("max_steps in the outer consumer is the other ceiling", line 347), a **bare-text nudge** prevents silent termination on tool-less turns, **memory flush runs pre-API before compaction** (flush-before-loss), and compaction is both reactive (on overflow error) and proactive. Crucially, "the episode wall-budget is orchestration-owned." This is a minimalism corrective. Let me read the current Phase-1 components and loop to apply precise simplifications.

This is a clear minimalism corrective. The decisive simplification: ALE Claw proves the **inner session** needs only a bounded loop + DONE + nudge + flush + compaction, and that the **wall-budget is orchestration-owned**. By the user's own rule ("reject expensive machinery until measured"), the **meta-agent self-modification does not close the early-stop failure mode** (the driver does) — so it should move to Phase 2, shrinking Phase 1. Let me read the canonical loop, cost model, and text architecture to apply this consistently.

I have the full picture. This is a genuine simplification pass. I'll (1) add a compact ALE Claw minimalism section, (2) expand C2 into the precise inner-session contract, (3) tighten C7 memory, (4) extend the cost policy, and (5) move the meta-agent to Phase 2 consistently. Starting with the minimalism section and the inner-session contract.

Now expanding C2 into the precise inner-session contract grounded in `agent_loop.py`.

Now tightening C7 with the ALE Claw memory rules.

==== Thinking ====
I'm revising the C8 mechanism files section, which documents the evolve skill, meta skill, feedback spec, next goal, family map, and memory files that address over-anchoring and missing anti-stop contracts.

The new approach consolidates this to Phase 1 with just two files: evolve_skill.md (which encodes the anti-stop rule preventing early exit) and memory.md (the durable append-only log). The per-round goal and feedback format are now folded directly into the observation layer by observe.py, while the meta skill menu and family map move to Phase 2 with the meta-agent. The key test remains that an inner "we're done" signal still produces a candidate, but now the files are human-authored and locked during Phase 1 rather than edited by the agent. The risk of over-prescriptive skills constraining search space still applies, so keeping the skills minimal remains critical.
==== Thinking ====

Now reducing C8 to the two Phase-1 mechanism files.

Now updating the Phase-1 architecture diagram to drop the meta session.

Now the canonical plan: workspace line and the loop steps (dropping the meta step from Phase 1).

Now updating the cost model so Phase 1 is `K` inner sessions only (meta is Phase 2), and adding the explicit cost-policy caps/logging.

==== Thinking ====
I'm refining the anti-collapse mechanism to work as a deterministic harness switch at the P1 level rather than relying on meta-prompt logic. When reward saturation occurs—meaning the search score plateaus after P rounds without improvement—the system switches into de-anchor mode, where it stops using scalar feedback and instead navigates using non-scalar signals like the localized B4 residual.
==== Thinking ====

Now making the plateau de-anchor a deterministic Phase-1 switch (no meta-agent needed).

Now the text architecture — dropping the meta lines for Phase 1.

Now adding the meta-agent as a measured Phase-2 layer. Let me read the Phase 2 bullets.

Now updating the affected todos (agents, mechanism-files, loop) to reflect the Phase-1/Phase-2 split.

Let me fold the meta-agent into the Phase-2 attribution todo (they're coupled), keeping the todo list from growing.

Now updating the checklist reference and adding the decision-log + validation entries.

Finally, the ALE Claw validation tests. Let me read the Validation tail to anchor.

Let me verify the meta-agent references are all consistently Phase-2 now and the structure is intact.

Almost all references are consistent. Let me fix one decision-log line that still implies `meta_skill.md` is core.

Let me do a final structure check.

Inspected the actual ALE Claw code (`harness/agent_loop.py`, `config.py`) and used it as a minimalism corrective — the plan's **Phase 1 got smaller**, not larger.

## What ALE Claw proves (and we adopt for the inner session only)
The loop confirms the exact inner-loop discipline: a `max_turns` ceiling; **DONE that ends only the inner session** ("max_steps in the outer consumer is the other ceiling"); a **bare-text nudge** so a tool-less/DONE-less turn isn't silently killed (`_maybe_nudge_bare_text`); **memory flush before compaction** (`_maybe_flush_memory` pre-API); reactive+proactive compaction; a cheap `summary_model`; minimal `disabled_tools`; and — decisively — "the **episode wall-budget is orchestration-owned**." It's single-task, single-agent, self-terminating, so it can only ever be the *inner session*, never the search.

## What ALE Claw does NOT solve (so these outer parts stay — each closes a named failure mode)
Outer loop = early-stop; archive = plateau; selection = local optimum; allowlist reset = reward-hacking via evaluator edits; branching + de-anchor = plateau escape; holdout gate = noise. None of these exist in ALE Claw, which is why our outer machinery earns its place.

## The headline simplification (please sanity-check this one)
By your own rule ("reject expensive machinery until measured"), the **meta-agent self-modification does not close the early-stop failure mode — the driver does** — so I **moved it to Phase 2**. Consequences applied consistently across the plan (architecture diagrams, loop, cost model, todos, decision log):
- **Phase 1 mechanism files: 6 → 2** (`evolve_skill.md` + `memory.md`); `feedback_spec`/`next_goal` folded into Φ; `meta_skill`/`family_map` deferred.
- **Phase-1 LLM cost: `K` inner sessions/round** (no meta session); `M` is now a Phase-2 knob.
- **Plateau de-anchor is a deterministic harness switch** in Phase 1 (no LLM meta-edit).

This reverses some earlier meta-agent emphasis, so tell me if you'd rather keep a minimal meta session in Phase 1.

## What I added (grounded, not bulk)
- **Inner-session contract** (expanded C2): allowed/disabled tools, `max_turns`, wall-timeout→invalid, DONE-is-inner-only, bare-text nudge, crash/truncation→invalid, empty-diff→skip.
- **Memory rules** (C7): append-only episodic, bounded Φ, searchable history, **flush-before-loss**, and **no full-archive dumps into the prompt**.
- **Cost policy** (Cost model): per-session / per-round / total `cost_cap`, token + eval-time logging, opt-in-must-prove-value.
- **ALE Claw validation tests**: timeout→invalid candidate; crash doesn't kill harness; compaction preserves key state; no agent ends the outer run with DONE; **Phase 1 runs with all optional layers OFF**.

Net effect: Phase 1 is now driver + bounded inner session + allowlist protection + harness eval/scores + mandatory flat archive/selection + holdout gate + observe/memory + 2 mechanism files. Everything else is Phase 2, default OFF, measured.

Want me to switch to agent mode and start building Phase 1 (`scaffold` → `protect` → `evaluate`), keep refining, or revisit the meta-agent decision first?

---

**User**

You are the MetaAgent.

Check this code to improve the current plan:

https://github.com/NousResearch/hermes-agent

Most of this repo may be irrelevant. Do not force-fit personal-assistant features into an evolution harness.

Look specifically for transferable mechanisms related to:

closed learning loops
memory lifecycle
skill lifecycle
curator / garbage collection
searchable history
archive management
telemetry
pinning
stale item handling
backups
never-delete policy
provenance gating

Your task:

Identify what is transferable.
Identify what is irrelevant.
Identify what is dangerous or too complex.

Focus on the archive problem:

An open-ended evolution harness creates many candidates, memories, skills, selectors, and mechanism edits. Without lifecycle management, the archive bloats, prompts get expensive, parent selection gets diluted, and stale ideas keep resurfacing.

Design a lifecycle layer:

active candidates
stale candidates
archived candidates
pinned best lineage
restorable archive
never-delete policy
pre-run backups
provenance tracking
selection_count
children_count
last_improvement
last_selected
state transitions

Split into:

Phase 1 cheap hygiene:
pin best lineage
never delete
archive stale records
provenance metadata
searchable history
Phase 2 optional:
curator agent
LLM-assisted memory consolidation
skill-library extraction
auto-stale transitions
telemetry-driven pruning

Also evaluate whether a non-LLM SweepEngine should exist:

meta-agent writes one sweep spec
harness expands it to many candidates
evaluator runs them without per-candidate agent calls
useful for ablations and parameter sweeps
not a replacement for structural agent proposals

Add validation tests:

best lineage is pinned
stale records are archived, not deleted
archived records remain restorable
provenance is recorded
search can retrieve prior failed attempts
SweepEngine creates candidates with zero agent calls
curator cannot delete official history

Important:

Hermes is mostly a cost, hygiene, and memory-lifecycle source. Do not copy chat, voice, UI, or assistant-platform features unless they directly improve the evolution harness.

---

**Cursor**

I'll ground this in the actual Hermes repo, focusing only on the lifecycle/hygiene mechanisms. Let me check the local upload and pull the repo tree + AGENTS.md.

Let me find the lifecycle-relevant modules in the tree and grep the AGENTS.md for the specific mechanisms.

The Curator is exactly the lifecycle layer the user wants. Let me read the Curator section, the SQLite/FTS history, the config, and the memory manager.

The Curator section gives the complete lifecycle model: provenance-gated (`created_by:'agent'` only), never-delete (archive is max action, restorable), pinned-exempt, pre-run tar.gz backups, telemetry sidecar (`use_count`/`last_activity_at`/`state`/`pinned`), and FTS5 searchable history. Let me read the exact current text of the hygiene todo and rejected-ideas tail to anchor edits.

I have everything grounded. Now folding the Hermes lifecycle layer into the plan. First, the consolidated lifecycle section (with the SweepEngine decision), inserted before Rejected ideas.

Now adding the cheap Phase-1 hygiene component (C9).

Now updating the store-select and p2-cost-hygiene todos.

Now the Phase-2 cost/hygiene bullet.

Now the archive-bloat anti-collapse bullet.

Now the Hermes-driven validation tests.

Now the decision log and rejected ideas. Let me find the decision log tail.

Now adding the Hermes decision-log entries.

Now the Hermes rejected-ideas entries.

Let me verify the new sections render cleanly.

I inspected the actual Hermes repo (the `Curator (skill lifecycle)` system in `AGENTS.md`: `agent/curator.py` + `agent/curator_backup.py`, the `tools/skill_usage.py` telemetry sidecar, and the FTS5 `SessionDB` in `hermes_state.py`) and folded the transferable parts into the plan. Here is the MetaAgent verdict.

## Transferable / irrelevant / dangerous

- **Transferable (adopted):** Hermes' Curator *is* the lifecycle layer we need — a telemetry-driven `active/stale/archived` state machine + `pinned`, **provenance gating** (it only touches `created_by:'agent'`), a **never-delete** policy (max action = archive to `.archive/`, restorable), **pre-run tar.gz backups** + `rollback`, and an FTS5 **searchable history**. Its invariants map 1:1 to our archive problem.
- **Irrelevant (ignored):** chat/voice, desktop slash palette, skin engine/spinner, Telegram/Slack messaging, the Kanban board, external memory-provider plugins (honcho/mem0/…), profiles/cron/gateway.
- **Dangerous / too complex (deferred or constrained):** the **LLM review pass** and **background interval daemon** — an LLM that auto-archives can bury a stepping stone, and a daemon races the loop. So curation becomes Phase-2, **synchronous at round boundaries, suggest-only, provenance-gated, never deletes**.

## What changed in the plan

- New **`## Archive lifecycle layer (Hermes Curator)`** section: the lifecycle record (`state`, `pinned`, `selection_count`, `children_count`, `last_selected`, `last_improvement`, `created_by`, `provenance`), deterministic round-based transitions, hard invariants, and the Phase-1/Phase-2 split.
- New **Phase-1 component C9 (cheap hygiene)** + folded the same into the `store-select` todo: pin best lineage, **selection pool = active+pinned** (the actual de-dilution), provenance + `evolve/usage.json` counters, never-delete + conservative archive of dead records (unpinned, `children_count==0`), pre-run backup, minimal searchable `history.jsonl`.
- The expensive Curator (LLM review, auto-stale, memory consolidation, skill-library, FTS5) stays **Phase 2**, measured vs the P1 baseline; updated the `p2-cost-hygiene` todo, the Phase-2 bullet, and the archive-bloat anti-collapse line.
- **SweepEngine decision: yes — Phase-2 engine behind the `EvolutionEngine` interface.** One sweep spec → many parameter candidates, **zero `Agent.prompt` calls**, maps onto your existing `scripts/sweep_atk_trump.py` + SWEEP mode + the `kParameterCount` manifest. It refines *around* an accepted structure, is **not** a replacement for structural agent proposals, and every sweep candidate still clears the full holdout gate (`lower_ci` + dual).
- Added the 7 **validation tests** (best lineage pinned; stale archived-not-deleted; archived restorable; provenance recorded; search retrieves prior failed attempts; SweepEngine = 0 agent calls; curator cannot delete official history), plus **decision-log** and **rejected-ideas** entries.

The key safety line: the curator may only touch `created_by:'agent'|'sweep'` records and can **never** touch official history (`scores.json`, `results.tsv`, `evo-N` tags, locked contract, human mechanism files) — provenance gating is what makes "curator cannot delete official history" mechanical rather than trust-based.

The plan now has all five external sources integrated (AEvo, HyperAgents, Ralph, A-Evolve, ALE Claw, Hermes). Want me to switch to agent mode and start building Phase 1 (`scaffold → protect → evaluate → store-select`), or is there another source/section you want to refine first?

---

**User**

You are the MetaAgent consolidating the canonical evolution-harness plan.

Sources already considered:

AEvo
HyperAgents paper
HyperAgents code
Ralph
A-Evolve
ALE Claw
Hermes Agent

Your job is to compress, not expand.

Do not add new features unless they remove an existing component or close a named failure mode.

Named failure modes:

coding agent stops early
agent-local DONE conflicts with external budget
reward hacking
self-written scores
evaluator/test modification
reward saturation
diversity collapse
noise-overfitting
context bloat
archive bloat
cost blow-up
stale ideas resurfacing
untestable meta-churn

Produce the final plan in this structure:

Irreducible Phase 1 core

Only include components necessary to solve the core problem.

Required candidates:

external driver owns rounds and budget
bounded inner-agent sessions
manifest allowlist
git reset protection
harness-owned evaluation
append-only candidate records
flat open-ended archive
simple parent selection
seed-disjoint holdout Gate
durable searchable memory
cost cap
harness-owned convergence
Phase 2 optional measured upgrades

Only include if they can be tested against Phase 1:

MAP-Elites
gridless novelty
islands
modifiable selector
curator agent
SweepEngine
skill library
attribution analysis
Explicitly rejected ideas

Reject or defer:

prompt-only “NEVER STOP”
agent-owned scoring
greedy best-only hill-climbing
COMPLETE sentinel for outer run
unprotected evaluator access
full archive dumps into prompt
complex QD before baseline works
personal-assistant platform features
Final architecture

Specify:

module layout
data model
run loop
candidate lifecycle
parent-selection interface
evaluation pipeline
holdout Gate
memory system
cost policy
convergence policy
Acceptance tests

Write tests for:

early stopping impossible
illegal edits reset
self-scoring impossible
holdout overfit rejected
crash safe
timeout safe
archive append-only
best lineage pinned
cost cap enforced
optional layers disabled by default
optional layers measured against baseline
Implementation order

Give the smallest implementation slice that proves the thesis:

no QD first
no islands first
no curator agent first
no modifiable selector first
only minimal external harness first
Cursor implementation prompt

End by writing the exact prompt I should paste into Cursor Agent mode to implement Phase 1.

Important:

The final answer should be implementation-grade. No literature summary. No vague advice. No untested architecture accretion.

---

**Cursor**

I'll read the full current plan so the consolidation preserves every hard-won decision while compressing.

This is now a consolidation/compression pass. I'll rewrite the canonical plan file into the requested 7-section structure, collapsing the per-source analysis and the 25-bullet decision log into tight implementation-grade decisions, while preserving the frontmatter and the ordered todos verbatim.

Let me verify the rewrite is well-formed and check the final size.

Frontmatter intact, body compressed. Let me confirm the file ends cleanly with the closed Cursor prompt block.

Done. The canonical plan is consolidated and compressed from **447 → 233 lines**, restructured into exactly the 7 sections you specified. Nothing was added; the per-source narrative was removed.

**What I compressed away** (the literature/accretion): the `HyperAgents code — exact module specs`, `Shared primitives (A-Evolve)`, `ALE Claw — minimalism check`, and `Archive lifecycle (Hermes)` prose sections, the duplicate Mermaid + text architecture diagrams, the 25-bullet decision log, and the separate `Validation` section that duplicated the acceptance tests. The implementation-grade specifics they carried (exact git commands, the `run_batch114.py` regexes, the `meta.json` schema, the keep rule) are preserved in **§4 Final architecture** and in the ordered **todos** block, which I left verbatim.

**Final structure:**
- **§1 Irreducible Phase 1 core** — your 12 required candidates, one line each (file — failure mode — test), plus the near-zero-cost archive hygiene folded into store/select.
- **§2 Phase 2** — the 8 measured upgrades (+ engine ABC, meta-agent, evidence-convergence), all default-OFF, kept only on holdout-gain-per-dollar.
- **§3 Rejected** — your 8 rejects, each one line.
- **§4 Final architecture** — module layout, data model, run loop, candidate lifecycle, parent-selection interface, evaluation pipeline, holdout Gate, memory, cost policy, convergence policy.
- **§5 Acceptance tests** — your 11, mapped to the tiny-budget harness.
- **§6 Implementation order** — Slice 0 (`scaffold→protect→evaluate`) → Slice 1 (`store-select→observe→agents→mechanism`) → Slice 2 (`loop→integrate-validate`); no QD/islands/curator/modifiable/meta first.
- **§7 Cursor prompt** — a complete paste-able Agent-mode prompt with the hard invariants, all 9 modules, the workspace, and the slice-by-slice build + assertions.

**One reconciliation worth flagging:** your Phase-1 required list includes *harness-owned convergence* and *durable searchable memory*, which my prior draft had partly in Phase 2. I split them by **ownership vs sophistication**: Phase 1 gets the *ownership* (convergence = budget-only, harness-decided, never the agent; memory = append-only + `history.jsonl` substring search), and Phase 2 gets the *sophistication* (evidence-based convergence behind a `min_rounds` floor; FTS5 index). So both now appear as core items #12 and #10.

Want me to switch to Agent mode and execute Slice 0 (`scaffold → protect → evaluate`)?

