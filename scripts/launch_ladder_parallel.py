#!/usr/bin/env python
'''Launch parallel Phase-2 ladder arms (A0–A2, A4–A8) in isolated worktrees.

Usage (from repo root):
  python scripts/launch_ladder_parallel.py
  python scripts/launch_ladder_parallel.py --init-only
  python scripts/launch_ladder_parallel.py --max-concurrent 3 --stagger-seconds 60
  python scripts/launch_ladder_parallel.py --arms A6 A8 --replicates 3
'''
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder_lib import (  # noqa: E402
    CONTAMINATED_BATCH,
    MANIFEST_PATH,
    MIN_ABLATION_REPLICATES,
    PHASE1_ARMS,
    QUARANTINE_ROOT,
    REPO_ROOT,
    RUN_ROOT,
    arm_rng_seed,
    arm_uses_claude_meta,
    assert_git_isolation,
    init_worktree,
    load_manifest,
    manifest_spawn_id,
    manifest_spawn_ids,
    parse_manifest_arm,
    preflight_claude_cli,
    preflight_cursor_cli,
    quarantine_contaminated_runs,
    save_manifest,
    spawn_arm,
    validate_replicate_concurrency,
    verify_worktree,
)


def _stamp() -> str:
    return time.strftime('%Y%m%d_%H%M%S')


def main() -> int:
    parser = argparse.ArgumentParser(description='Parallel ladder launcher')
    parser.add_argument('--max-concurrent', type=int, default=3)
    parser.add_argument('--stagger-seconds', type=int, default=60)
    parser.add_argument('--init-only', action='store_true', help='init worktrees, no spawn')
    parser.add_argument('--force-init', action='store_true', help='recreate existing worktrees')
    parser.add_argument('--spawn-only', action='store_true',
                        help='spawn pending arms from manifest (skip init)')
    parser.add_argument('--no-slot-wait', action='store_true',
                        help='stagger all arms; do not wait for a slot to free (all run in parallel)')
    parser.add_argument('--arms', nargs='*', default=list(PHASE1_ARMS))
    parser.add_argument(
        '--replicates', type=int, default=1,
        help=f'independent harness RNG replicates per arm (ablation: use >={MIN_ABLATION_REPLICATES})',
    )
    parser.add_argument(
        '--max-rounds', type=int, default=None,
        help='override max_rounds for evolver run (A8.json already 60 for long runs)',
    )
    args = parser.parse_args()

    if args.replicates < 1:
        print('--replicates must be >= 1', flush=True)
        return 1

    rep_err = validate_replicate_concurrency(args.replicates, args.max_concurrent)
    if rep_err:
        print(rep_err, flush=True)
        return 1

    if not args.arms:
        print('no arms selected', flush=True)
        return 1

    moved = quarantine_contaminated_runs(('A1', 'A2', 'A4', 'A5'))
    if moved:
        print(f'[quarantine] moved {len(moved)} contaminated run(s) to {QUARANTINE_ROOT}', flush=True)

    batch_id = _stamp()
    manifest = load_manifest()
    if not manifest.get('arms'):
        manifest = {'batch_id': batch_id, 'arms': {}}
    else:
        manifest.setdefault('batch_id', batch_id)
        manifest.setdefault('arms', {})
    manifest['quarantine'] = {
        'contaminated_batch': CONTAMINATED_BATCH,
        'root': str(QUARANTINE_ROOT),
        'last_moved': [p.name for p in moved],
    }
    batch_id = str(manifest['batch_id'])

    if args.spawn_only:
        to_spawn = manifest_spawn_ids(manifest.get('arms', {}), args.arms)
        if not to_spawn:
            print('no matching arms in manifest', flush=True)
            return 1
        print(f'=== spawn-only batch {batch_id} spawn_ids={to_spawn} ===', flush=True)
        return _spawn_arms(manifest, to_spawn, args.max_concurrent, args.stagger_seconds,
                           no_slot_wait=args.no_slot_wait)

    if args.force_init:
        manifest['batch_id'] = _stamp()
        for arm in args.arms:
            to_drop = [k for k in manifest['arms'] if parse_manifest_arm(k) == arm]
            for key in to_drop:
                manifest['arms'].pop(key, None)

    print(
        f'=== ladder batch {manifest["batch_id"]} arms={args.arms} '
        f'replicates={args.replicates} ===',
        flush=True,
    )

    for arm in args.arms:
        print(f'\n--- init {arm} ---', flush=True)
        wt = init_worktree(arm, REPO_ROOT, force=args.force_init)
        iso = assert_git_isolation(wt)
        for rep in range(args.replicates):
            spawn_id = manifest_spawn_id(arm, rep, replicates=args.replicates)
            run_suffix = '' if args.replicates <= 1 else f'_r{rep}'
            run_dir = RUN_ROOT / f'{arm}_{manifest["batch_id"]}{run_suffix}'
            fails = verify_worktree(arm, wt, run_dir)
            if fails:
                for msg in fails:
                    print(f'VERIFY FAIL: {msg}', flush=True)
                return 1
            manifest['arms'][spawn_id] = {
                'arm': arm,
                'replicate': rep,
                'worktree': str(wt),
                'run_dir': str(run_dir),
                'rng_seed': arm_rng_seed(arm, rep),
                'pid': None,
                'reachability': iso.get('reachability'),
                'batch_id': manifest['batch_id'],
            }
            if args.max_rounds is not None:
                manifest['arms'][spawn_id]['max_rounds'] = args.max_rounds
        print(f'OK {arm} worktree={wt} replicates={args.replicates}', flush=True)

    save_manifest(manifest)
    print(f'\nmanifest: {MANIFEST_PATH}', flush=True)

    if args.init_only:
        print('init-only: done', flush=True)
        return 0

    preflight_issues: list[str] = []
    for arm in args.arms:
        wt = Path(manifest['arms'][manifest_spawn_id(arm, 0, replicates=args.replicates)]['worktree'])
        preflight_issues.extend(preflight_cursor_cli(repo_root=wt))

    claude_arms = [a for a in args.arms if arm_uses_claude_meta(a)]
    if claude_arms:
        for arm in claude_arms:
            wt = Path(manifest['arms'][manifest_spawn_id(arm, 0, replicates=args.replicates)]['worktree'])
            preflight_issues.extend(preflight_claude_cli(arm=arm, repo_root=wt))

    if preflight_issues:
        for msg in preflight_issues:
            print(f'PREFLIGHT FAIL: {msg}', flush=True)
        return 1

    spawn_ids = manifest_spawn_ids(manifest.get('arms', {}), list(args.arms))
    return _spawn_arms(manifest, spawn_ids, args.max_concurrent, args.stagger_seconds,
                       no_slot_wait=args.no_slot_wait)


