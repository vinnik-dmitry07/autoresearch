'''Batch-103: EXPLOIT WR ablations + finish-window probes.'''
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / 'durak/src/strategy_heuristic.cpp'
RESULTS = ROOT / 'results.tsv'
BASELINE = STRATEGY.read_text(encoding='utf-8')
BEST_SEARCH = '0.79506'
BEST_B4 = '0.64489'

TOTAL_GATE = '''            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || total <= 16) {
                for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                    if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                        open_rank = r;
                        break;
                    }
                }
            }'''

NO_TOTAL_GATE = '''            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }'''

STRIP_ON = '''            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

STRIP_OFF = '''            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 0 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

PILE_WIN = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
        popcount(L.hand) >= L.opponent_hand_count &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

PILE_OPP4 = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 4 &&
        popcount(L.hand) >= L.opponent_hand_count &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

PILE_DECK2 = '''    if (L.deck_count <= 2 && L.opponent_hand_count <= 5 &&
        popcount(L.hand) >= L.opponent_hand_count &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

PROBES = [
    ('XC', 'ABLATE total<=16 gate off', BASELINE, TOTAL_GATE, NO_TOTAL_GATE),
    ('XD', 'ABLATE strip opp<=2 off', BASELINE, STRIP_ON, STRIP_OFF),
    ('XE', 'COMBO WR+pile opp<=4', BASELINE, PILE_WIN, PILE_OPP4),
    ('XF', 'PIVOT pile deck<=2 only', BASELINE, PILE_WIN, PILE_DECK2),
]


def run_triage(label: str, stage: str = 'quick') -> tuple[float, float, float]:
    env = {**dict(__import__('os').environ), 'BEST_SEARCH': BEST_SEARCH, 'BEST_B4': BEST_B4}
    print(f'\n=== {label}: {stage} ===', flush=True)
    proc = subprocess.run(
        ['cmd', '/c', 'scripts\\triage.bat', stage],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    print(out, flush=True)
    m = re.search(r'Gate [23] search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    if not m:
        raise RuntimeError(f'{label} parse failed')
    b4, search = float(m.group(2)), float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-103\n'
        )


def main() -> int:
    for code, desc, src, old, new in PROBES:
        STRATEGY.write_text(src.replace(old, new, 1), encoding='utf-8')
        try:
            b4, search, lower = run_triage(code, 'quick')
            append_row(code, b4, search, lower, desc)
            if search - float(BEST_SEARCH) >= 0.003:
                b4m, sm, lm = run_triage(code, 'medium')
                append_row(code, b4m, sm, lm, desc + ' medium', 500000)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
