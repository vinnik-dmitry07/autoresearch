#!/usr/bin/env python
'''Poll ladder_parallel run directories and print a status table.

Usage:
  python scripts/ladder_status.py
  python scripts/ladder_status.py --base D:\\Projects\\.evolver_runs\\ladder_parallel
'''
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder_lib import MANIFEST_PATH, load_manifest  # noqa: E402


def _read_state(run_dir: Path) -> dict:
    path = run_dir / 'state.json'
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}


def _read_coverage(run_dir: Path) -> str:
    path = run_dir / 'descriptor_coverage.jsonl'
    if not path.exists():
        me = _read_state(run_dir).get('map_elites_coverage')
        return str(me) if me is not None else '-'
    try:
        last = path.read_text(encoding='utf-8').strip().splitlines()[-1]
        rec = json.loads(last)
        return f'{rec.get("occupied", "?")}/{rec.get("total_cells", "?")}'
    except (IndexError, json.JSONDecodeError):
        return '-'


def _count_official(run_dir: Path) -> int:
    path = run_dir / 'archive.json'
    if not path.exists():
        return 0
    try:
        rows = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return 0
    return sum(1 for r in rows if r.get('status') == 'official_best')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=None)
    args = parser.parse_args()

    manifest = load_manifest()
    arms = manifest.get('arms', {})
    if not arms and args.base:
        for p in sorted(args.base.glob('*')):
            if p.is_dir():
                arms[p.name.split('_')[0]] = {'run_dir': str(p)}

    if not arms:
        print('no ladder runs found (run launch_ladder_parallel.py first)', flush=True)
        return 1

    print(
        f"{'arm':<8} {'round':>6} {'best':>8} {'evo':>4} {'off':>4} {'cov':>8} {'done':>5}  run_dir",
        flush=True,
    )
    print('-' * 80, flush=True)
    for arm in sorted(arms.keys()):
        entry = arms[arm]
        run_dir = Path(entry['run_dir'])
        st = _read_state(run_dir)
        rnd = st.get('round', '-')
        best = st.get('best_search', 0.0)
        evo = st.get('evo_count', 0)
        off = _count_official(run_dir)
        cov = _read_coverage(run_dir)
        done = st.get('finished', False)
        print(
            f'{arm:<8} {str(rnd):>6} {best:8.5f} {evo:4} {off:4} {cov:>8} {str(done):>5}  {run_dir.name}',
            flush=True,
        )
    if MANIFEST_PATH.exists():
        print(f'\nmanifest: {MANIFEST_PATH}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
