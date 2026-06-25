'''Run batch-90 PIVOT throw-in/pass timing quick probes.'''
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

PILE_BLOCK = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;
    if (!is_trump(pile_card, L.trump_suit)) return legal.moves[best];'''

UI_PILE = '''    // UI: pass when every throw-in is trump and deck still deep
    if (L.deck_count >= 4) {
        bool any_nt_throw = false;
        for (int i = 0; i < legal.count; ++i) {
            const Move& m = legal.moves[i];
            if (m.type != MoveType::AttackPlay) continue;
            if (!is_trump(m.card, L.trump_suit)) {
                any_nt_throw = true;
                break;
            }
        }
        if (!any_nt_throw) return {MoveType::AttackDone, NO_CARD, 0};
    }
    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;
    if (!is_trump(pile_card, L.trump_suit)) return legal.moves[best];'''

UJ_PILE = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;
    if (is_trump(pile_card, L.trump_suit) &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) == 1)
        return {MoveType::AttackDone, NO_CARD, 0};
    if (!is_trump(pile_card, L.trump_suit)) return legal.moves[best];'''

UK_PILE = PILE_BLOCK.replace('L.deck_count <= 3', 'L.deck_count <= 1')

OPEN_START = '''        int open_rank = mnt;
        if (L.deck_count >= 5) {'''

UL_OPEN = '''        int open_rank = mnt;
        if (nt == 0 && L.deck_count >= 3 &&
            popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {
            Move low_trump{MoveType::AttackDone, NO_CARD, 0};
            for (int i = 0; i < legal.count; ++i) {
                const Move& m = legal.moves[i];
                if (m.type != MoveType::AttackPlay || !is_trump(m.card, L.trump_suit)) continue;
                if (low_trump.type != MoveType::AttackPlay ||
                    rank_of(m.card) < rank_of(low_trump.card))
                    low_trump = m;
            }
            if (low_trump.type == MoveType::AttackPlay) return low_trump;
        } else if (L.deck_count >= 5) {'''

DEF_START = '''    // Rational base (shared with B1): if any uncovered card cannot be beaten, take now.
    for (int i = 0; i < L.n_table; ++i)
        if (L.def[i] == NO_CARD && !coverable[i]) return {MoveType::DefendTake, NO_CARD, 0};
    if (!any_defend) return {MoveType::DefendTake, NO_CARD, 0};'''

UM_DEF = '''    // UM: take when table nearly full even if coverable exists
    if (L.n_table >= 5) return {MoveType::DefendTake, NO_CARD, 0};
    // Rational base (shared with B1): if any uncovered card cannot be beaten, take now.
    for (int i = 0; i < L.n_table; ++i)
        if (L.def[i] == NO_CARD && !coverable[i]) return {MoveType::DefendTake, NO_CARD, 0};
    if (!any_defend) return {MoveType::DefendTake, NO_CARD, 0};'''

PROBES = [
    ('UI', 'pass when only trump throw-ins deck>=4', [('pile', UI_PILE)]),
    ('UJ', 'pass when throw-in is sole trump', [('pile', UJ_PILE)]),
    ('UK', 'pile trump dump deck<=1 only', [('pile', UK_PILE)]),
    ('UL', 'open lowest trump when void nt==0 deck>=3', [('open', UL_OPEN)]),
    ('UM', 'defense take when n_table>=5', [('def', UM_DEF)]),
]


def run_triage(label: str) -> tuple[float, float, float]:
    env = {**dict(__import__('os').environ), 'BEST_SEARCH': BEST_SEARCH, 'BEST_B4': BEST_B4}
    print(f'\n=== {label}: triage quick ===', flush=True)
    proc = subprocess.run(
        ['cmd', '/c', 'scripts\\triage.bat', 'quick'],
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


def append_row(code: str, b4: float, search: float, lower: float, desc: str) -> None:
    line = (
        f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
        f'200000\t100\tdiscard\texp {code} {desc} batch-90\n'
    )
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(line)


def main() -> int:
    for code, desc, patches in PROBES:
        src = BASELINE
        for kind, repl in patches:
            if kind == 'pile':
                src = src.replace(PILE_BLOCK, repl)
            elif kind == 'open':
                src = src.replace(OPEN_START, repl)
            elif kind == 'def':
                src = src.replace(DEF_START, repl)
        STRATEGY.write_text(src, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code)
            append_row(code, b4, search, lower, desc)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    print('\nBatch 90 complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
