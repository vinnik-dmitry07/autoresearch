#!/usr/bin/env python
'''Pre-launch verification checklist (plan verify-launch section).

Usage:
  python scripts/verify_ladder_launch.py --init-only --arms A0
  python scripts/verify_ladder_launch.py
'''
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder_lib import (  # noqa: E402
    MANIFEST_VERIFY_PATH,
    PHASE1_ARMS,
    REPO_ROOT,
    RUN_ROOT,
    STRATEGY_COMMIT,
    arm_uses_claude_meta,
    assert_git_isolation,
    file_hash,
    git_show,
    init_worktree,
    preflight_claude_cli,
    write_json,
    verify_worktree,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--init-only', action='store_true',
                        help='init one arm and verify (no spawn)')
    parser.add_argument('--arms', nargs='*', default=['A0'])
    parser.add_argument('--force-init', action='store_true')
    args = parser.parse_args()

    fails: list[str] = []
    manifest_arms: dict = {}

    for arm in args.arms:
        print(f'\n=== verify init {arm} ===', flush=True)
        wt = init_worktree(arm, REPO_ROOT, force=args.force_init)
        run_dir = RUN_ROOT / f'{arm}_verify'
        fails.extend(verify_worktree(arm, wt, run_dir))
        iso = assert_git_isolation(wt)
        manifest_arms[arm] = {
            'worktree': str(wt),
            'run_dir': str(run_dir),
            'reachability': iso.get('reachability'),
        }

    ref_hash = file_hash(git_show(REPO_ROOT, STRATEGY_COMMIT, 'durak/src/strategy_heuristic.cpp'))
    print(f'strategy ref hash (2c11101): {ref_hash}', flush=True)

    claude_arms = [a for a in args.arms if arm_uses_claude_meta(a)]
    for arm in claude_arms:
        print(f'\n=== claude preflight {arm} ===', flush=True)
        wt = Path(manifest_arms[arm]['worktree'])
        fails.extend(preflight_claude_cli(arm=arm, repo_root=wt))

    if args.init_only:
        write_json(MANIFEST_VERIFY_PATH, {'verify': True, 'arms': manifest_arms})
        print(f'verify manifest: {MANIFEST_VERIFY_PATH}', flush=True)
        print('(production manifest.json is written by launch_ladder_parallel.py only)', flush=True)

    print('\n=== overlay dry-run ===', flush=True)
    import subprocess
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / 'scripts/overlay_ladder_progress.py'), '--dry-run'],
        cwd=str(REPO_ROOT),
    ).returncode
    if rc != 0:
        fails.append('overlay dry-run failed')

    if fails:
        print('\nFAILURES:', flush=True)
        for f in fails:
            print(f'  - {f}', flush=True)
        return 1

    print('\nall checks passed', flush=True)
    if set(args.arms) == set(PHASE1_ARMS):
        print('ready: python scripts/launch_ladder_parallel.py', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
