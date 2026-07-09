# Evolving AEvo Plan

**User:** Anonymous  
**Created:** 6/27/2026 2:38:30  
**Updated:** 7/2/2026 15:03:59  
**Exported:** 7/2/2026 15:06:54  
**Link:** [https://chatgpt.com/c/6a3f9a10-f02c-83e8-8a30-8ac75153a989?mweb_fallback=1](https://chatgpt.com/c/6a3f9a10-f02c-83e8-8a30-8ac75153a989?mweb_fallback=1)  

## Prompt:
6/27/2026, 2:38:28 AM

You are the MetaAgent, tell me how to evolve the attached plan

## Handoff summary 

This conversation evolved an **AEvo-style external evolution harness plan** for a coding-agent optimization system where the core failure is: the coding agent stops early when local improvements get hard, even though the external evolution budget is not exhausted. The uploaded Cursor export shows the plan was repeatedly refined using AEvo, HyperAgents/DGM-H, Ralph, A-Evolve, ALE Claw, and Hermes, then compressed into a final implementation-grade canonical plan. 

### Core decision

Do **not** try to fix early stopping with stronger prompts like “NEVER STOP.”
Build a small **external driver harness** that owns:

* rounds
* budget
* candidate recording
* evaluation
* official scores
* keep/rollback decisions

The coding agent only receives **bounded candidate-generation tasks**. It may say “done” for the local task, but it cannot declare the full search finished.

### Current system mapped into AEvo terms

* **Candidate:** edit to `durak/src/strategy_heuristic.cpp`.
* **Evaluator:** `durak/build/simulate.exe` via `scripts/triage.bat`; build with `durak/build.bat fast`; protected by `durak/cmake/check_forbidden.cmake` and ctest.
* **Archive / ledger today:** `results.tsv`, but it is currently agent-written, which is a problem.
* **Mutation mechanism:** prose search modes in `program.md` such as EXPLORE, PIVOT, ABLATE, EXPLOIT, COMBO, SWEEP.
* **Feedback:** `durak/triage.log`, `results.tsv`, and feature diagnostics.
* **External budget owner today:** none; “NEVER STOP” is only prose.
* **Agent-local stopping point:** CLOSURE / PLATEAU verdict around the current best.

### Exact gap

The coding agent still controls too much:

* It can decide to stop.
* It can write official scores.
* It can choose mutations and keep decisions.
* It can potentially edit policy-locked files unless mechanical protection is added.

The plan’s main fix is to make the harness, not the agent, own evaluation and continuation.

### Phase 1 minimal core

Build only the irreducible harness first:

1. `evolver/loop.py`, `cli.py`, `config.py`
   External driver owns `max_rounds`, `cost_cap`, and loop continuation.

2. `evolver/agents.py`
   Bounded agent sessions with limited task scope, explicit local DONE, no global stop authority.

3. `evolver/protect.py` + `evolve/manifest.yaml`
   Mechanical git-reset allowlist. Only permitted files survive candidate generation.

4. `evolver/evaluate.py`
   Harness runs build, forbidden check, ctest, triage, and writes official score artifacts.

5. `evolver/store.py` + `evolver/select.py`
   Candidate store, flat open-ended archive, parent selection.

6. Holdout gate using seed-disjoint evaluation
   Search-bank result can suggest escalation, but official best only advances after holdout-confirmed locked keep rule.

7. `evolver/observe.py` + append-only `history.jsonl`
   Durable memory and compact feedback. No convergence stop in Phase 1 except budget exhaustion.

8. `evolve/mechanism/*`
   Lean meta/inner skills, anti-stop rules, and AEvo-style procedure-evolution menu.

### Critical HyperAgents correction

Greedy best-only hill-climbing is rejected. HyperAgents/DGM-H evidence was treated as adversarial: the “without open-ended exploration” ablation corresponds to greedy replace-best search and gets stuck. Therefore:

* Keep **all valid candidates**, including regressions.
* Use a **branching archive**.
* Use parent selection over valid candidates, not only the current best.
* Official best still follows locked evaluation rules.
* Regressions can remain stepping stones but cannot become official best without passing the keep rule.

Default parent selection should be `score_child_prop`:

```text
p(parent) ∝ sigmoid(holdout_score_relative_to_top_frontier) × 1 / (1 + n_children)
```

So the search exploits good parents but avoids collapsing onto the single best.

### Phase 2 optional upgrades

Default OFF. Add only if Phase 1 works and the upgrade improves holdout-gain-per-dollar:

* `EvolutionEngine` abstraction.
* MAP-Elites / gridless novelty / curiosity selection.
* Island populations.
* Modifiable parent selection.
* SweepEngine for zero-agent-call scripted sweeps.
* Curator / archive lifecycle.
* FTS5 searchable memory.
* Evidence-based convergence behind a `min_rounds` floor.
* Meta-agent self-improvement with attribution.

### Rejected ideas

Do not implement these as core:

* Stronger prompts instead of external control.
* Agent-written scores.
* Agent-owned `COMPLETE` sentinel.
* Agent-editable evaluator / metric / tests.
* Greedy best-only default.
* Early convergence stop before budget floor.
* Overbuilt QD/islands/curator before the minimal harness works.
* Opening the B5 memory/stateful branch; stay strictly memoryless for this plan.

### Final canonical plan state

The Cursor agent consolidated the canonical plan from **447 lines to 233 lines** into 7 sections:

1. Irreducible Phase 1 core.
2. Phase 2 measured upgrades.
3. Rejected ideas.
4. Final architecture.
5. Acceptance tests.
6. Implementation order.
7. Paste-ready Cursor Agent prompt.

The prior literature narrative was removed, but the concrete implementation details were preserved: module layout, candidate schema, git-reset protection, official score ownership, keep rule, parent-selection policy, and validation tests.

### Implementation order

Proceed in slices:

```text
Slice 0: scaffold → protect → evaluate
Slice 1: store-select → observe → agents → mechanism
Slice 2: loop → integrate-validate
```

Do **not** start with MAP-Elites, islands, curator, modifiable selection, or a full meta-agent. The first success criterion is a tiny-budget run where the external harness continues despite plateau language and the agent cannot write official scores.

### Acceptance tests the next agent must preserve

* Plateau language from the agent does not stop the run.
* Archive keeps valid regressions as future stepping stones.
* Parent selection does not collapse to only the current best.
* Official best advances only under the locked keep rule.
* Agent cannot edit evaluator, tests, triage, or score files.
* Agent crash/timeout becomes invalid candidate, not run failure.
* Harness-owned `results.tsv` or equivalent official score export is regenerated from structured score artifacts.
* Budget exhaustion, not agent choice, ends Phase 1.

[Attachment: aevo_harness_for_autoresearch_b2455abd.plan(1).md]

## Response:
6/27/2026, 2:38:29 AM

I’ll treat the uploaded plan as the canonical artifact and focus on evolution pressure: what to simplify, what to harden mechanically, and what to defer so the first implementation proves the thesis rather than becoming another research project.

> **Considering file citation and reference**
>
> The user's asking about evolving an attached plan. I see it's already in the prompt and file, though I need to ensure proper citation. The file's loaded, but the citation doesn’t include line numbers, making it tricky. Should I use Python? I can cite the file at top-level, though. I'll decide soon!
>
> **Considering reading attached file with Python**
>
> I’m wondering if I should just read the attached file using Python. It could give me exactly what I need. I’ll just go ahead and do it to make sure I’m working with the most accurate data. Let’s see if that helps clarify things!
>
> **Reading file content from path**
>
>
> **Analyzing the plan and proposing evolution**
>
> I think I'll break the analysis into sections like "verdict," "evolution plan," and "concrete changes." The user likely expects an answer from "MetaAgent" with context. I'll suggest the current plan isn’t final and needs evolution. I should mention its concrete components, avoid tables, and focus on evolving the phases. I’ll also point out contradictions like "strictly memoryless" versus durable memory definitions.
>
> Thought for 42s

MetaAgent verdict: the attached plan is already strong and close to implementation-grade. The next evolution should **not** add more AEvo/QD/meta-agent ideas. It should turn the plan from a “canonical architecture” into a **crash-safe, executable contract** with fewer ambiguous authority boundaries. The core thesis is correct: the harness, not the coding agent, must own rounds, budget, scoring, keep/rollback, and termination. `aevo_harness_for_autoresearch_b2455abd.plan.md`

## Main evolution direction

Evolve it from:

> “Build Phase 1 harness with 12 components.”

to:

> “First prove 5 non-negotiable invariants with a stubbed agent, then attach Cursor.”

The strongest vNext change is to introduce a **Phase 0 contract harness** before real Cursor SDK integration.

Phase 0 should run with scripted/stub agents only and prove:

1. agent says `DONE` / `PLATEAU` but outer loop continues;
2. agent edits locked files but they are discarded;
3. agent writes `scores.json` / `results.tsv` but harness regenerates them;
4. crashing candidate becomes invalid, not fatal;
5. valid regressions stay in archive and remain selectable.

Only after that should real `agents.py` call Cursor. This avoids mixing the hardest integration problem with the core proof.

## Biggest flaw to fix

Your current reset/clean policy can accidentally destroy the harness’s own artifacts.

The plan says candidates, logs, state, and results are untracked, but also proposes:

```text
git reset --hard <base>
git clean -fd
```

That can delete `evolve/candidates/`, `state.json`, `history.jsonl`, logs, and score artifacts unless they are tracked, excluded, or stored outside the repo.

This is the most important mechanical correction.

Better options:

```text
Option A:
Store harness runtime outside repo:
.evolver_runs/<run_id>/...

Option B:
Use separate git worktrees for candidate generation,
then copy only the candidate diff/artifacts back into the protected harness store.

Option C:
Use git clean with explicit negative pathspec exclusions:
git clean -fd -- ':!evolve/candidates' ':!evolve/history.jsonl' ':!evolve/state.json' ...
```

I would prefer **Option B** eventually, but **Option A** is simplest for Phase 0.

## Second flaw: “strictly memoryless” is ambiguous

The plan says “strictly memoryless,” but also has durable memory, `memory.md`, `history.jsonl`, observations, archive, and state.

This is not wrong, but the wording is dangerous.

Use this distinction instead:

```text
Candidate execution is snapshot-isolated and stateless.
The harness is stateful and append-only.
The agent receives only bounded Φ, not the full archive.
```

That preserves the intended discipline without contradicting the memory system.

## Third flaw: parent selection uses holdout alpha too early

The plan says:

```text
α = holdout score
```

But also says every candidate gets cheap evaluation, while dual/full holdout is only for promotion. That creates an ambiguity:

- Do all valid candidates get holdout scores? Expensive.
- Or only promotion candidates? Then most candidates lack α.
- If α falls back to search score, the selector may overfit to noisy search-bank wins.

Fix by splitting scores:

```text
search_alpha:
    cheap search-bank score; usable for exploratory parent selection.

holdout_alpha:
    disjoint holdout score; required for official best promotion.

selection_alpha:
    holdout_alpha if available,
    else search_alpha penalized by uncertainty / non-confirmation.
```

Then official best remains holdout-locked, while the archive can still explore cheaply.

## Fourth flaw: do not mark the parent invalid after one failed child

The plan inherits a HyperAgents rule:

```text
on child failure set the PARENT valid_parent=False
```

For this system, that is too aggressive.

A child can fail because the agent crashed, made an illegal edit, timed out, or generated a bad patch. That does **not** prove the parent is invalid.

Better rule:

```text
A parent becomes invalid only if replaying/restoring/evaluating the parent itself fails,
or if its stored snapshot/diff is corrupted.

A failed child marks only the child invalid.
```

You can still penalize parents that repeatedly produce invalid children with `children_invalid_count`, but do not remove them from the pool automatically.

## Fifth flaw: separate “official best” from “selectable stepping stone”

The plan mostly gets this right, but vNext should make it impossible to confuse these two states.

Use three statuses:

```text
invalid:
    failed build/test/eval/protection/empty diff/crash.

valid_stepping_stone:
    builds and evaluates; may be worse; selectable.

official_best:
    passed locked holdout keep rule and advanced the deployment baseline.
```

Never let `valid_stepping_stone` update `best_commit`.  
Never let `official_best` be chosen by search-bank score alone.

## Sixth flaw: Phase 1 still includes too much “nice to have”

Your “irreducible Phase 1” is good, but it is slightly inflated.

I would evolve the phase structure like this:

### Phase 0 - authority proof

No Cursor SDK. No real mutation intelligence. Stub agents only.

Build:

```text
config.py
protect.py
evaluate.py
store.py
loop.py
cli.py
```

Goal: prove early stopping and self-scoring are structurally impossible.

### Phase 1 - real candidate generation

Add:

```text
agents.py
select.py
observe.py
mechanism/evolve_skill.md
history.jsonl
cost.jsonl
```

Goal: real bounded Cursor sessions generate candidates, but still have no scoring or stop authority.

### Phase 1.5 - search quality hardening

Add:

```text
score_child_prop tuning
archive hygiene
parent usage counters
better Φ summaries
restart/resume durability
```

Goal: make the search actually productive, not merely safe.

### Phase 2 - optional research layers

Keep as-is:

```text
EvolutionEngine
novelty
MAP-Elites
islands
curator
SweepEngine
meta-agent
FTS5
evidence convergence
```

Default OFF.

## Seventh flaw: use atomic artifacts and schema versions

The plan says harness writes official scores, but vNext should specify atomic writes.

Use:

```text
scores.tmp.json -> fsync -> rename scores.json
archive.tmp.json -> fsync -> rename archive.json
results.tmp.tsv -> fsync -> rename results.tsv
```

Also add:

```json
{
  "schema_version": 1,
  "candidate_id": "candidate_0007",
  "parent_id": "candidate_0003",
  "eval_bank": "search_seed_0",
  "score_kind": "search|holdout|full",
  "created_by": "harness"
}
```

This prevents half-written artifacts from corrupting restarts.

## Evolved vNext thesis

The plan should say this near the top:

```text
The first deliverable is not better Durak performance.

The first deliverable is an authority-separation proof:
the agent may generate patches, but it cannot stop the outer run,
cannot write official scores, cannot preserve illegal edits,
cannot promote itself, and cannot destroy the archive.

Only after this proof passes with stubbed agents do we attach the real Cursor agent.
```

That sentence makes the whole implementation less likely to drift.

## What I would change in the Cursor prompt

Add these hard corrections:

```text
Before integrating Cursor SDK, implement a Phase-0 stub-agent test harness.
The stub agent must simulate:
- DONE/PLATEAU text;
- illegal evaluator edit;
- scores.json/results.tsv write attempt;
- crash/timeout;
- seed-overfit candidate;
- valid regression.

The full loop must pass these tests without any Cursor/API call.

Do not store candidate/runtime artifacts in a location that can be deleted by git clean.
Either store them outside the repo under .evolver_runs/<run_id>/ or explicitly exclude them from every clean/reset path.

Candidate execution is stateless and snapshot-isolated; the harness state is append-only.
Do not call the whole system memoryless.

Do not mark a parent invalid merely because one child failed.
Only mark the child invalid unless the parent snapshot itself cannot be restored/evaluated.

Use search_alpha for cheap exploratory selection and holdout_alpha for official promotion.
Official best may advance only on holdout/full keep rule.
```

## Final recommendation

Do **not** evolve the plan by adding sophistication. Evolve it by making the invariants executable.

The current plan is already a good architecture. The next version should be a **smaller, harsher implementation contract**:

```text
Phase 0: prove authority separation with stubs.
Phase 1: attach Cursor as a bounded patch generator.
Phase 1.5: improve selection/archive ergonomics.
Phase 2: optional measured research layers.
```

That will make the plan much harder for a coding agent to misinterpret, overbuild, or quietly weaken.

## Prompt:
6/27/2026, 2:48:05 AM

[Attachment: Pasted markdown(17).md]

## Response:
6/27/2026, 2:48:06 AM

I’m reading the new upload as your revised vNext. It successfully absorbed the main corrections; I’ll now stress-test what still needs tightening before handing it to Cursor.

> **Evaluating user's revised plan**
>
> The user uploaded a revised plan and likely wants me to evaluate it. Since we've already reviewed the previous version, I'll compare this one to the previous critique and focus on improvements made. The main changes seem well-applied, but future revisions could address potential contradictions and implementation risks. I'll also include relevant feedback on specific areas of improvement.
>
> **Reviewing user's revised plan**
>
> The user uploaded an updated plan, so I’ll review and provide feedback on improvements. I’m reading this as a request to evolve it further. 
> 
> Phase 0 still raises questions about the evaluator setup, needing stubs versus real builds. It's important to address decoupling tests and ensuring the evaluation system works seamlessly with platform builds. We should consider adding an Evaluator interface, but avoid unnecessary complexity.
>
> Thought for 23s

Yes - this revised vNext is **substantially better**. It successfully converts the previous architecture plan into an **authority contract**: Phase 0 with stub agents, runtime outside the repo, split `search_alpha / holdout_alpha / selection_alpha`, three candidate states, atomic artifacts, and corrected child/parent invalidation are all the right upgrades. `Pasted markdown.md`

My MetaAgent verdict: **this is now close to shippable as the canonical plan**, but I would evolve it one more notch before giving it to Cursor.

## The remaining weakness

The plan now protects the big invariants, but it still mixes two different things inside Phase 0:

1. **authority proof**;
2. **real Durak evaluator integration**.

That is dangerous because if `build.bat`, `ctest`, or `triage.bat` fails for mundane repo reasons, the agent may conflate “harness invariant failed” with “Durak evaluator failed.”

So I would split Phase 0 into:

```text
Phase 0A - pure authority proof
StubAgent + FakeEvaluator + fake git sandbox.
No Durak build. No Cursor. No real scoring.
Proves stop/self-score/illegal-edit/crash/archive invariants.

Phase 0B - real repo adapter smoke test
Same harness, but now RealEvaluator calls build.bat / ctest / triage.bat.
Proves the adapter wiring, not the abstract authority model.
```

This is not overengineering. It makes failures diagnosable.

## The most important implementation correction

Add an explicit tiny interface seam:

```python
class Evaluator(Protocol):
    def evaluate_search(self, candidate: Candidate) -> ScoreResult: ...
    def evaluate_holdout(self, candidate: Candidate) -> ScoreResult: ...
```

Then:

```text
FakeEvaluator:
    used only for Phase 0A invariant tests.

DurakEvaluator:
    wraps build.bat, check_forbidden.cmake, ctest, triage.bat.
```

This is **not** the Phase-2 `EvolutionEngine` abstraction. It is just testability for the authority proof.

Without this seam, Cursor may build a harness that can only be tested through slow, flaky real Durak commands.

## Second correction: define parent replay precisely

The current plan says parent snapshots are restored, but the exact semantics need to be stricter.

Use this:

```text
Every candidate stores:
- parent_id
- parent_snapshot_hash
- snapshot.cpp
- model_patch.diff
- base_commit
- generated_from_status

To generate from parent P:
1. reset repo to current official best_commit;
2. overwrite durak/src/strategy_heuristic.cpp with P.snapshot.cpp;
3. verify hash == P.snapshot_hash;
4. run the agent;
5. capture the resulting strategy file as child snapshot;
6. compute diff relative to P.snapshot.cpp for lineage;
7. compute diff relative to official best_commit for commit/promotion.
```

Why this matters: a regression parent may not correspond to a git commit. The archive contains many valid stepping stones that were never promoted. So “restore parent” cannot mean `git checkout parent_commit` unless every valid candidate has a commit. Better: **official best is git state; archive parents are file snapshots**.

## Third correction: make `run_dir` impossible to misconfigure

The plan says default `../.evolver_runs/<run_id>/`, which is good. But add a hard runtime assertion:

```text
resolve(run_dir) must not be inside resolve(repo_root).
If it is inside the repo, abort before the first candidate.
```

Also reject symlink traps:

```text
run_dir.resolve().is_relative_to(repo_root.resolve()) == False
```

This prevents a bad config from silently putting runtime artifacts back under `git clean`.

## Fourth correction: define promotion track trigger

The plan says holdout is computed “only on the promotion track,” but not exactly what enters promotion track.

Add:

```text
A candidate enters promotion track only if:
- it is valid on search eval;
- search_alpha >= current_best_search_alpha + search_margin
  OR search_alpha is within epsilon of best and lower_ci improves
  OR it is explicitly sampled for periodic audit every N valid candidates.
```

Without this, implementation may either holdout too many candidates or too few.

I like this default:

```text
promotion_track =
    search_score >= best_search_score + 0.002
    OR lower_ci >= best_lower_ci
    OR candidate_id % audit_every == 0
```

Then official keep remains stricter:

```text
search_full >= best + 0.005
AND lower_ci >= best_lower_ci
```

## Fifth correction: don’t let `results.tsv` become ambiguous

The plan says `results.tsv` is regenerated from `run_dir`. Good. Now define it as a **view**, not a source:

```text
results.tsv is disposable.
It is never read for official state.
It is regenerated from archive.json + per-candidate scores.json.
If missing or corrupted, rebuild it.
```

Cursor agents often accidentally reintroduce old files as state sources. This sentence prevents that.

## Sixth correction: make crash-safe writes directory-level too

Atomic file writes are good. But candidate folders can still be half-created.

Use a staging directory:

```text
candidate_NNNN.tmp/
  meta.json
  scores.json
  snapshot.cpp
  model_patch.diff

fsync files
fsync directory
rename candidate_NNNN.tmp -> candidate_NNNN
append candidate_NNNN to archive.json atomically
```

Rule:

```text
Only finalized candidate_NNNN/ directories are visible to the archive.
.tmp directories are ignored or cleaned on resume.
```

This closes the “half-created candidate directory” hole.

## Seventh correction: Cursor prompt should forbid “helpful simplification”

Add this line to the prompt:

```text
Do not collapse Phase 0A/0B, do not skip the FakeEvaluator, and do not replace invariant tests with a live dry run.
```

That line matters because coding agents often compress test scaffolds away when they think the real integration is enough.

## My final version of the next evolution

I would add this small block to the plan:

```text
Phase 0 is split into two subphases.

Phase 0A - authority proof:
Uses StubAgent + FakeEvaluator + controlled fake outcomes.
No Cursor SDK, no real Durak build, no triage.bat.
Proves early-stop immunity, self-score immunity, illegal-edit reset,
crash/timeout safety, archive persistence, valid-regression selectability,
atomic artifact writes, and restart behavior.

Phase 0B - Durak adapter smoke:
Swaps FakeEvaluator for DurakEvaluator.
Runs build.bat fast -> check_forbidden.cmake -> ctest -> triage.bat.
This phase proves repo integration only; it must not be the first proof
of the authority model.

The harness must expose a minimal Evaluator protocol so Phase 0A tests
cannot depend on real simulator behavior.
```

## Final verdict

This vNext is **good enough to become the canonical implementation plan** after one last hardening pass.

The only thing I would not ship unchanged is the Phase 0 structure. Split it into **Phase 0A FakeEvaluator authority proof** and **Phase 0B real Durak adapter smoke**. That makes the plan much more robust against Cursor implementing something that “works once” but is not actually proven.

## Prompt:
6/27/2026, 3:53:18 AM

[Attachment: cursor_agent_stopping_decision_conflict2.md]

## Response:
6/27/2026, 3:53:19 AM

> **Inspecting uploaded plan for analysis**
>
> The user has uploaded a file, and it seems like they may be looking for feedback or suggestions on it, possibly focusing on changes to a plan. I'll need to carefully read the file to check for the content and context and determine if they're expecting a critique, summary, or evolution of it.
>
> **Reviewing file and preparing feedback**
>
> The user hasn’t asked a direct question, but based on patterns, they likely want feedback on the uploaded file. I’ll reference the file and review it, providing an analysis of the changes. I’ll also make sure to cite the file content properly, possibly checking if there's more context or updates available.
>
> Thought for 24s

MetaAgent verdict: the newest export shows **real progress**, but it also shows **plan drift**. You now have two competing canonical shapes in the conversation:

1. the older “Phase 1 minimal core” plan with `evolve/candidates/` inside the repo and Phase 1 directly attaching Cursor;
2. the better vNext plan where **Phase 0 proves authority separation with stubs**, runtime artifacts live outside the repo, and Cursor is attached only after invariants pass. `Pasted markdown.md`

You should declare the vNext plan canonical and retire the older one.

## Main correction

The current strongest version is:

```text
Phase 0A: pure authority proof with StubAgent + FakeEvaluator.
Phase 0B: Durak adapter smoke with real build/ctest/triage.
Phase 1: attach Cursor as bounded patch generator.
Phase 1.5: search-quality hardening.
Phase 2: optional measured QD/meta/curator layers.
```

The export already moved in this direction: Phase 0 proves the agent cannot stop the run, write official scores, preserve illegal edits, promote itself, or destroy the archive before Cursor is attached. Runtime artifacts are moved outside the repo so `git reset` / `git clean` cannot wipe candidates, state, history, logs, or scores. `Pasted markdown.md`

That is the right backbone.

## The dangerous conflict still present

There is a conflict between the HyperAgents-code-derived rule and your later vNext correction.

Earlier, the plan copied HyperAgents’ behavior:

```text
child failure -> mark parent valid_parent=False
```

But vNext correctly says:

```text
failed child marks only the child invalid;
parent is invalid only if restoring/evaluating the parent itself fails.
```

Keep the vNext rule. In your domain, a failed child can mean agent crash, illegal edit, timeout, empty diff, or bad patch. None of those proves the parent is unusable. Removing the parent would destroy useful stepping stones and reintroduce diversity collapse. The vNext plan explicitly says child failure increments `children_invalid_count` but does not remove the parent. `Pasted markdown.md`

## Second conflict: tool permissions vs mechanical reset

The export oscillates between:

```text
give the agent full tools, then reset everything outside allowlist
```

and:

```text
disable git/eval/web/shell; agent can only read repo and edit strategy file
```

Use both, but order the authority correctly:

```text
Tool restriction is convenience.
Git reset allowlist is authority.
Harness-owned evaluation is truth.
```

So the final rule should be:

```text
The agent should not receive git/eval/web/shell tools when possible.
But safety must not depend on tool restrictions.
After every candidate, protect.py resets everything except the manifest allowlist.
Only evaluate.py writes official scores.
```

That preserves HyperAgents’ mechanical safety lesson without unnecessarily giving Cursor more dangerous tools.

## Third conflict: Phase 2 bloat is creeping back

Ralph pushed the plan toward a pluggable QD interface: flat archive, MAP-Elites, gridless novelty, islands, meta-editable selector. That is fine as **Phase 2**, but it must not contaminate Phase 0 or Phase 1.

The plan should say:

```text
Phase 1 has only:
- flat open-ended archive;
- score_child_prop selector;
- random selector as ablation;
- no MAP-Elites;
- no islands;
- no modifiable selector;
- no curator;
- no meta-agent.
```

The older canonical plan already had this discipline: MAP-Elites, islands, novelty, curator, SweepEngine, meta-agent, and evidence convergence are default-OFF Phase 2 upgrades measured against the baseline. `aevo_harness_for_autoresearch_b2455abd.plan.md`

Keep that.

## Fourth correction: add Phase 0A / 0B explicitly

Your vNext says Phase 0 uses stubs, but it still risks mixing the authority proof with real Durak evaluator wiring. Make the split explicit:

```text
Phase 0A - authority proof:
StubAgent + FakeEvaluator + fake score outcomes.
No Cursor SDK.
No build.bat.
No ctest.
No triage.bat.
Proves authority separation.

Phase 0B - Durak adapter smoke:
Same harness.
Swap FakeEvaluator for DurakEvaluator.
Run build.bat fast -> check_forbidden.cmake -> ctest -> triage.bat.
Proves repo integration only.
```

This prevents the first proof from failing because of a mundane build issue.

## Fifth correction: make candidate replay snapshot-based

Do not rely on applying parent patch stacks as the primary restore mechanism. For this system, many valid stepping stones will never be git commits.

Canonical replay should be:

```text
1. reset repo to official best_commit;
2. overwrite durak/src/strategy_heuristic.cpp with parent snapshot.cpp;
3. verify parent_snapshot_hash;
4. run agent;
5. capture child snapshot.cpp;
6. compute child diff against parent snapshot for lineage;
7. compute promotion diff against official best for commit/tag.
```

Git commits are for official bests. Archive parents are file snapshots.

## Sixth correction: QD architecture should be interface-only until Phase 2

Keep these interfaces in the design, but do not implement them in Phase 1:

```text
Container:
    parents_pool()
    add_candidate()
    update_elite()
    coverage_stats()

Selector:
    select(container, k, rng)

Descriptor:
    compute_b(candidate)

AdmissionPolicy:
    valid candidate enters archive

ReplacementPolicy:
    official best / MAP cell elite updates only on holdout-confirmed rule

MigrationPolicy:
    only used if islands enabled
```

Phase 1 implements only:

```text
FlatArchiveContainer
ScoreChildPropSelector
RandomSelector
NoopDescriptor
SimpleAdmissionPolicy
NoMigrationPolicy
```

This gives you the seam without paying the complexity cost.

## Revised canonical plan

Use this as the clean hierarchy:

```text
Phase 0A - Authority Proof
- config.py
- protect.py
- store.py
- loop.py
- cli.py
- FakeEvaluator
- StubAgent
- run_dir outside repo
- atomic artifacts
- no Cursor
- no real Durak eval

Phase 0B - Durak Adapter Smoke
- DurakEvaluator
- build.bat fast
- check_forbidden.cmake
- ctest
- triage.bat
- parse official scores
- regenerate results.tsv view

Phase 1 - Real Candidate Generation
- agents.py with Cursor SDK
- bounded inner sessions
- score_child_prop selector
- flat open-ended archive
- compact Phi observe.py
- cost.jsonl
- mechanism/evolve_skill.md
- re-run Phase 0 invariants with real agent

Phase 1.5 - Durability / Search Hardening
- restart/resume
- parent usage counters
- best-lineage pinning
- archive hygiene
- richer Phi
- optional worktrees

Phase 2 - Measured Optional Layers
- EvolutionEngine
- GreedyEngine ablation
- gridless novelty
- MAP-Elites
- islands
- modifiable selector
- curator
- SweepEngine
- FTS5
- meta-agent
- evidence convergence with min_rounds floor
```

## Decision log update

Add these entries:

```text
D1. vNext supersedes older Phase-1-first plan.
D2. Phase 0 is split into 0A FakeEvaluator authority proof and 0B Durak adapter smoke.
D3. Runtime artifacts must live outside repo; abort if run_dir resolves inside repo.
D4. Agent tool restrictions are not trusted; allowlist reset is the authority.
D5. Failed child never invalidates parent unless parent restore/eval fails.
D6. Archive parents restore from snapshot.cpp, not from git commits.
D7. Phase 1 QD is flat archive + score_child_prop only.
D8. MAP-Elites/islands/novelty/modifiable selector stay Phase 2 and must beat baseline per dollar.
D9. results.tsv is a disposable view, never a source of truth.
D10. Official best requires holdout/full keep rule; search_alpha can never promote.
```

## Final verdict

The plan is now very close. The biggest remaining task is **not adding more mechanisms**. It is removing ambiguity.

The canonical version should be:

```text
Prove authority separation first.
Attach Cursor second.
Improve search third.
Add QD/meta layers only after the baseline is measured.
```

That is the version I would give to Cursor.

## Prompt:
6/27/2026, 3:56:06 AM

how to run the system

## Response:
6/27/2026, 3:56:08 AM

> **Remembering**
>
> Clarifying harness status
>
> **Remembering**
>
> Reviewing your preferred phase
>
> **Remembering**
>
> Identifying command style
>
> **Remembering**
>
> Confirming system setup
>
> Thought for 26s

To run it correctly, treat the system as **phase-gated**. Do **not** start with live Cursor. First run the stub authority proof, then the real Durak evaluator smoke, then attach Cursor.

The vNext plan says Phase 0 must prove the agent cannot stop the outer run, write official scores, preserve illegal edits, promote itself, or destroy the archive before Cursor is attached; runtime artifacts should live outside the repo under `../.evolver_runs/<run_id>/`; Phase 1 attaches Cursor only after that. `Pasted markdown.md`

## 0. From repo root

PowerShell:

```powershell
cd path\to\repo

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
```

Make sure these exist:

```text
evolver/
evolve/config.json
evolve/manifest.yaml
evolve/mechanism/evolve_skill.md
```

Your manifest should allow only:

```yaml
evolvable_layers:
  inner:
    - durak/src/strategy_heuristic.cpp
reload_strategy: cold
locked: everything_else
```

The plan’s required modules are `cli.py`, `loop.py`, `config.py`, `protect.py`, `evaluate.py`, `store.py`, `select.py`, `observe.py`, and later `agents.py`. `Pasted markdown.md`

## 1. Phase 0A - run authority proof, no Cursor

This should use:

```text
StubAgent + FakeEvaluator
```

Run:

```powershell
python -m evolver.cli run `
  --phase 0a `
  --agent stub `
  --evaluator fake `
  --max-rounds 2 `
  --k 2 `
  --run-id p0a_authority_smoke
```

Expected pass conditions:

```text
DONE/PLATEAU does not stop the run
illegal edits are reset
agent-written scores.json/results.tsv are ignored
crash/timeout becomes invalid candidate
valid regression stays selectable
run_dir survives git reset/clean
```

Check status:

```powershell
python -m evolver.cli status --run-id p0a_authority_smoke
```

Inspect artifacts:

```powershell
dir ..\.evolver_runs\p0a_authority_smoke
dir ..\.evolver_runs\p0a_authority_smoke\candidates
type ..\.evolver_runs\p0a_authority_smoke\archive.json
```

Do **not** continue unless Phase 0A passes.

## 2. Phase 0B - real Durak evaluator smoke, still no Cursor

First verify the repo evaluator manually:

```powershell
.\durak\build.bat fast
ctest --test-dir durak\build --output-on-failure
.\scripts\triage.bat quick
```

Then run the harness with the real evaluator but still stub agent:

```powershell
python -m evolver.cli run `
  --phase 0b `
  --agent stub `
  --evaluator durak `
  --max-rounds 2 `
  --k 2 `
  --run-id p0b_durak_smoke
```

Expected:

```text
build.bat fast runs from evaluate.py
check_forbidden.cmake / ctest / triage.bat are harness-owned
scores.json is written only by evaluate.py
results.tsv is regenerated as a view
seed-overfit candidate is not promoted
```

The plan specifically makes `evaluate.py` own `build.bat fast -> check_forbidden.cmake -> ctest -> scripts/triage.bat`, parse `search_score / point_rate / lower_ci`, write atomic `scores.json`, and regenerate `results.tsv`. `Pasted markdown.md`

## 3. Phase 1 - attach Cursor

Only now set Cursor credentials:

```powershell
$env:CURSOR_API_KEY = 'your_key_here'
```

Install Cursor SDK if not already in the project:

```powershell
python -m pip install cursor-sdk
```

Run a tiny live dry run:

```powershell
python -m evolver.cli run `
  --phase 1 `
  --agent cursor `
  --evaluator durak `
  --max-rounds 2 `
  --k 2 `
  --cost-cap 5 `
  --run-id p1_cursor_tiny
```

Watch progress:

```powershell
python -m evolver.cli status --run-id p1_cursor_tiny
```

Continue a stopped/incomplete run:

```powershell
python -m evolver.cli continue --run-id p1_cursor_tiny
```

Stop externally:

```powershell
python -m evolver.cli stop --run-id p1_cursor_tiny
```

## 4. Normal run

After tiny run passes:

```powershell
python -m evolver.cli run `
  --phase 1 `
  --agent cursor `
  --evaluator durak `
  --max-rounds 50 `
  --k 4 `
  --cost-cap 50 `
  --run-id durak_aevo_001
```

Use `K=2` while debugging. Move to `K=4` only after crash/restart and score-regeneration are proven.

## 5. What not to run yet

Do not run these until the flat Phase 1 baseline works:

```text
MAP-Elites
islands
gridless novelty
curator
SweepEngine
meta-agent
evidence convergence
EvolutionEngine abstraction
```

Those are Phase 2 measured upgrades, not the first runnable system. The plan explicitly keeps QD/curator/sweep/FTS/attribution/convergence default-OFF until they beat the Phase 1 baseline. `aevo_harness_for_autoresearch_b2455abd.plan.md`

## Minimal command sequence

The practical sequence is:

```powershell
python -m evolver.cli run --phase 0a --agent stub --evaluator fake  --max-rounds 2 --k 2 --run-id p0a
python -m evolver.cli run --phase 0b --agent stub --evaluator durak --max-rounds 2 --k 2 --run-id p0b
$env:CURSOR_API_KEY = 'your_key_here'
python -m evolver.cli run --phase 1  --agent cursor --evaluator durak --max-rounds 2 --k 2 --cost-cap 5 --run-id p1_tiny
python -m evolver.cli run --phase 1  --agent cursor --evaluator durak --max-rounds 50 --k 4 --cost-cap 50 --run-id durak_aevo_001
```

If the harness is not implemented yet, the only thing you can run today is the current evaluator path:

```powershell
.\durak\build.bat fast
ctest --test-dir durak\build --output-on-failure
.\scripts\triage.bat quick
```

The AEvo loop itself becomes runnable only after `evolver/cli.py`, `loop.py`, `protect.py`, `evaluate.py`, and `store.py` exist.

## Prompt:
6/29/2026, 12:00:14 AM

I read the full plan and audited the code against it. Here's the status. Short version: **Phases 0, 1, and most of 1.5 are implemented and actively running; Phase 2 is fully coded and unit-tested but almost entirely dormant** (disabled by config or never wired into the live loop). A handful of Phase-2 sub-features are only placeholders or not wired at all.

## Implemented and in use (the run you just started)
`cli` (run/continue/status/stop), `config`/`manifest` allowlist, `protect` (reset-all-but-allowlist, reset-to-base, commit_inline, evo-N tags), `evaluate` (build→forbidden→ctest→triage, search/holdout/full, keep-rule, atomic writes), `store` (3 statuses, atomic archive, `usage.json`, pin-lineage, archive-stale), `loop` (driver owns rounds/budget/gate/termination), `agents.CursorCliAgent`, `select.ScoreChildPropSelector`, `observe` (bounded Φ + `memory.md` + `cost.jsonl` + program.md dead-ends), `hygiene` (backups + stale archiving), and `mechanism/evolve_skill.md` (prepended to every prompt). All four phase test suites exist (`test_phase0/1/15/2.py`).

## Implemented + tested, but NOT used (dormant — gated off by `evolve/config.json`)
| Feature | Code | Why it's idle |
|---|---|---|
| Greedy / Novelty / Curiosity / MAP-Elites / Islands / Modifiable engines | `engine/base.py`, `engine/qd.py` | `"engine": "default"` → only `DefaultEngine` runs |
| Meta-agent self-modification | `meta.MetaController`, `mechanism/meta_skill.md` | `"meta.every": 0` → never instantiated |
| Evidence-based convergence | `meta.ConvergencePolicy` | `"convergence.enabled": false` → never fires (budget-only) |
| Attribution ledger | `meta.Attribution` | only writes during meta rounds → silent now |
| Git worktrees (candidate isolation) | `worktree.py`, `loop._propose_in_worktree` | `"use_worktrees": false` → edits in place |
| SDK agent | `agents.CursorAgent` | `"agent": "cursor_cli"`; would now fail anyway (we removed `CURSOR_API_KEY`) |
| Curator (suggest-only LLM hygiene) | `curator.py` | imported only by tests; loop uses the deterministic `store.archive_stale` + `Hygiene` instead |
| FTS5 history index | `db.EvolutionDB` | imported only by tests; live history is `history.jsonl` + `archive.json` |
| LLM-free parameter sweeps | `engine/sweep.SweepEngine` | not even registered in `make_engine`; tests-only |

## Only partial / placeholder / not wired at all
- **Behavioral descriptors `b(x)`**: `StaticDescriptor` (complexity, point_rate_b4) is the default. A real `FeatureDescriptor` + `parse_feature_descriptor` for `durak --mode features` exists in `population.py` but isn't selectable via config or passed into any QD engine.
- **`select_policy.json`** (meta-editable selector): `ModifiableEngine` accepts an in-memory dict, but there's no JSON policy file load/save, so the meta layer can't actually edit selection.
- **`family_map.md`**: the file exists but **no code reads it** (only `meta_skill.md` is consumed, and only when meta is on).
- **Skill-library + LLM memory consolidation**: only the static `evolve_skill.md` and a suggest-only curator hook; no growing/consolidating skill store is wired.
- **Parallel Pass@K via worktrees**: the candidate loop is strictly sequential (`for parent in parents`); worktrees only ever isolate one candidate.

One non-gap worth noting: `memory.md` lives in `run_dir` (outside the repo) rather than `evolve/mechanism/` — that's intentional per mechanical contract #1 (so `git clean` can't delete it), not a missing piece.

