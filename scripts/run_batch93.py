'''Run batch-93 SWEEP pile opp threshold quick probes on CZ base.'''
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

PROBES = [
    ('VC', 'pile trump opp<=3', 'opponent_hand_count <= 5', 'opponent_hand_count <= 3'),
    ('VD', 'pile trump opp<=4', 'opponent_hand_count <= 5', 'opponent_hand_count <= 4'),
    ('VE', 'pile trump opp<=6', 'opponent_hand_count <= 5', 'opponent_hand_count <= 6'),
    ('VF', 'pile trump opp<=7', 'opponent_hand_count <= 5', 'opponent_hand_count <= 7'),
    ('VG', 'pile trump deck<=2 opp<=5', 'L.deck_count <= 3 && L.opponent_hand_count <= 5',
     'L.deck_count <= 2 && L.opponent_hand_count <= 5'),
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
        f'200000\t100\tdiscard\texp {code} {desc} batch-93\n'
    )
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(line)


def main() -> int:
    for code, desc, old, new in PROBES:
        src = BASELINE.replace(old, new, 1)
        if src == BASELINE:
            print(f'WARN {code}: patch did not apply', flush=True)
        STRATEGY.write_text(src, encoding='utf-8')
        try:
            b4, search, lower = run_triage(code)
            append_row(code, b4, search, lower, desc)
        finally:
            STRATEGY.write_text(BASELINE, encoding='utf-8')
    print('\nBatch 93 complete.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
