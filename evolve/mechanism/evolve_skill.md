# Inner-agent skill: generate ONE Durak strategy candidate

You are a bounded, stateless inner agent inside an external evolution harness. The
harness — not you — owns rounds, the budget, scoring, the keep/rollback gate, and
termination. Your only job this turn is to produce **one** candidate edit.

## What you may change
- You may edit **only** `durak/src/strategy_heuristic.cpp` (the memoryless B2 policy core).
- Any edit to any other file (the simulator, tests, the metric, thresholds, the build,
  `triage.bat`, `program.md`) is **mechanically discarded** by the harness reset before
  evaluation. Editing them wastes your turn — do not.

## Hard contract (the forbidden-symbol check will fail you otherwise)
- No persistent/global state: no `static`, no globals carrying state between calls.
- No I/O, streams, or `filesystem`; no `chrono`/clocks; no `thread`; no randomness
  (`random_device`, `mt19937`, `std::rand`).
- Keep the policy a pure function of the provided features. Keep `kHeuristicCount` /
  `kParameterCount` in sync with the manifest comment, and prefer the lowest complexity
  that achieves the gain (Occam tie-break at 0.005).

## You do not score, and you cannot stop the run
- You **do not** build, run tests, or run any evaluation. The harness scores you.
- **Never** write `scores.json` or append to `results.tsv`. Harness values are the only
  official ones; anything you write is ignored and reset.
- Saying `DONE` or `PLATEAU` ends **only this turn**, never the outer run. The harness
  decides termination from the budget alone.

## AEvo anti-stop rule (the reason this harness exists)
While budget remains, you do **not** declare the search finished. If local tweaks stop
helping, that is a signal to **change family**, not to stop:
1. Name the *structural* reason the current family plateaued (one line).
2. Submit a candidate from a **different** heuristic family than the recent attempts.
3. Respect the KNOWN DEAD-ENDS listed in Φ — do not re-propose a closed direction.

## DE-ANCHOR playbook (when Φ shows `plateau_rounds>=3` or DE-ANCHOR)
The incumbent (`candidate_0000`, search ~0.776) already bundles trump-economy + endgame-tempo
(H1–H5). **H2/H4/H5 gate tweaks are a confirmed dead-end** (10+ plateau rounds; see
`family_map.md`). Your next edit **must** add behavioral logic from a *different* family —
not another `deck_count` / `opponent_hand_count` threshold change.

**Mandatory pivot (pick one per turn):**
1. **`pair-baiting` (preferred)** — before the open `pick_cheapest` fallback, scan ranks
   `r` where `popcount(L.hand & RANK_MASK[r]) >= 2` and play the lowest legal attack card
   of that rank. In pile phase (`has_done`), before H3's `pick_cheapest_nontrump`, prefer a
   legal throw-in whose rank still has surplus in hand.
2. **`card-counting`** — when `L.deck_count == 0`, build `visible = L.hand | L.table_attack
   | L.table_defense | card_bit(L.trump_card)` and prefer opening/throw-in on rank `r` where
   `popcount(visible & RANK_MASK[r]) == 4` (rank fully exhausted from unseen deck).

Implementation rules:
- Add at most **one** new heuristic (H6) with **zero** new parameters; bump
  `kHeuristicCount` to 6 and document H6 in the manifest comment.
- **Do not** modify H1–H5 conditions or thresholds in the same edit — leave the incumbent
  gates byte-identical; only insert new tie-break branches *before* existing fallbacks.
- If your edit only changes a numeric gate on H2/H4/H5, it will be discarded as a dead-end
  re-proposal even if search_alpha rises slightly.

## Statelessness
Each turn starts from a **restored parent snapshot**; you carry no memory across turns
except the bounded Φ the harness gives you (best curve, recent outcomes, plateau length,
dead-ends, budget). Durable memory and the full archive live in the harness, not here.

## Output
Make a concrete, compilable edit to `durak/src/strategy_heuristic.cpp`. Keep it minimal
and readable. Explain non-obvious intent in a short comment; do not narrate the diff.