So nothing in the **authority-proof core (Phase 0/1)** is missing — that's the whole point of the plan and it's all live. Everything absent is **Phase 2 "optional measured layers," which the plan explicitly says ship OFF by default** and are only kept if they beat the Phase-1 baseline on holdout-gain-per-dollar. The run you have going right now *is* that Phase-1 baseline.

Want me to wire up and A/B any specific dormant layer (e.g., flip on a QD engine like `islands`/`map_elites`, or enable the meta-agent every N rounds) against the baseline once this run produces a few data points?

## Response:
6/29/2026, 12:00:15 AM

This is exactly the right audit format: it separates “authority core is live” from “research layers are present but not part of the baseline.” I’ll treat the current run as the Phase-1 baseline and recommend the least risky next activation path.

> **Deciding on phase 2 advice**
>
> It seems the user isn't looking to compare with the attached plan, but might expect citations from it. If I use details from the uploaded file, I'll need to cite it carefully. For now, I think the best advice is: don’t enable Phase 2 until baseline data is in place, and start A/B testing one layer at a time.
>
> Thought for 24s

Yes — your audit says the system is in the **right state**.

The important conclusion is:

```text id="ijqjrs"
The authority-proof core is live.
The current run is the Phase-1 baseline.
Phase 2 being dormant is not a bug; it is the intended control condition.
```

