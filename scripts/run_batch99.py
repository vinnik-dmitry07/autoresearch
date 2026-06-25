'''Run batch-99 EXPLORE attack micro-tweaks on CZ base.'''
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / 'durak/src/strategy_heuristic.cpp'
RESULTS = ROOT / 'results.tsv'
BASELINE = STRATEGY.read_text(encoding='utf-8')
BEST_SEARCH = '0.78941'
BEST_B4 = '0.63676'

PROBES = [
    ('WF', 'midgame pair cap min+1', 'mnt + 2', 'mnt + 1'),
    ('WG', 'endgame pair skip min+4', 'mnt + 1; r < NUM_RANKS; ++r', 'mnt + 1; r <= mnt + 4 && r < NUM_RANKS; ++r'),
    ('WH', 'pile trump opp<=4', 'opponent_hand_count <= 5', 'opponent_hand_count <= 4'),
    ('WI', 'strip trumps>=2 opp<=2', 'popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1',
     'popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 2'),
    ('WJ', 'void open -6 pile -10', 'pile_phase ? 8.0 : 5.0', 'pile_phase ? 10.0 : 6.0'),
]


def run_triage(label: str) -> tuple[float, float, float]:
    env = {**dict(__import__('os').environ), 'BEST_SEARCH': BEST_SEARCH, 'BEST_B4': BEST_B4}
    print(f'\n=== {label}: quick ===', flush=True)
    proc = subprocess.run(
        ['cmd', '/c', 'scripts\\triage.bat', 'quick'],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    print(out, flush=True)
    m = re.search(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    if not m:
        raise RuntimeError(label)
    search, b4 = float(m.group(1)), float(m.group(2))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'200000\t100\tdiscard\texp {code} {desc} batch-99\n'
        )


def main() -> int:
    for code, desc, old, new in PROBES:
        src = BASELINE
        if code == 'WG':
            src = src.replace(
                'for (int r = mnt + 1; r < NUM_RANKS; ++r) {',
                'for (int r = mnt + 1; r <= mnt + 4 && r < NUM_RANKS; ++r) {',
                1,
            )
        elif code == 'WH':
            src = src.replace(
                'if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&',
                'if (L.deck_count <= 3 && L.opponent_hand_count <= 4 &&',
                1,
            )
        elif code == 'WI':
            src = src.replace(
                'if (open_rank == mnt && L.opponent_hand_count <= 2 &&\n                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1)',
                'if (open_rank == mnt && L.opponent_hand_count <= 2 &&\n                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 2)',
                1,
            )
        else:
            src = src.replace(old, new)
        STRATEGY.write_text(src, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code)
            append_row(code, b4, search, lower, desc)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
