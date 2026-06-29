# Heuristic family map (maintained by the meta-agent)

A living catalog of Durak strategy heuristic *families* the inner agent can draw from, plus
families that have been confirmed dead. The inner agent reads the harness Φ (which derives
dead-ends from here and from `program.md`); the meta-agent curates this file from evidence.

## Active families (try these)
- `pair-baiting` **(DE-ANCHOR priority)**: open or pile with a rank you hold in duplicate
  so the opponent must break pairs or accept tempo loss; use `hand`/`table_attack` rank
  masks only — no new state.
- `card-counting` **(DE-ANCHOR priority)**: memoryless rank exhaustion from visible cards
  (`hand`, `table_attack`, `table_defense`, `trump_card`); when `deck_count==0`, prefer
  attacking ranks whose four copies are already accounted for on table + hand.
- `trump-economy`: when to spend vs hoard trumps; thresholds on remaining trump count.
  **Plateau watch:** rounds 4–6 (parents `candidate_0004` / `candidate_0000`) produced
  stepping stones only (search ~0.70–0.75); do not submit another deck/opponent gate tweak
  until a different family is tried.
- `endgame-tempo`: switch policy when stock is empty / few cards remain. Same plateau watch
  as trump-economy — H4/H5-style gates are saturated at current complexity.

## Confirmed dead-ends (do NOT re-propose)
_(none yet — the meta-agent appends here as Φ confirms a structural plateau)_

## Notes
- A family is "confirmed dead" only after multiple distinct attempts failed the holdout
  keep rule, not after a single low search score.
- Prefer the lowest-complexity member of a family that achieves the gain (Occam tie-break).
- B2 evaluation passes `memory=nullptr`; card-counting must use `LocalFeatures` only, not
  `MemoryFeatures` (B3 ablation path is not scored).
