'''Batch-102: EXPLOIT on WR base — ablate, COMBO, SWEEP hand gate.'''
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

HAND_GE = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
        popcount(L.hand) >= L.opponent_hand_count &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

HAND_NO = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

HAND_GT = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
        popcount(L.hand) > L.opponent_hand_count &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

HAND_GE1 = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
        popcount(L.hand) >= L.opponent_hand_count + 1 &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

RANK_MATCH = '''    double v = double(rank_of(c));
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
    ('WX', 'ABLATE hand>=opp off (TQ pile)', BASELINE, HAND_GE, HAND_NO),
    ('WY', 'COMBO WR+rank-match pile', BASELINE, ATTACK_V, RANK_MATCH),
    ('WZ', 'SWEEP hand>opp pile gate', BASELINE, HAND_GE, HAND_GT),
    ('XA', 'SWEEP hand>=opp+1 pile gate', BASELINE, HAND_GE, HAND_GE1),
    ('XB', 'COMBO WR+deck>=6 midgame pair', BASELINE, 'L.deck_count >= 5', 'L.deck_count >= 6'),
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
        m3 = re.search(
            r'Gate 3 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out
        )
        if not m3:
            raise RuntimeError(f'{label} parse failed')
        b4, search = float(m3.group(2)), float(m3.group(1))
    else:
        b4, search = float(m.group(2)), float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-102\n'
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
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
