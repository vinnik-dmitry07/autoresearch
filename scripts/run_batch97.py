'''Batch-97: TQ + deck>=6 midgame x total gate fine sweep.'''
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

TQ_TMPL = '''        } else if (mnt < NUM_RANKS && L.deck_count <= 2 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || total <= {total_cap}) {
                for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                    if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                        open_rank = r;
                        break;
                    }
                }
            }
            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&'''


def build_tq(total_cap: int, deck6: bool) -> str:
    tq = TQ_TMPL.replace('{total_cap}', str(total_cap))
    s = BASELINE.replace(CZ_END, tq)
    if deck6:
        s = s.replace('L.deck_count >= 5', 'L.deck_count >= 6', 1)
    return s


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
        raise RuntimeError(label)
    search, b4 = float(m.group(1)), float(m.group(2))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-97\n'
        )


def main() -> int:
    probes = [
        ('VV', 15, True, 'TQ deck>=6 total<=15'),
        ('VW', 17, True, 'TQ deck>=6 total<=17'),
        ('VX', 14, True, 'TQ deck>=6 total<=14'),
        ('VY', 16, True, 'TQ deck>=6 total<=16 control'),
        ('VZ', 16, False, 'TQ total<=16 medium seed check'),
    ]
    for code, cap, d6, desc in probes:
        STRATEGY.write_text(build_tq(cap, d6), encoding='utf-8')
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
