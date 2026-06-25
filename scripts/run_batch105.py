'''Batch-105: PIVOT new mechanisms on WR base + Occam audit.'''
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

RANK_VOID = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) {
        bool rank_ok = !pile_phase;
        if (pile_phase) {
            const int r = rank_of(c);
            for (int ti = 0; ti < L.n_table; ++ti) {
                const Card a = L.atk[ti];
                const Card d = L.def[ti];
                if (a != NO_CARD && rank_of(a) == r) { rank_ok = true; break; }
                if (d != NO_CARD && rank_of(d) == r) { rank_ok = true; break; }
            }
        }
        if (rank_ok) v -= pile_phase ? 8.0 : 5.0;
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

PROBES = [
    ('XM', 'PIVOT pile trump deck==0 only',
     BASELINE,
     'L.deck_count <= 3 && L.opponent_hand_count <= 5',
     'L.deck_count == 0 && L.opponent_hand_count <= 5'),
    ('XN', 'PIVOT midgame pair min+1 cap',
     BASELINE,
     'for (int r = mnt; r <= mnt + 2 && r < NUM_RANKS; ++r)',
     'for (int r = mnt + 1; r <= mnt + 3 && r < NUM_RANKS; ++r)'),
    ('XO', 'PIVOT pile void rank-aware', BASELINE, ATTACK_V, RANK_VOID),
]

# Occam: WR=195 lines; CZ was 189 (batch-100 audit); +6 vs CZ, +3 vs TQ
CZ_LINES = 189
WR_LINES = len(BASELINE.splitlines())


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
            f'{games}\t100\tdiscard\texp {code} {desc} batch-105\n'
        )


def main() -> int:
    print(f'Occam audit: CZ={CZ_LINES} WR={WR_LINES} (+{WR_LINES - CZ_LINES} vs CZ)', flush=True)
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
