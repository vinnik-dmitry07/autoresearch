'''Batch-113: PIVOT qualitatively new mechanisms on WR base + dual reconfirm.'''
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

ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

SHORT_SUIT = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        if (!pile_phase)
            v -= 2.0 * double(6 - popcount(L.hand & SUIT_MASK[suit_of(c)]));
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

PILE_DEPTH = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        if (pile_phase &&
            popcount(L.hand & RANK_MASK[rank_of(c)] & ~SUIT_MASK[trump]) >= 2)
            v -= 3.0;
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

DEFENSE_BASE = '''        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

TIGHT_BEAT = '''        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        const int tgt = m.target;
        if (tgt >= 0 && tgt < L.n_table) {
            const Card atk = L.atk[tgt];
            if (atk != NO_CARD && !is_trump(d, L.trump_suit) && suit_of(d) == suit_of(atk)) {
                const int gap = rank_of(d) - rank_of(atk);
                if (gap > 0) cost += 2.0 * double(gap);
            }
        }
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

OPEN_HEAD = '''    if (!has_done) {
        const CardMask nt = L.hand & ~SUIT_MASK[L.trump_suit];'''

OPEN_PASS = '''    if (!has_done) {
        if (L.deck_count == 0 && L.opponent_hand_count == 1 && popcount(L.hand) == 2)
            return {MoveType::AttackDone, NO_CARD, 0};
        const CardMask nt = L.hand & ~SUIT_MASK[L.trump_suit];'''

PROBES = [
    ('YL', 'PIVOT open shortest-suit dump tie-break', BASELINE, ATTACK_V, SHORT_SUIT),
    ('YM', 'PIVOT pile rank hand-depth bonus', BASELINE, ATTACK_V, PILE_DEPTH),
    ('YN', 'PIVOT defense tight-beat overkill penalty', BASELINE, DEFENSE_BASE, TIGHT_BEAT),
    ('YO', 'PIVOT open pass deck==0 opp==1 hand==2', BASELINE, OPEN_HEAD, OPEN_PASS),
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
    if stage == 'dual':
        m0 = re.search(r'Dual seed 0: search=([\d.]+).* B4=([\d.]+)', out)
        m1 = re.search(r'Dual seed 1: search=([\d.]+).* B4=([\d.]+)', out)
        if not m0 or not m1:
            raise RuntimeError(f'{label} dual parse failed')
        search = (float(m0.group(1)) + float(m1.group(1))) / 2.0
        b4 = (float(m0.group(2)) + float(m1.group(2))) / 2.0
        return b4, search, b4 - 0.00176
    m = re.search(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    if not m:
        raise RuntimeError(f'{label} parse failed')
    b4, search = float(m.group(2)), float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-113\n'
        )


def main() -> int:
    # YP: WR dual reconfirm
    STRATEGY.write_text(BASELINE, encoding='utf-8')
    b4, search, lower = run_triage('YP', 'dual')
    append_row('YP', b4, search, lower, 'WR dual seed reconfirm', 400000)

    for code, desc, src, old, new in PROBES:
        STRATEGY.write_text(src.replace(old, new, 1), encoding='utf-8')
        try:
            b4, search, lower = run_triage(code, 'quick')
            append_row(code, b4, search, lower, desc)
            print(f'{code}: search {search:.5f} delta {search - float(BEST_SEARCH):+.5f}', flush=True)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
