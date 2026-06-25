'''Batch-100: meta TQ doc probes + PIVOT trump hoard / TQ variants.'''
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

ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

WL_ATTACK = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) {
        v += 100.0;
        if (!pile_phase && L.deck_count > 2) v += 200.0;
    } else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

WM_ATTACK = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c)) && L.deck_count <= 4)
        v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

VH_ATTACK = '''    double v = double(rank_of(c));
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

PROBES = [
    ('WL', 'open trump hoard deck>2 +200 penalty', BASELINE, ATTACK_V, WL_ATTACK),
    ('WM', 'void bonus only when deck<=4', BASELINE, ATTACK_V, WM_ATTACK),
    ('WN', 'TQ control quick', BASELINE.replace(CZ_END, TQ_END), None, None),
    ('WO', 'TQ+pile trump deck<=1 only', BASELINE.replace(CZ_END, TQ_END),
     'L.deck_count <= 3 && L.opponent_hand_count <= 5',
     'L.deck_count <= 1 && L.opponent_hand_count <= 5'),
    ('WP', 'TQ+pile rank-match', BASELINE.replace(CZ_END, TQ_END), ATTACK_V, VH_ATTACK),
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
        raise RuntimeError(label)
    return float(m.group(2)), float(m.group(1)), float(m.group(2)) - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-100\n'
        )


def main() -> int:
    cz_lines = len(BASELINE.splitlines())
    tq_lines = len(BASELINE.replace(CZ_END, TQ_END).splitlines())
    print(f'Occam audit: CZ={cz_lines} lines, TQ={tq_lines} lines (+{tq_lines - cz_lines})', flush=True)

    for item in PROBES:
        code, desc = item[0], item[1]
        src = item[2]
        if len(item) > 4 and item[3] and item[4]:
            old, new = item[3], item[4]
            if old in (ATTACK_V,):
                src = src.replace(old, new)
            else:
                src = src.replace(old, new, 1)
        STRATEGY.write_text(src, encoding='utf-8')
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
