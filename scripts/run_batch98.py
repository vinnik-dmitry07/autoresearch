'''Run batch-98 PIVOT probes outside TQ/CZ attack stack.'''
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

WB_ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        const int r = rank_of(c);
        for (int ti = 0; ti < L.n_table; ++ti) {
            const Card a = L.atk[ti];
            const Card d = L.def[ti];
            if (a != NO_CARD && rank_of(a) == r) { v -= 2.0; break; }
            if (d != NO_CARD && rank_of(d) == r) { v -= 2.0; break; }
        }
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

WC_ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        if (!pile_phase) v += 0.08 * popcount(L.hand & SUIT_MASK[suit_of(c)]);
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

VOID_LINE = '    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;'
WD_VOID = '    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 12.0 : 5.0;'

DEF_LOOP = '''    int best = -1;
    double best_c = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);
        if (cost < best_c) {
            best_c = cost;
            best = i;
        }
    }
    return best >= 0 ? legal.moves[best] : Move{MoveType::DefendTake, NO_CARD, 0};'''

WA_DEF = '''    int best = -1;
    double best_c = 1e18;
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        const Card atk = L.atk[m.target];
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;
        if (atk != NO_CARD && rank_of(d) > rank_of(atk) + 2) cost += 1e6;
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);
        if (cost < best_c) {
            best_c = cost;
            best = i;
        }
    }
    return best >= 0 ? legal.moves[best] : Move{MoveType::DefendTake, NO_CARD, 0};'''

WE_DEF = '''    int best = -1;
    double best_c = 1e18;
    int max_atk_rank = -1;
    for (int ti = 0; ti < L.n_table; ++ti) {
        const Card a = L.atk[ti];
        if (a != NO_CARD) max_atk_rank = max_atk_rank < rank_of(a) ? rank_of(a) : max_atk_rank;
    }
    for (int i = 0; i < legal.count; ++i) {
        const Move& m = legal.moves[i];
        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);
        if (cost < best_c) {
            best_c = cost;
            best = i;
        }
    }
    if (max_atk_rank >= 0 && best_c > double(max_atk_rank) + 8.0)
        return Move{MoveType::DefendTake, NO_CARD, 0};
    return best >= 0 ? legal.moves[best] : Move{MoveType::DefendTake, NO_CARD, 0};'''

PROBES = [
    ('WA', 'defense rank cap +2 over attack', DEF_LOOP, WA_DEF),
    ('WB', 'attack prefer table-matching rank dump', ATTACK_V, WB_ATTACK_V),
    ('WC', 'open shed light-suit tie-break', ATTACK_V, WC_ATTACK_V),
    ('WD', 'pile void bonus -12 open -5', VOID_LINE, WD_VOID),
    ('WE', 'defense take when cover cost > atk+8', DEF_LOOP, WE_DEF),
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
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'200000\t100\tdiscard\texp {code} {desc} batch-98\n'
        )


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
    print('\nBatch 98 complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
