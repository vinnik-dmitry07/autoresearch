# Heuristic family map (maintained by the meta-agent)

A living catalog of Durak strategy heuristic *families* the inner agent can draw from, plus
families that have been confirmed dead. The inner agent reads the harness Φ (which derives
dead-ends from here and from `program.md`); the meta-agent curates this file from evidence.

## Active families (try these)
- `trump-economy`: when to spend vs hoard trumps; thresholds on remaining trump count.
- `card-counting`: track seen ranks to bias attack/defense once the deck is exhausted.
- `endgame-tempo`: switch policy when stock is empty / few cards remain.
- `pair-baiting`: provoke the opponent into breaking pairs/low cards early.

## Confirmed dead-ends (do NOT re-propose)
_(none yet — the meta-agent appends here as Φ confirms a structural plateau)_

## Notes
- A family is "confirmed dead" only after multiple distinct attempts failed the holdout
  keep rule, not after a single low search score.
- Prefer the lowest-complexity member of a family that achieves the gain (Occam tie-break).