I would **not** flip on MAP-Elites, islands, meta-agent, or convergence yet. First let the Phase-1 baseline produce enough evidence.

## My recommendation

Let the current baseline run until it has at least:

```text id="mhx0l3"
20–30 valid candidates
and preferably 5+ holdout/full promotion attempts
or until the current cost cap is reached
```

Then run **one Phase-2 layer at a time** against that baseline.

Do not enable several dormant layers together, because then you will not know what caused any gain or regression.

## First thing to wire: shadow descriptors, not QD

The best next step is **not** `map_elites` or `islands`.

It is:

```text id="er7c7q"
Wire FeatureDescriptor into config and run it in shadow mode.
```

Meaning:

```text id="q6wkp7"
- parse real durak --mode features;
- store b_descriptor in meta.json;
- write descriptor coverage stats to observations;
- do NOT change parent selection yet.
```

Why: QD without real behavioral descriptors is mostly fake QD. Right now `StaticDescriptor(complexity, point_rate_b4)` is too thin. Before turning on MAP-Elites or novelty, you need to verify that `b(x)` is stable, informative, and cheap.

Expected test:

```text id="7pqauz"
same Phase-1 run behavior,
but every valid candidate now has b_descriptor,
descriptor entropy/coverage appears in observe.py,
and no keep/selection behavior changes.
```

