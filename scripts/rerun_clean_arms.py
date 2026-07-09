#!/usr/bin/env python
'''Re-init and spawn a clean phase-1 rerun for selected arms (leak-safe isolated repos).

Usage:
  python scripts/rerun_clean_arms.py A0 A6 A7
  python scripts/rerun_clean_arms.py A0 A6 A7 --init-only
'''
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ARMS = ('A0', 'A6', 'A7')


def main() -> int:
    parser = argparse.ArgumentParser(description='Clean leak-safe rerun for ladder arms')
    parser.add_argument('arms', nargs='*', default=list(DEFAULT_ARMS))
    parser.add_argument('--init-only', action='store_true')
    parser.add_argument('--no-slot-wait', action='store_true', default=True)
    args = parser.parse_args()

    cmd = [
        sys.executable,
        str(REPO / 'scripts/launch_ladder_parallel.py'),
        '--force-init',
        '--arms', *args.arms,
    ]
    if args.init_only:
        cmd.append('--init-only')
    if args.no_slot_wait:
        cmd.append('--no-slot-wait')

    print('=== clean rerun ===', flush=True)
    print(' '.join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


if __name__ == '__main__':
    raise SystemExit(main())
