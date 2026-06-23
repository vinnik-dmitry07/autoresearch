'''Batch-114: closure — WR post-plateau memory ablation + meta documentation.'''
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results.tsv'
COMMIT = 'f5bb135'
BEST_SEARCH = '0.79506'
BEST_B4 = '0.64489'


def run_ablation() -> tuple[float, float]:
    print('=== memory ablation (5M seeds) ===', flush=True)
    proc = subprocess.run(
        ['durak\\build\\simulate.exe', '--mode', 'ablate', '--eval', 'full'],
        cwd=ROOT, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    print(out, flush=True)
    if proc.returncode != 0:
        raise RuntimeError('ablation failed')
    m = re.search(
        r'B3 vs B2\s+point_rate=([\d.]+).*ci95=\[([\d.]+)',
        out,
    )
    if not m:
        raise RuntimeError('ablation parse failed')
    return float(m.group(1)), float(m.group(2))


def run_quick_reconfirm() -> tuple[float, float, float]:
    env = {**dict(__import__('os').environ), 'BEST_SEARCH': BEST_SEARCH, 'BEST_B4': BEST_B4}
    print('=== WR quick reconfirm ===', flush=True)
    proc = subprocess.run(
        ['cmd', '/c', 'scripts\\triage.bat', 'quick'],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    print(out, flush=True)
    m = re.search(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)', out)
    if not m:
        raise RuntimeError('quick reconfirm parse failed')
    search, b4 = float(m.group(1)), float(m.group(2))
    return b4, search, b4 - 0.00176


def append_row(
    commit: str, opponent: str, b4: float, search: float, lower: float,
    desc: str, games: int, status: str = 'discard',
) -> None:
    with RESULTS.open('a', encoding='utf-8') as f:
        f.write(
            f'{commit}\t{opponent}\t{b4:.5f}\t{search:.5f}\t{lower:.5f}\t'
            f'{games}\t100\t{status}\t{desc}\n'
        )


def main() -> int:
    b3, lower = run_ablation()
    append_row(
        COMMIT, 'B3vsB2', b3, float(BEST_SEARCH), lower,
        'WR post-plateau memory ablation batch-114', 10_000_000, 'keep',
    )
    b4, search, lower_b4 = run_quick_reconfirm()
    append_row(
        'probe', 'B4', b4, search, lower_b4,
        'exp YQ WR closure quick reconfirm batch-114', 200_000, 'discard',
    )
    print(f'B3vsB2={b3:.5f} WR quick search={search:.5f} B4={b4:.5f}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
