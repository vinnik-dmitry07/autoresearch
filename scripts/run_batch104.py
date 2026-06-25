'''Batch-104: SWEEP total gate + WR ablate/COMBO/PIVOT.'''
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

PROBES = [
    ('XG', 'SWEEP total gate <=14', BASELINE, 'total <= 16', 'total <= 14'),
    ('XH', 'SWEEP total gate <=15', BASELINE, 'total <= 16', 'total <= 15'),
    ('XI', 'SWEEP total gate <=17', BASELINE, 'total <= 16', 'total <= 17'),
    ('XJ', 'ABLATE deck==0 pair only', BASELINE, 'L.deck_count <= 2', 'L.deck_count == 0'),
    ('XK', 'COMBO WR void pile -10', BASELINE, 'pile_phase ? 8.0 : 5.0', 'pile_phase ? 10.0 : 5.0'),
    ('XL', 'PIVOT pile opp<=6', BASELINE,
     'L.deck_count <= 3 && L.opponent_hand_count <= 5',
     'L.deck_count <= 3 && L.opponent_hand_count <= 6'),
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
            f'{games}\t100\tdiscard\texp {code} {desc} batch-104\n'
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
