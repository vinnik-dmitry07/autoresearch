'''Quick sweep of attack trump penalty (H1 tuning, complexity 110).'''
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'durak' / 'src' / 'strategy_heuristic.cpp'
BUILD = ROOT / 'durak' / 'build.bat'
SIM = ROOT / 'durak' / 'build' / 'simulate.exe'
ORIG = SRC.read_text(encoding='utf-8')


def patch(bonus: int, param: bool) -> str:
    text = ORIG
    text = re.sub(
        r'if \(is_trump\(c, trump\)\) v \+= \d+\.0;',
        f'if (is_trump(c, trump)) v += {bonus}.0;',
        text,
        count=1,
    )
    if param:
        text = re.sub(
            r'constexpr int kParameterCount = \d+;',
            'constexpr int kParameterCount = 1;',
            text,
            count=1,
        )
        text = re.sub(
            r'// Parameters: \(none\)',
            f'// Parameters: kAtkTrumpBonus={bonus}',
            text,
            count=1,
        )
        text = re.sub(
            r'constexpr int kComplexity = 100 \* kHeuristicCount \+ 10 \* kParameterCount;',
            'constexpr int kComplexity = 100 * kHeuristicCount + 10 * kParameterCount;',
            text,
            count=1,
        )
    return text


def run_eval(bonus: int) -> float:
    out = subprocess.run(
        [str(SIM), '--mode', 'ladder', '--eval', 'quick', '--batch', '100000'],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in out.stdout.splitlines():
        if line.startswith('search_score='):
            return float(line.split('=')[1].split()[0])
        if 'B2 vs B4' in line and 'point_rate=' in line:
            pr = float(line.split('point_rate=')[1].split()[0])
    return pr


def main() -> None:
    bonuses = [70, 80, 100, 120, 150, 200]
    print('Sweep kAtkTrumpBonus (quick 100k seeds)')
    print(f"{'bonus':>6}  {'B4_pr':>8}  {'search':>8}")
    for bonus in bonuses:
        SRC.write_text(patch(bonus, bonus != 100), encoding='utf-8')
        subprocess.run(['cmd', '/c', str(BUILD)], cwd=ROOT, check=True, capture_output=True)
        out = subprocess.run(
            [str(SIM), '--mode', 'ladder', '--eval', 'quick', '--batch', '100000'],
            capture_output=True,
            text=True,
            check=True,
        )
        b4_pr = search = 0.0
        for line in out.stdout.splitlines():
            if line.startswith('search_score='):
                search = float(line.split('=')[1].split()[0])
            if line.startswith('B2 vs B4'):
                b4_pr = float(line.split('point_rate=')[1].split()[0])
        print(f'{bonus:6d}  {b4_pr:8.5f}  {search:8.5f}', flush=True)
    SRC.write_text(ORIG, encoding='utf-8')
    subprocess.run(['cmd', '/c', str(BUILD)], cwd=ROOT, check=True, capture_output=True)
    print('Restored baseline source.')


if __name__ == '__main__':
    main()
