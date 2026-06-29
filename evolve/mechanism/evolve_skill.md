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
(H1–H5). **H2/H4/H5 gate tweaks are a confirmed dead-end** (15 plateau rounds; parents
through `candidate_0030` — see `family_map.md`). Your next edit **must** add behavioral logic
from a *different* family — not another `deck_count` / `opponent_hand_count` threshold change.

**Wasted-turn detector (do NOT submit):**
- Any diff that only edits numeric literals inside existing H2/H4/H5 `if` conditions.
- Any pile tweak that matches table ranks without the pair-surplus gate (`popcount(L.hand &
  RANK_MASK[r]) >= 2`) — `candidate_0025`–`0030` already tried that shape.

**Mandatory pivot this round: `pair-baiting` H6** (card-counting is the fallback *next* turn).
Structural reason to cite: scalar trump-economy gates are saturated; pair surplus is unused.

Add one helper and two call sites — leave every existing H1–H5 `if` body byte-identical:

```cpp
// H6 pair_baiting: lowest legal attack whose rank still has duplicate in hand.
int pick_pair_surplus(const LocalFeatures& L, const LegalMoves& legal, int trump, bool nontrump_only) {
    int best = -1, best_rank = NUM_RANKS;
    for (int i = 0; i < legal.count; ++i) {
        if (legal.moves[i].type != MoveType::AttackPlay) continue;
        const Card c = legal.moves[i].card;
        if (nontrump_only && is_trump(c, trump)) continue;
        const int r = rank_of(c);
        if (popcount(L.hand & RANK_MASK[r]) < 2) continue;
        if (r < best_rank) { best_rank = r; best = i; }
    }
    return best;
}
```

Insertion points in `choose_attack` (restored parent uses `pick_cheapest_nontrump` in pile):
1. **Open** (`!has_done`): after the H4 trump-strip block, *before* `pick_cheapest` — call
   `pick_pair_surplus(L, legal, L.trump_suit, false)`.
2. **Pile** (`has_done`): *before* `pick_cheapest_nontrump` — call
   `pick_pair_surplus(L, legal, L.trump_suit, true)`.

Manifest: add `H6 pair_baiting`, set `kHeuristicCount = 6`. Zero new parameters.

**Fallback family (`card-counting`, only if pair-baiting already present):** when
`L.deck_count == 0`, `visible = L.hand | L.table_attack | L.table_defense |
card_bit(L.trump_card)`; prefer attack on rank `r` with `popcount(visible & RANK_MASK[r]) == 4`
before H4 / `pick_cheapest`. Still H6, still zero parameters.

## Statelessness
Each turn starts from a **restored parent snapshot**; you carry no memory across turns
except the bounded Φ the harness gives you (best curve, recent outcomes, plateau length,
dead-ends, budget). Durable memory and the full archive live in the harness, not here.

## Output
Make a concrete, compilable edit to `durak/src/strategy_heuristic.cpp`. Keep it minimal
and readable. Explain non-obvious intent in a short comment; do not narrate the diff.
