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


def parse_b4(stdout: str) -> float:
    for line in stdout.splitlines():
        if 'point_rate=' in line:
            return float(line.split('point_rate=')[1].split()[0])
    return 0.0


def main() -> None:
    bonuses = [70, 80, 100, 120, 150, 200]
    best_b4 = 0.0
    print('Sweep kAtkTrumpBonus (gate 1: B4 quick 100k seeds, build.bat fast)')
    print(f"{'bonus':>6}  {'B4_pr':>8}  {'delta':>8}")
    for bonus in bonuses:
        SRC.write_text(patch(bonus, bonus != 100), encoding='utf-8')
        subprocess.run(
            ['cmd', '/c', str(BUILD), 'fast'],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        out = subprocess.run(
            [str(SIM), '--mode', 'match', '--opponent', 'B4', '--eval', 'quick', '--batch', '50000'],
            capture_output=True,
            text=True,
            check=True,
        )
        b4_pr = parse_b4(out.stdout)
        delta = b4_pr - best_b4 if best_b4 > 0 else 0.0
        if b4_pr > best_b4:
            best_b4 = b4_pr
        print(f'{bonus:6d}  {b4_pr:8.5f}  {delta:8.5f}', flush=True)
        if bonus >= 100 and delta <= 0.0 and best_b4 > 0:
            print('No B4 improvement since bonus=100; stopping early.', flush=True)
            break
    SRC.write_text(ORIG, encoding='utf-8')
    subprocess.run(['cmd', '/c', str(BUILD), 'fast'], cwd=ROOT, check=True, capture_output=True)
    print('Restored baseline source.')


if __name__ == '__main__':
    main()
