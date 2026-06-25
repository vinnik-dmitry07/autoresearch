'''Run batch-89 ABLATE quick probes and append results.tsv rows.'''
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / 'durak' / 'src' / 'strategy_heuristic.cpp'
RESULTS = ROOT / 'results.tsv'
BASELINE = STRATEGY.read_text(encoding='utf-8')

BEST_SEARCH = '0.78941'
BEST_B4 = '0.63676'

# CZ endgame block (baseline)
CZ_END = '''        } else if (mnt < NUM_RANKS && L.deck_count == 0 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
            if (open_rank == mnt && L.opponent_hand_count <= 2 &&'''

SD_END = '''        } else if (mnt < NUM_RANKS && L.deck_count <= 2 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&'''

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

UF_END = '''        } else if (mnt < NUM_RANKS &&
                   (L.deck_count == 0 ||
                    (L.deck_count == 2 &&
                     L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table <= 16)) &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                    open_rank = r;
                    break;
                }
            }
            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&'''

UD_END = '''        } else if (mnt < NUM_RANKS && L.deck_count <= 2 &&
                   popcount(L.hand & RANK_MASK[mnt] & ~SUIT_MASK[L.trump_suit]) == 1) {
            const int total = L.deck_count + popcount(L.hand) + L.opponent_hand_count + L.n_table;
            if (L.deck_count != 2 || (total > 10 && total <= 16)) {
                for (int r = mnt + 1; r < NUM_RANKS; ++r) {
                    if (popcount(L.hand & RANK_MASK[r] & ~SUIT_MASK[L.trump_suit]) >= 2) {
                        open_rank = r;
                        break;
                    }
                }
            }
            if (open_rank == mnt && L.deck_count == 0 && L.opponent_hand_count <= 2 &&'''

PROBES = [
    ('UB', 'SD ablate TQ total gate off', SD_END, None),
    ('UC', 'CZ ablate deck<=2 pair (SP ref)', CZ_END, None),
    ('UD', 'TQ deck==2 pair total 11-16 window', UD_END, None),
    ('UE', 'TQ ablate TW min+3 (control)', TQ_END, 'mnt + 2'),
    ('UF', 'deck==2+total<=16 on CZ no deck==1', UF_END, None),
]

TW_MID = 'mnt + 3'


def apply_probe(src: str, end_block: str, midgame_cap: str | None) -> str:
    out = src.replace(CZ_END, end_block)
    if midgame_cap == 'mnt + 2':
        out = out.replace('mnt + 3', 'mnt + 2')
        out = out.replace(TW_MID, 'mnt + 2')
    elif midgame_cap == TW_MID:
        out = out.replace('r <= mnt + 2', f'r <= {TW_MID}')
    return out


def run_triage(label: str) -> tuple[float, float, float]:
    env = {
        **dict(__import__('os').environ),
        'BEST_SEARCH': BEST_SEARCH,
        'BEST_B4': BEST_B4,
    }
    print(f'\n=== {label}: triage quick ===', flush=True)
    proc = subprocess.run(
        ['cmd', '/c', 'scripts\\triage.bat', 'quick'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    print(out, flush=True)
    m_b4 = re.search(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    m_lo = re.search(r'lower_ci=([\d.]+)', out)
    if not m_b4:
        raise RuntimeError(f'{label}: could not parse triage output')
    search = float(m_b4.group(1))
    b4 = float(m_b4.group(2))
    lower = float(m_lo.group(1)) if m_lo else b4 - 0.00176
    return b4, search, lower


def append_row(code: str, b4: float, search: float, lower: float, desc: str) -> None:
    line = (
        f'probe\tB4\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
        f'200000\t100\tdiscard\texp {code} {desc} batch-89\n'
    )
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(line)
    print(f'Logged: {line.strip()}', flush=True)


def main() -> int:
    # UE uses TQ base + ensure midgame is mnt+2 (baseline), TW ablate = no min+3 change
    # Run TW variant separately for comparison
    probes = list(PROBES)
    probes[3] = ('UE', 'TQ control midgame min+2', TQ_END, None)
    probes.append(
        ('UG', 'TW TQ+min+3 confirm', TQ_END, TW_MID),
    )

    for code, desc, end_block, mid in probes:
        src = BASELINE
        if mid == TW_MID:
            src = src.replace('r <= mnt + 2', f'r <= {TW_MID}')
        patched = apply_probe(src, end_block, mid)
        if patched == src and code not in ('UC',):
            print(f'WARN {code}: patch may not have applied', flush=True)
        STRATEGY.write_text(patched, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code)
            append_row(code, b4, search, lower, desc)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')

    print('\nBatch 89 quick complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
