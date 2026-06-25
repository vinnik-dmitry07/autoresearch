'''Rebuild results.tsv from analysis.ipynb embedded outputs + new probes.'''
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / 'analysis.ipynb'
OUT = ROOT / 'results.tsv'

HEADER = (
    'commit\topponent\tpoint_rate\tsearch_score\tlower_ci\tgames\tcomplexity\tstatus\tdescription\n'
)

# Known full-eval keeps (from notebook / full runs)
KEEPS = [
    ('228791f', 'B4', 0.49211, 0.68404, 0.49200, 10000000, 310, 'keep',
     'baseline B2 H1-H3 (min non-trump, low group, same-rank trump defense)'),
    ('2415f53', 'B4', 0.50461, 0.70002, 0.50447, 10000000, 210, 'keep',
     'exp A: drop H3 same-rank trump defense'),
    ('35330ec', 'B4', 0.52434, 0.72562, 0.52409, 10000000, 100, 'keep',
     'exp B: drop H2 + kDelta throw-in cap (H1-only); aggressive pile-on'),
    ('c263a3a', 'B4', 0.53748, 0.73239, 0.53723, 10000000, 100, 'keep',
     'exp G: endgame open low pair when min non-trump is singleton'),
    ('84c9321', 'B4', 0.54507, 0.73650, 0.54485, 10000000, 100, 'keep',
     'exp H: midgame pair-open min+2 + endgame pair + trump-strip fallback'),
]

DISCARDS = [
    ('069959b', 'B4', 0.54516, 0.73654, 0.54493, 10000000, 100, 'discard',
     'exp J: void-suit pile pressure inside H1 (full +0.00004 search, below keep bar)'),
    ('probe', 'B4', 0.53397, 0.73094, 0.53241, 200000, 100, 'discard',
     'exp K: defense voluntary take + same-rank trump (quick regression)'),
    ('probe', 'B4', 0.54409, 0.73727, 0.54246, 200000, 100, 'discard',
     'exp L: relaxed trump-strip opp<=4 trumps>=2 (B4 -0.001 quick)'),
    ('probe', 'B4', 0.54551, 0.73679, 0.54391, 200000, 100, 'discard',
     'exp M: late-game pair-open deck<=6 (neutral vs J on quick)'),
]

ABLATIONS = [
    ('228791f', 'B3vsB2', 0.50000, 0.68404, 0.50000, 10000000, 310, 'keep',
     'memory ablation baseline'),
    ('35330ec', 'B3vsB2', 0.50000, 0.72562, 0.50000, 10000000, 100, 'keep',
     'ablation after B'),
    ('c263a3a', 'B3vsB2', 0.50000, 0.73239, 0.50000, 10000000, 100, 'keep',
     'ablation after G'),
    ('84c9321', 'B3vsB2', 0.50000, 0.73650, 0.50000, 10000000, 100, 'keep',
     'ablation after H'),
]


def row(c, opp, pr, ss, lo, games, cx, st, desc) -> str:
    return f'{c}\t{opp}\t{pr:.6f}\t{ss:.6f}\t{lo:.6f}\t{games}\t{cx}\t{st}\t{desc}\n'


def main() -> None:
    lines = [HEADER]
    for r in KEEPS + DISCARDS + ABLATIONS:
        lines.append(row(*r))
    OUT.write_text(''.join(lines), encoding='utf-8')
    print(f'Wrote {len(lines)-1} rows to {OUT}')


if __name__ == '__main__':
    main()
