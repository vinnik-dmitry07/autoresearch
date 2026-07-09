#!/usr/bin/env python
'''Launch A3 SweepEngine follow-up: sweep the latest phase-1 best per arm.

Each arm tokenizes its own phase-1 snapshot (kDelta or threshold literals) into
evolve/sweep/template.cpp — not the shared jun22-family template.

Usage:
  python scripts/launch_a3_sweep.py
  python scripts/launch_a3_sweep.py --init-only --arms A0 A2
'''
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder_lib import (  # noqa: E402
    MANIFEST_PATH,
    PHASE1_ARMS,
    REPO_ROOT,
    RUN_ROOT,
    WORKTREE_ROOT,
    discover_latest_phase1_run,
    init_a3_worktree,
    load_manifest,
    refresh_a3_config,
    save_manifest,
    spawn_arm,
)


def _stamp() -> str:
    return time.strftime('%Y%m%d_%H%M%S')


def main() -> int:
    parser = argparse.ArgumentParser(description='A3 sweep follow-up per ladder arm')
    parser.add_argument('--init-only', action='store_true')
    parser.add_argument('--force-init', action='store_true')
    parser.add_argument('--respawn', action='store_true',
                        help='refresh A3 config in existing worktrees and spawn (skip init)')
    parser.add_argument('--stagger-seconds', type=int, default=30,
                        help='delay between spawning each arm sweep')
    parser.add_argument('--arms', nargs='*', default=list(PHASE1_ARMS))
    args = parser.parse_args()

    manifest = load_manifest()
    phase1 = manifest.get('arms', {})
    if not phase1:
        print('no phase-1 manifest; run launch_ladder_parallel.py first', flush=True)
        return 1

    batch_id = _stamp()
    a3_manifest: dict = {'batch_id': batch_id, 'phase': 'A3', 'arms': {}}

    if args.respawn:
        for arm in args.arms:
            wt = WORKTREE_ROOT / f'{arm}_A3'
            if not wt.exists():
                print(f'skip {arm}: no A3 worktree (run without --respawn first)', flush=True)
                continue
            refresh_a3_config(wt)
            p1_run = discover_latest_phase1_run(arm)
            if p1_run is None:
                print(f'skip {arm}: no phase-1 run dir', flush=True)
                continue
            run_dir = RUN_ROOT / f'{arm}_A3_{batch_id}'
            a3_manifest['arms'][arm] = {
                'worktree': str(wt),
                'run_dir': str(run_dir),
                'phase1_run_dir': str(p1_run),
                'pid': None,
            }
            print(f'OK {arm}_A3 config refreshed', flush=True)
    else:
        for arm in args.arms:
            if arm not in phase1:
                print(f'skip {arm}: not in phase-1 manifest', flush=True)
                continue
            p1_run = discover_latest_phase1_run(arm)
            if p1_run is None:
                print(f'skip {arm}: no phase-1 run dir', flush=True)
                continue
            print(f'\n--- A3 init {arm} from {p1_run.name} ---', flush=True)
            wt = init_a3_worktree(arm, p1_run, REPO_ROOT, force=args.force_init)
            if wt is None:
                continue
            run_dir = RUN_ROOT / f'{arm}_A3_{batch_id}'
            a3_manifest['arms'][arm] = {
                'worktree': str(wt),
                'run_dir': str(run_dir),
                'phase1_run_dir': str(p1_run),
                'pid': None,
            }
            print(f'OK {arm}_A3 worktree={wt}', flush=True)

    if not a3_manifest['arms']:
        print('no A3 worktrees initialized', flush=True)
        return 1

    merged = {**manifest, 'a3': a3_manifest}
    save_manifest(merged)
    print(f'\nmanifest updated: {MANIFEST_PATH}', flush=True)

    if args.init_only:
        return 0

    arms_list = list(a3_manifest['arms'].items())
    for i, (arm, entry) in enumerate(arms_list):
        proc = spawn_arm(f'{arm}_A3', Path(entry['worktree']), Path(entry['run_dir']))
        entry['pid'] = proc.pid
        print(f'[spawn] {arm}_A3 pid={proc.pid} ({i + 1}/{len(arms_list)})', flush=True)
        save_manifest(merged)
        if i + 1 < len(arms_list) and args.stagger_seconds > 0:
            print(f'[stagger] sleep {args.stagger_seconds}s', flush=True)
            time.sleep(args.stagger_seconds)

    save_manifest(merged)
    print('A3 sweeps launched', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
