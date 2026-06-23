'''Batch-112: ABLATE WR stack decomposition — confirm minimal / simplification hunt.'''
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

MIDGAME_PAIR = '''        if (L.deck_count >= 5) {
            for (int r = mnt; r <= mnt + 2 && r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
        } else if'''

MIDGAME_OFF = '''        if (false) {
        } else if'''

VOID_PEN = '''    else if (opp_likely_void_suit(L, suit_of(c))) v -= pile_phase ? 8.0 : 5.0;'''

VOID_OFF = '''    else if (false) v -= 0.0;'''

ENDGAME_PAIR = '''        } else if (mnt < NUM_RANKS && L.deck_count <= 2 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || total <= 16) {
                for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                    if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                        open_rank = r;
                        break;
                    }
                }
            }'''

ENDGAME_CZ = '''        } else if (mnt < NUM_RANKS && L.deck_count == 0 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }'''

PILE_TRUMP = '''    if (L.deck_count <= 3 && L.opponent_hand_count <= 5 &&
        popcount(L.hand) >= L.opponent_hand_count &&
        popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {
        Move low_trump{MoveType::AttackDone, NO_CARD, 0};
        for (int i = 0; i < legal.count; ++i) {
            const Move& m = legal.moves[i];
            if (m.type != MoveType::AttackPlay || !is_trump(m.card, L.trump_suit)) continue;
            if (low_trump.type != MoveType::AttackPlay ||
                rank_of(m.card) < rank_of(low_trump.card))
                low_trump = m;
        }
        if (low_trump.type == MoveType::AttackPlay) return low_trump;
    }'''

PILE_OFF = '''    if (false) {
    }'''

STRIP_ON = '''            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

STRIP_OFF = '''            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 0 &&
                popcount(L.hand & SUIT_MASK[L.trump_suit]) >= 1) {'''

PROBES = [
    ('YG', 'ABLATE pile trump dump off', BASELINE, PILE_TRUMP, PILE_OFF),
    ('YH', 'ABLATE midgame pair path off', BASELINE, MIDGAME_PAIR, MIDGAME_OFF),
    ('YI', 'ABLATE void penalty off', BASELINE, VOID_PEN, VOID_OFF),
    ('YJ', 'ABLATE deck<=2 pair (CZ deck==0 only)', BASELINE, ENDGAME_PAIR, ENDGAME_CZ),
    ('YK', 'ABLATE strip opp<=2 off', BASELINE, STRIP_ON, STRIP_OFF),
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
            f'{games}\t100\tdiscard\texp {code} {desc} batch-112\n'
        )


def main() -> int:
    print(f'Occam WR baseline: {len(BASELINE.splitlines())} lines', flush=True)
    for code, desc, src, old, new in PROBES:
        STRATEGY.write_text(src.replace(old, new, 1), encoding='utf-8')
        try:
            b4, search, lower = run_triage(code, 'quick')
            append_row(code, b4, search, lower, desc)
            delta = search - float(BEST_SEARCH)
            print(f'{code}: search {search:.5f} delta {delta:+.5f}', flush=True)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
