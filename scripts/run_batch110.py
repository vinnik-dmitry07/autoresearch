'''Batch-110: COMBO WR+def−4 dual/medium + attack PIVOTs on WR base.'''
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

COMBO_WR_DEF4 = BASELINE.replace(DEFENSE_BASE, DEFENSE_M4, 1)

MIDGAME_PAIR = '''        if (L.deck_count >= 5) {
            for (int r = mnt; r <= mnt + 2 && r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
        }'''

MIDGAME_HAND = '''        if (L.deck_count >= 5 && popcount(L.hand) >= L.opponent_hand_count) {
            for (int r = mnt; r <= mnt + 2 && r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
        }'''

PROBES = [
    ('YB', 'COMBO WR+defense rank-match -4 dual', COMBO_WR_DEF4, None, None, 'dual'),
    ('YC', 'PIVOT strip opp==1 only on WR', BASELINE,
     'L.deck_count == 0 && L.opponent_hand_count <= 2',
     'L.deck_count == 0 && L.opponent_hand_count == 1'),
    ('YD', 'PIVOT midgame pair only hand>=opp on WR', BASELINE, MIDGAME_PAIR, MIDGAME_HAND),
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
        m0 = re.search(
            r'Dual seed 0: search=[\d.]+ .* B4=([\d.]+)',
            out,
        )
        m1 = re.search(
            r'Dual seed 1: search=[\d.]+ .* B4=([\d.]+)',
            out,
        )
        ms0 = re.search(r'Dual seed 0: search=([\d.]+)', out)
        ms1 = re.search(r'Dual seed 1: search=([\d.]+)', out)
        if not m0 or not m1 or not ms0 or not ms1:
            raise RuntimeError(f'{label} dual parse failed')
        search = (float(ms0.group(1)) + float(ms1.group(1))) / 2.0
        b4 = (float(m0.group(1)) + float(m1.group(1))) / 2.0
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
            f'{games}\t100\tdiscard\texp {code} {desc} batch-110\n'
        )


def main() -> int:
    # YB: dual then medium if dual agrees (both seeds positive delta)
    src = PROBES[0][2]
    STRATEGY.write_text(src, encoding='utf-8')
    try:
        b4, search, lower = run_triage('YB', 'dual')
        append_row('YB', b4, search, lower, PROBES[0][1], 400000)
        b4m, sm, lm = run_triage('YB', 'medium')
        append_row('YB', b4m, sm, lm, PROBES[0][1] + ' medium', 500000)
    finally:
        STRATEGY.write_text(BASELINE, encoding='utf-8')

    for code, desc, src, old, new, *_ in PROBES[1:]:
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