## First actual A/B: gridless novelty, not MAP-Elites

After shadow descriptors work, A/B this first:

```text id="p7t8rc"
DefaultEngine + ScoreChildPropSelector
vs
DefaultEngine + ScoreChildPropSelector with novelty tie-break / novelty multiplier
```

I would not jump directly to MAP-Elites. Gridless novelty is the smallest change that tests the actual hypothesis:

```text id="g82972"
Does behavioral diversity help escape the plateau?
```

A safe formula:

```text id="czs9o8"
p(parent) ∝ score_child_prop(parent) × (1 + λ × novelty(parent))
```

with a small λ first, for example `0.1` or `0.25`.

Do not let novelty override quality yet. Let it act as a de-collapse pressure.

## MAP-Elites should be second or third

MAP-Elites is only worth trying after you know descriptors work.

Risk: with noisy scores and sparse cells, MAP-Elites can preserve mediocre elites just because they occupy rare bins. That is useful for exploration but dangerous if you let it touch official best.

So MAP-Elites should obey:

```text id="nad443"
cell admission: valid candidate
cell elite replacement: holdout-confirmed or robust search+lower_ci
official best: unchanged locked keep rule
```

I would try MAP-Elites only after gridless novelty has either:

```text id="clcaxq"
helped but not enough,
or shown clear descriptor coverage without score improvement.
```

