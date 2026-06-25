'''Run batch-94 PIVOT table-depth / rank-match quick probes on CZ base.'''
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

ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

VH_ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        if (pile_phase) {
            const int r = rank_of(c);
            for (int ti = 0; ti < L.n_table; ++ti) {
                const Card a = L.atk[ti];
                const Card d = L.def[ti];
                if (a != NO_CARD && rank_of(a) == r) { v -= 4.0; break; }
                if (d != NO_CARD && rank_of(d) == r) { v -= 4.0; break; }
            }
        }
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

PILE_START = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;'''

VJ_PILE = '''    // VJ: pass early when table already deep
    if (L.n_table >= 4) return {MoveType::AttackDone, NO_CARD, 0};
    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;'''

STRIP_COND = '''            if (open_rank == mnt && L.opponent_hand_count <= 2 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

VK_STRIP = '''            if (open_rank == mnt && L.n_table == 0 && L.opponent_hand_count <= 2 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

DEF_COST = '''        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

VL_DEF = '''        double cost = double(rank_of(d));
        const Card atk = L.atk[m.target];
        if (is_trump(d, L.trump_suit)) {
            if (atk == NO_CARD || !is_trump(atk, L.trump_suit)) cost += 1e6;
            else cost += 50.0;
        }
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

# VI: at open, if table has ranks and we hold a pair matching a table rank, prefer that open rank
VI_OPEN = '''        int open_rank = mnt;
        if (L.n_table > 0) {
            for (int ti = 0; ti < L.n_table; ++ti) {
                const Card a = L.atk[ti];
                const Card d = L.def[ti];
                const int ranks[2] = {a != NO_CARD ? rank_of(a) : -1,
                                      d != NO_CARD ? rank_of(d) : -1};
                for (int ri = 0; ri < 2; ++ri) {
                    const int tr = ranks[ri];
                    if (tr < 0) continue;
                    if (popcount(L.hand & RANK_MASK[tr] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                        open_rank = tr;
                        break;
                    }
                }
                if (open_rank != mnt) break;
            }
        }
        if (L.deck_count >= 5) {'''

OPEN_START = '''        int open_rank = mnt;
        if (L.deck_count >= 5) {'''

PROBES = [
    ('VH', 'pile throw-in rank-match table bonus', ATTACK_V, VH_ATTACK_V),
    ('VI', 'open pair prefer table-matching rank', OPEN_START, VI_OPEN),
    ('VJ', 'pile pass when n_table>=4', PILE_START, VJ_PILE),
    ('VK', 'strip only when n_table==0', STRIP_COND, VK_STRIP),
    ('VL', 'defense trump only vs trump attack', DEF_COST, VL_DEF),
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
        f'200000\t100\tdiscard\texp {code} {desc} batch-94\n'
    )
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(line)


def main() -> int:
    for code, desc, old, new in PROBES:
        src = BASELINE.replace(old, new)
        if src == BASELINE:
            print(f'WARN {code}: patch did not apply', flush=True)
        STRATEGY.write_text(src, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code)
            append_row(code, b4, search, lower, desc)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    print('\nBatch 94 complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