def _spawn_arms(
    manifest: dict,
    spawn_ids: list[str],
    max_concurrent: int,
    stagger_seconds: int,
    *,
    no_slot_wait: bool = False,
) -> int:
    '''Launch evolver processes with optional concurrency cap.

    Default: at most ``max_concurrent`` runs at once; remaining arms wait until
    a slot frees (process exit).  With ``no_slot_wait``, every arm is spawned
    sequentially with stagger only — all run in parallel.
    '''
    pending = [
        sid for sid in spawn_ids
        if manifest.get('arms', {}).get(sid, {}).get('pid') is None
    ]
    if not pending:
        print('nothing to spawn (all spawn_ids already have pid in manifest)', flush=True)
        return 0

    active: list[tuple[str, object]] = []
    launched = sum(1 for sid in spawn_ids if manifest['arms'].get(sid, {}).get('pid') is not None)
    total = len(spawn_ids)

    while pending or active:
        cap = len(spawn_ids) if no_slot_wait else max_concurrent
        while pending and len(active) < cap:
            spawn_id = pending.pop(0)
            entry = manifest['arms'][spawn_id]
            arm = entry.get('arm') or parse_manifest_arm(spawn_id)
            rng_raw = entry.get('rng_seed')
            max_rounds_raw = entry.get('max_rounds')
            proc = spawn_arm(
                arm,
                Path(entry['worktree']),
                Path(entry['run_dir']),
                rng_seed=int(rng_raw) if rng_raw is not None else None,
                max_rounds=int(max_rounds_raw) if max_rounds_raw is not None else None,
            )
            entry['pid'] = proc.pid
            active.append((spawn_id, proc))
            launched += 1
            save_manifest(manifest)
            print(f'[launched] {spawn_id} pid={proc.pid} ({launched}/{total})', flush=True)
            if pending and stagger_seconds > 0:
                print(f'[stagger] sleep {stagger_seconds}s', flush=True)
                time.sleep(stagger_seconds)

        still: list[tuple[str, object]] = []
        for spawn_id, proc in active:
            rc = proc.poll()
            if rc is None:
                still.append((spawn_id, proc))
            else:
                print(f'WARN: {spawn_id} exited early pid={proc.pid} code={rc}', flush=True)
        active = still

        if pending and len(active) >= cap and not no_slot_wait:
            running = ','.join(s for s, _ in active)
            waiting = ','.join(pending)
            print(
                f'[wait] {len(active)}/{max_concurrent} slots full ({running}); '
                f'pending=[{waiting}] — next arm starts when one finishes '
                f'(or re-run with --spawn-only --no-slot-wait)',
                flush=True,
            )
            time.sleep(30)
        elif active:
            time.sleep(2)

    print(f'\nall {launched} arm(s) launched; logs in run_dir/launcher.stdout.log', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