## Islands should come later

Islands are heavier because they change run dynamics, migration, and attribution.

Use islands only if you observe real collapse:

```text id="hljyxe"
same parent lineage dominates;
same family repeats;
descriptor coverage stagnates;
valid candidates become near-duplicates;
score_child_prop keeps sampling the same basin.
```

Until then, islands are probably overkill.

## Meta-agent should be last

Do **not** enable `meta.every > 0` yet.

Reason: meta-agent self-modification changes the search procedure while you are still trying to measure the baseline. It will contaminate attribution.

Enable it only after you have:

```text id="5c05yd"
baseline run
descriptor shadow run
novelty A/B
maybe MAP-Elites A/B
```

Then meta-agent can be tested as a separate treatment:

```text id="y6hf3l"
fixed mechanism baseline
vs
meta every N rounds
```

with `N` large, not frequent. For example:

```text id="p498ti"
meta.every = 10 or 20
```

not every round.

## SweepEngine is the cheap exception

`SweepEngine` is the one dormant layer I would consider wiring earlier, because it is LLM-free.

But only if there are obvious parameterized knobs in `strategy_heuristic.cpp`.

Good use:

```text id="5qqgfl"
Agent proposes a structural family.
SweepEngine cheaply explores parameters around that family.
```

Bad use:

