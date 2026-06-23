'''Batch-111: attack timing PIVOTs on WR base.'''
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

PILE_HEAD = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;'''

PILE_PASS4 = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    if (L.n_table >= 4) return {MoveType::AttackDone, NO_CARD, 0};
    const Card pile_card = legal.moves[best].card;'''

TOTAL_GATE = '''            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || total <= 16) {'''

TOTAL_GATE18 = '''            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || total <= 18) {'''

PROBES = [
    ('YE', 'PIVOT pass throw-in n_table>=4 on WR', BASELINE, PILE_HEAD, PILE_PASS4),
    ('YF', 'PIVOT endgame pair skip total>18 on WR', BASELINE, TOTAL_GATE, TOTAL_GATE18),
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
    b4, search = float(m.group(2)), float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-111\n'
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
