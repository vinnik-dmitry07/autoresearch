'''Batch-109: XW medium confirm + attack-side PIVOTs on WR base.'''
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

DEFENSE_BASE = '''        if (m.type != MoveType::DefendPlay) continue;
        const Card d = m.card;
        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

DEFENSE_M4 = DEFENSE_BASE.replace(
    'if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)',
    'if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)\n'
    '        const int tgt = m.target;\n'
    '        if (tgt >= 0 && tgt < L.n_table && L.atk[tgt] != NO_CARD &&\n'
    '            rank_of(d) == rank_of(L.atk[tgt]))\n'
    '            cost -= 4.0;',
)

ATTACK_V = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

TRUMP_HOARD = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (!pile_phase && L.deck_count >= 4 &&
            popcount(L.hand & SUIT_MASK[trump]) >= 3)
            v += 5.0;
        else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

VOID_HAND = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c)) &&
             (!pile_phase || popcount(L.hand) >= L.opponent_hand_count))
        v -= pile_phase ? 8.0 : 5.0;
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

PROBES = [
    ('XW', 'defense rank-match -4 medium confirm', BASELINE.replace(DEFENSE_BASE, DEFENSE_M4, 1), None, None),
    ('XZ', 'PIVOT open trump hoard deck>=4 trumps>=3', BASELINE, ATTACK_V, TRUMP_HOARD),
    ('YA', 'PIVOT pile void only hand>=opp', BASELINE, ATTACK_V, VOID_HAND),
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
        raise RuntimeError(f'{label} parse failed')
    b4, search = float(m.group(2)), float(m.group(1))
    return b4, search, b4 - 0.00176


def append_row(code: str, b4: float, search: float, lower: float, desc: str, games: int = 200000) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\tdiscard\texp {code} {desc} batch-109\n'
        )


def main() -> int:
    occam = len(BASELINE.replace(DEFENSE_BASE, DEFENSE_M4, 1).splitlines())
    print(f'Occam WR+defense-4: {occam} lines (+{occam - len(BASELINE.splitlines())} vs WR)', flush=True)

    # XW medium only (quick already 0.79560 in batch-108)
    src = PROBES[0][2]
    STRATEGY.write_text(src, encoding='utf-8')
    try:
        b4, search, lower = run_triage('XW', 'medium')
        append_row('XW', b4, search, lower, PROBES[0][1], 500000)
    finally:
        STRATEGY.write_text(BASELINE, encoding='utf-8')

    for code, desc, src, old, new in PROBES[1:]:
        patched = src.replace(old, new, 1) if old else src
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
