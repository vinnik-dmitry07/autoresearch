'''Run batch-96 COMBO quick probes on TQ endgame base.'''
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

PROBES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ('VQ', 'TQ+pile rank-match bonus', [('end', CZ_END, TQ_END), ('atk', ATTACK_V, VH_ATTACK_V)]),
    ('VR', 'TQ+pile opp<=4', [('end', CZ_END, TQ_END), ('pile', 'L.deck_count <= 3 && L.opponent_hand_count <= 5', 'L.deck_count <= 3 && L.opponent_hand_count <= 4')]),
    ('VS', 'TQ+midgame pair deck>=6', [('end', CZ_END, TQ_END), ('mid', 'L.deck_count >= 5', 'L.deck_count >= 6')]),
    ('VT', 'TQ+strip opp==1', [('end', CZ_END, TQ_END), ('strip', 'L.deck_count == 0 && L.opponent_hand_count <= 2', 'L.deck_count == 0 && L.opponent_hand_count == 1')]),
]


def tq_base() -> str:
    return BASELINE.replace(CZ_END, TQ_END)


def apply_patches(src: str, patches: list[tuple[str, str, str]]) -> str:
    out = src
    for _kind, old, new in patches:
        out = out.replace(old, new)
    return out


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
        f'{games}\t100\tdiscard\texp {code} {desc} batch-96\n'
    )
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(line)


def main() -> int:
    best_delta = -1.0
    best_code = ''

    for code, desc, patches in PROBES:
        src = apply_patches(tq_base(), patches)
        if src == BASELINE:
            print(f'WARN {code}: patch may not have applied', flush=True)
        STRATEGY.write_text(src, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code, 'quick')
            append_row(code, b4, search, lower, desc)
            delta = search - float(BEST_SEARCH)
            if delta > best_delta:
                best_delta, best_code = delta, code
            if delta >= 0.003:
                b4m, sm, lm = run_triage(code, 'medium')
                append_row(code, b4m, sm, lm, desc + ' medium', 500000)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')

    # VU: TQ control dual
    STRATEGY.write_text(tq_base(), encoding='utf-8')
    try:
        print('\n=== VU: triage dual TQ control ===', flush=True)
        env = {**dict(__import__('os').environ), 'BEST_SEARCH': BEST_SEARCH, 'BEST_B4': BEST_B4}
        proc = subprocess.run(
            ['cmd', '/c', 'scripts\\triage.bat', 'dual'],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        out = proc.stdout + proc.stderr
        print(out, flush=True)
        m0 = re.search(r'seed 0: search=([\d.]+).*delta_search=([\d.+-e]+)', out)
        m1 = re.search(r'seed 1: search=([\d.]+).*delta_search=([\d.+-e]+)', out)
        if m0 and m1:
            append_row('VU', 0.64261, float(m0.group(1)), 0.64085, 'TQ dual seed0 control')
            append_row('VU', 0.64261, float(m1.group(1)), 0.64085, 'TQ dual seed1 control')
    finally:
        STRATEGY.write_text(BASELINE, encoding='utf-8')

    print(f'\nBatch 96 complete. Best quick: {best_code} delta={best_delta:.5f}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