```text id="mnx5oy"
SweepEngine replaces structural search.
```

So register it in `make_engine`, but keep it off until you have a known accepted or near-accepted family worth sweeping.

## What to fix before any Phase-2 A/B

These are wiring gaps worth fixing now, but keep them dormant:

```text id="d1vp52"
1. Make FeatureDescriptor selectable via config.
2. Store b_descriptor in candidate meta.json.
3. Add descriptor coverage / entropy to observe.py.
4. Register SweepEngine in make_engine, but default OFF.
5. Implement select_policy.json load/save before calling ModifiableEngine real.
6. Make family_map.md readable by observe/meta only when meta is enabled.
```

The key is: **wiring is okay; changing live behavior is not.**

## A/B order I would use

```text id="nmx5mq"
A0. Current Phase-1 baseline:
    DefaultEngine + flat archive + score_child_prop.

A1. Shadow descriptors:
    same as baseline, but collect real FeatureDescriptor.

A2. Gridless novelty:
    score_child_prop × small novelty multiplier.

A3. SweepEngine:
    only around a known promising family.

A4. MAP-Elites:
    coarse 2D/3D grid, robust elite replacement.

A5. Islands:
    only if lineage/diversity collapse is observed.

A6. Meta-agent:
    only after selector/QD effects are measurable.

A7. Evidence convergence:
    last, behind min_rounds floor.
```

## What I would answer to the runner

Yes, but narrowly:

```text id="1l17yo"
Do not enable a Phase-2 engine yet.
First let the current Phase-1 baseline run produce enough valid candidates.
Meanwhile, wire FeatureDescriptor in shadow mode and add descriptor coverage to observations.
After the baseline has data, A/B gridless novelty against score_child_prop.
Do not enable meta-agent, MAP-Elites, islands, or convergence until that comparison is done.
```

## Final verdict

Your current state is healthy:

```text id="w0hlxq"
Authority core: implemented and live.
Phase-1 baseline: running.
Phase-2: correctly dormant.
```

The next evolution should be **measurement discipline**, not more architecture.
