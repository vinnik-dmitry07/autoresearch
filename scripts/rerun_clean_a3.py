#!/usr/bin/env python
'''Clean A3 re-init from finished phase-1 runs (scrubbed template, isolated repos).

Waits until every selected phase-1 arm has state.finished=True, then destroys
leaky A3 worktrees and launches fresh sweeps from each arm's current run_dir.

Usage:
  python scripts/rerun_clean_a3.py --wait
  python scripts/rerun_clean_a3.py --wait --poll-seconds 120
  python scripts/rerun_clean_a3.py --init-only --arms A1 A2
'''
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from ladder_lib import MANIFEST_PATH, PHASE1_ARMS, load_manifest  # noqa: E402


def _phase1_status(manifest: dict, arms: list[str]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for arm in arms:
        entry = manifest.get('arms', {}).get(arm)
        if not entry:
            rows[arm] = {'round': '-', 'finished': False, 'run_dir': '-', 'missing': True}
            continue
        run_dir = Path(entry['run_dir'])
        state_path = run_dir / 'state.json'
        if not state_path.exists():
            rows[arm] = {
                'round': '-', 'finished': False, 'run_dir': run_dir.name, 'missing': True,
            }
            continue
        st = json.loads(state_path.read_text(encoding='utf-8'))
        rows[arm] = {
            'round': st.get('round', '-'),
            'finished': bool(st.get('finished')),
            'best': st.get('best_search'),
            'run_dir': run_dir.name,
            'missing': False,
        }
    return rows


def _all_finished(status: dict[str, dict]) -> bool:
    return all(
        row['finished'] and not row.get('missing')
        for row in status.values()
    )


def _print_status(status: dict[str, dict], prefix: str = '') -> None:
    pending = [a for a, r in status.items() if not r.get('finished') or r.get('missing')]
    done = [a for a, r in status.items() if r.get('finished') and not r.get('missing')]
    print(f'{prefix}phase-1 done={len(done)}/{len(status)} pending={pending or "none"}', flush=True)
    for arm in sorted(status):
        row = status[arm]
        flag = 'OK' if row.get('finished') and not row.get('missing') else '…'
        best = row.get('best')
        best_s = f'{best:.5f}' if isinstance(best, (int, float)) else '-'
        print(
            f'{prefix}  {flag} {arm:<3} round={row["round"]!s:>3} best={best_s} {row["run_dir"]}',
            flush=True,
        )


def wait_for_phase1(manifest: dict, arms: list[str], poll_seconds: int) -> None:
    print('[wait] polling until all phase-1 arms finished=True', flush=True)
    while True:
        status = _phase1_status(manifest, arms)
        _print_status(status, prefix='[wait] ')
        if _all_finished(status):
            print('[wait] all phase-1 arms finished — launching clean A3', flush=True)
            return
        print(f'[wait] sleep {poll_seconds}s', flush=True)
        time.sleep(poll_seconds)
        manifest = load_manifest()


def main() -> int:
    parser = argparse.ArgumentParser(description='Clean leak-safe A3 rerun after phase-1')
    parser.add_argument('--wait', action='store_true',
                        help='poll until phase-1 arms are finished before init/spawn')
    parser.add_argument('--poll-seconds', type=int, default=60,
                        help='poll interval when --wait (default 60)')
    parser.add_argument('--init-only', action='store_true')
    parser.add_argument('--arms', nargs='*', default=list(PHASE1_ARMS))
    parser.add_argument('--stagger-seconds', type=int, default=30)
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print(f'no manifest at {MANIFEST_PATH}; run launch_ladder_parallel.py first', flush=True)
        return 1

    manifest = load_manifest()
    if args.wait:
        wait_for_phase1(manifest, args.arms, args.poll_seconds)

    cmd = [
        sys.executable,
        str(REPO / 'scripts/launch_a3_sweep.py'),
        '--force-init',
        '--arms', *args.arms,
        '--stagger-seconds', str(args.stagger_seconds),
    ]
    if args.init_only:
        cmd.append('--init-only')

    print('=== clean A3 rerun ===', flush=True)
    print(' '.join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


if __name__ == '__main__':
    raise SystemExit(main())
