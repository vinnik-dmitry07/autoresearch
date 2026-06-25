'''Batch-101: PIVOT on TQ base — strip opp==1, hand-size pile, n_table pass, total gate.'''
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

CZ_END = '''        } else if (mnt < NUM_RANKS && L.deck_count == 0 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
            if (open_rank == mnt && L.opponent_hand_count <= 2 &&'''

TQ_END = '''        } else if (mnt < NUM_RANKS && L.deck_count <= 2 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || total <= 16) {
                for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                    if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                        open_rank = r;
                        break;
                    }
                }
            }
            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&'''

TQ_BASE = BASELINE.replace(CZ_END, TQ_END)

PROBES = [
    ('WQ', 'TQ strip opp==1 only',
     TQ_BASE,
     'L.opponent_hand_count <= 2',
     'L.opponent_hand_count == 1'),
    ('WR', 'TQ pile hand>=opp',
     TQ_BASE,
     'L.deck_count <= 3 && L.opponent_hand_count <= 5 &&\n        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1',
     'L.deck_count <= 3 && L.opponent_hand_count <= 5 &&\n        popcount(L.hand) >= L.opponent_hand_count &&\n        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1'),
    ('WS', 'TQ skip throw-in n_table>=3',
     TQ_BASE,
     '    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.\n    const Card pile_card',
     '    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.\n    if (L.n_table >= 3) return {MoveType::AttackDone, NO_CARD, 0};\n    const Card pile_card'),
    ('WT', 'TQ total gate <=14',
     TQ_BASE,
     'total <= 16',
     'total <= 14'),
    ('WU', 'TQ total gate <=18',
     TQ_BASE,
     'total <= 16',
     'total <= 18'),
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
    m = re.search(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    if not m:
        raise RuntimeError(f'{label} parse failed')
    b4 = float(m.group(2))
    search = float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-101\n'
        )


def main() -> int:
    for code, desc, src, old, new in PROBES:
        patched = src.replace(old, new, 1)
        STRATEGY.write_text(patched, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code, 'quick')
            append_row(code, b4, search, lower, desc)
            if search - float(BEST_SEARCH) >= 0.003:
                b4m, sm, lm = run_triage(code, 'medium')
                append_row(code, b4m, sm, lm, desc + ' medium', 500000)
                if sm >= 0.79441:
                    print(f'*** {code} crosses keep bar at medium — consider full ***', flush=True)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
