# Heuristic family map (maintained by the meta-agent)

A living catalog of Durak strategy heuristic *families* the inner agent can draw from, plus
families that have been confirmed dead. The inner agent reads the harness Φ (which derives
dead-ends from here and from `program.md`); the meta-agent curates this file from evidence.

## Active families (try these)
- `pair-baiting` **(DE-ANCHOR priority — try first; zero attempts in archive so far)**:
  open or pile with a rank you hold in duplicate so the opponent must break pairs or accept
  tempo loss. Scan `RANK_MASK[r]` for ranks with `popcount(L.hand & RANK_MASK[r]) >= 2`; on
  open, attack the *lowest* legal card of such a rank before `pick_cheapest`. In pile phase,
  prefer a throw-in whose rank still has surplus in hand (`popcount(L.hand &
  RANK_MASK[rank_of(c)]) >= 2`) before H3's `pick_cheapest_nontrump` default. Bump
  `kHeuristicCount` to 6 and document H6 in the manifest — do not touch H1–H5 `if` bodies.
- `card-counting` **(DE-ANCHOR priority — try second)**: memoryless rank exhaustion from
  visible cards only (`hand | table_attack | table_defense | trump_card`); when
  `deck_count==0`, prefer opening or throw-in on ranks where all four copies are already
  visible (`popcount(visible & RANK_MASK[r]) == 4`). Do not use `MemoryFeatures` — B2 passes
  `memory=nullptr`.
- `trump-economy` / `endgame-tempo`: already embodied in incumbent H1–H5
  (`candidate_0000`). Do not re-tune — see dead-ends.

## Confirmed dead-ends (do NOT re-propose)
- **H2/H4/H5 scalar gate tweaks** (trump-economy + endgame-tempo): 15 plateau rounds;
  parents `candidate_0000`, `candidate_0002`, `candidate_0004`, `candidate_0013`–`0030` all
  produced stepping stones only (search ~0.74–0.77, keep rule failed). Changing
  `deck_count` / `opponent_hand_count` thresholds on existing heuristics is structurally
  saturated at current complexity — add H6 from a different family instead.
- **H3 pile-rank-matching without pair surplus** (extends incumbent pile logic only):
  candidates `candidate_0025`–`0030` (parents `0015`/`0017`/`0025`/`0028`) reached
  search ~0.745–0.766 but failed keep — table-rank throw-in without duplicate-rank
  pressure is not a new family; pair-baiting must gate on `popcount(L.hand & RANK_MASK[r]) >= 2`.

## Notes
- A family is "confirmed dead" only after multiple distinct attempts failed the holdout
  keep rule, not after a single low search score.
- Prefer the lowest-complexity member of a family that achieves the gain (Occam tie-break).
- B2 evaluation passes `memory=nullptr`; card-counting must use `LocalFeatures` only, not
  `MemoryFeatures` (B3 ablation path is not scored).
