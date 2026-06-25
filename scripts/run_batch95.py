'''Run batch-95: TQ integration + n_table pass fine sweep.'''
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

PILE = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;'''


def tq_base() -> str:
    return BASELINE.replace(CZ_END, TQ_END)


def run_triage(label: str, stage: str = 'quick') -> tuple[float, float, float]:
    env = {**dict(__import__('os').environ), 'BEST_SEARCH': BEST_SEARCH, 'BEST_B4': BEST_B4}
    print(f'\n=== {label}: triage {stage} ===', flush=True)
    proc = subprocess.run(
        ['cmd', '/c', 'scripts\\triage.bat', stage],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    print(out, flush=True)
    m = re.search(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    if not m:
        raise RuntimeError(f'{label}: parse failed')
    search, b4 = float(m.group(1)), float(m.group(2))
    m_lo = re.search(r'lower_ci=([\d.]+)', out)
    lower = float(m_lo.group(1)) if m_lo else b4 - 0.00176
    return b4, search, lower


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    line = (
        f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
        f'{games}\t100\tdiscard\texp {code} {desc} batch-95\n'
    )
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(line)


def main() -> int:
    # VM: TQ endgame on CZ
    STRATEGY.write_text(tq_base(), encoding='utf-8')
    try:
        b4, search, lower = run_triage('VM', 'quick')
        append_row('VM', b4, search, lower, 'TQ endgame integration quick')
        if search - float(BEST_SEARCH) >= 0.003:
            b4m, sm, lm = run_triage('VM', 'medium')
            append_row('VM', b4m, sm, lm, 'TQ endgame integration medium', 500000)
    finally:
        STRATEGY.write_text(BASELINE, encoding='utf-8')

    for code, n, desc in [
        ('VN', 3, 'pile pass n_table>=3'),
        ('VO', 5, 'pile pass n_table>=5'),
        ('VP', 2, 'pile pass n_table>=2'),
    ]:
        src = BASELINE.replace(
            PILE,
            f'    if (L.n_table >= {n}) return {{MoveType::AttackDone, NO_CARD, 0}};\n' + PILE,
        )
        STRATEGY.write_text(src, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code, 'quick')
            append_row(code, b4, search, lower, desc)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')

    print('\nBatch 95 complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
