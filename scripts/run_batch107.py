'''Batch-107: meta plateau + PIVOT ultra-endgame / defense rank-match + dual reconfirm.'''
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

ATTACK_HEAD = '''Move choose_attack(const LocalFeatures& L, const MemoryFeatures* mem, const LegalMoves& legal,
                   bool has_done) {
    const int best = pick_lowest_attack(L, mem, legal, -1, false, has_done);'''

ULTRA_PASS = '''Move choose_attack(const LocalFeatures& L, const MemoryFeatures* mem, const LegalMoves& legal,
                   bool has_done) {
    if (has_done && L.deck_count == 0 && popcount(L.hand) == 1)
        return {MoveType::AttackDone, NO_CARD, 0};
    const int best = pick_lowest_attack(L, mem, legal, -1, false, has_done);'''

DEFENSE_LOOP = '''        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

DEFENSE_RANK = '''        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        const int tgt = m.target;
        if (tgt >= 0 && tgt < L.n_table && L.atk[tgt] != NO_CARD &&
            rank_of(d) == rank_of(L.atk[tgt]))
            cost -= 3.0;
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

PROBES = [
    ('XS', 'PIVOT ultra-endgame pass hand==1 deck==0', BASELINE, ATTACK_HEAD, ULTRA_PASS),
    ('XT', 'PIVOT defense rank-match cover -3', BASELINE, DEFENSE_LOOP, DEFENSE_RANK),
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
        m2 = re.search(r'search_score=([\d.]+).*?point_rate=([\d.]+)', out, re.DOTALL)
        if not m2:
            raise RuntimeError(f'{label} parse failed')
        b4, search = float(m2.group(2)), float(m2.group(1))
    else:
        b4, search = float(m.group(2)), float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-107\n'
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

    b4, search, lower = run_triage('XU', 'dual')
    append_row('XU', b4, search, lower, 'WR dual seed reconfirm', 400000)
    return 0


if __name__ == '__main__':
    sys.exit(main())
