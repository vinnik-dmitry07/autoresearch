'''Run batch-91 EXPLORE rank/suit ordering quick probes.'''
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

VOID_LINE = '    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;'

UN_ATTACK = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (pile_phase) v = -v;  // UN: pile throw-in prefers highest non-trump junk
    else if (opp_likely_void_suit(L, suit_of(c))) v -= 5.0;'''

UO_DEF = '''        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);
        const Card atk = L.atk[m.target];
        if (atk != NO_CARD && suit_of(d) == suit_of(atk) && !is_trump(d, L.trump_suit))
            cost -= 0.25;  // UO: prefer same-suit cover tie-break'''

UP_ATTACK = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else {
        if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;
        if (!pile_phase) v += 0.05 * popcount(L.hand & SUIT_MASK[suit_of(c)]);  // UP: shed heavy suits on open
    }'''

UQ_VOID = '    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 5.0 : 10.0;  // UQ: stronger void on open'

PILE_RET = '''    const Card pile_card = legal.moves[best].card;
    if (!is_trump(pile_card, L.trump_suit)) return legal.moves[best];'''

UR_PILE = '''    const Card pile_card = legal.moves[best].card;
    if (!is_trump(pile_card, L.trump_suit)) {
        const CardMask nt = L.hand & ~SUIT_MASK[L.trump_suit];
        const int mnt = nt ? rank_of(lowest(nt)) : 0;
        if (rank_of(pile_card) > mnt + 4) return {MoveType::AttackDone, NO_CARD, 0};
        return legal.moves[best];
    }'''

DEF_BLOCK = '''        double cost = double(rank_of(d));
        if (is_trump(d, L.trump_suit)) cost += 50.0;  // prefer non-trump (rational base)
        if (mem) cost -= 0.001 * double(mem->unknown_rank_count[rank_of(d)]);'''

ATTACK_V_START = '''    double v = double(rank_of(c));
    if (is_trump(c, trump)) v += 100.0;
    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;'''

PROBES = [
    ('UN', 'pile throw-in highest non-trump junk', ATTACK_V_START, UN_ATTACK),
    ('UO', 'defense same-suit cover tie-break', DEF_BLOCK, UO_DEF),
    ('UP', 'open shed heavy-suit tie-break', ATTACK_V_START, UP_ATTACK),
    ('UQ', 'void bonus open -10 pile -5', VOID_LINE, UQ_VOID),
    ('UR', 'pile pass when throw-in rank > mnt+4', PILE_RET, UR_PILE),
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
        f'200000\t100\tdiscard\texp {code} {desc} batch-91\n'
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
    print('\nBatch 91 complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
