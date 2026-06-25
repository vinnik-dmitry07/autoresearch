'''Batch-106: meta WR ablation map + PIVOT pile-pass / suit tie / pair skip.'''
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

SUIT_TB = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        if (!pile_phase) v += 0.001 * double(suit_of(c));
    }
    if (mem) v -= 0.001 * double(mem->unknown_rank_count[rank_of(c)]);'''

PILE_HEAD = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;
    if (!is_trump(pile_card, L.trump_suit)) return legal.moves[best];'''

PILE_PASS = '''    // Optional throw-in / pile-on: dump lowest non-trump; finish pile may dump low trump.
    const Card pile_card = legal.moves[best].card;
    if (!is_trump(pile_card, L.trump_suit)) return legal.moves[best];
    if (L.deck_count > 0) {
        bool has_nt = false;
        for (int i = 0; i < legal.count; ++i) {
            if (legal.moves[i].type != MoveType::AttackPlay) continue;
            if (!is_trump(legal.moves[i].card, L.trump_suit)) { has_nt = true; break; }
        }
        if (!has_nt) return {MoveType::AttackDone, NO_CARD, 0};
    }'''

PROBES = [
    ('XP', 'PIVOT pile pass only-trump deck>0', BASELINE, PILE_HEAD, PILE_PASS),
    ('XQ', 'PIVOT open lowest-suit tie-break', BASELINE, ATTACK_V, SUIT_TB),
    ('XR', 'PIVOT endgame pair skip min+2', BASELINE,
     'for (int r = mnt + 1; r < NUM_RANKS; ++r)',
     'for (int r = mnt + 2; r < NUM_RANKS; ++r)'),
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
            f'{games}\t100\tdiscard\texp {code} {desc} batch-106\n'
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
