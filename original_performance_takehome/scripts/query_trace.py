"""Summarize a Chrome/Perfetto trace.json without trace_processor.

Prints engine occupancy from slot threads (alu-0, load-1, ...).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from problem import SLOT_LIMITS

ENGINES = ('alu', 'valu', 'load', 'store', 'flow')


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def _engine_of(name: str) -> str | None:
    base = name.split('-', 1)[0]
    return base if base in SLOT_LIMITS and base != 'debug' else None


def iter_events(path: Path):
    """Yield Chrome trace events. Handles the simulator's [obj, obj,] array."""
    with path.open(encoding='utf-8') as fh:
        peek = fh.read(8)
        fh.seek(0)
        if peek.lstrip().startswith('{'):
            payload = json.load(fh)
            events = payload.get('traceEvents', payload if isinstance(payload, list) else [])
            for ev in events:
                if isinstance(ev, dict):
                    yield ev
            return
        for n, line in enumerate(fh, 1):
            raw = line.strip().lstrip('[').rstrip(',').rstrip(']')
            if not raw or raw in '[]':
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict):
                yield ev
            if n % 200000 == 0:
                print(f'  ... {n} lines', flush=True)


def summarize_trace(path: Path) -> dict:
    names: dict[int, str] = {}
    ops: dict[str, int] = defaultdict(int)
    n_events = 0
    n_ops = 0
    max_ts = 0
    for ev in iter_events(path):
        n_events += 1
        ph = ev.get('ph')
        tid = int(ev.get('tid') or 0)
        if ph == 'M' and ev.get('name') == 'thread_name':
            label = str((ev.get('args') or {}).get('name') or '')
            if label:
                names[tid] = label
            continue
        if ph != 'X':
            continue
        if int(ev.get('dur') or 0) <= 0:
            continue
        ts = int(ev.get('ts') or 0)
        if ts > max_ts:
            max_ts = ts
        label = names.get(tid) or str(ev.get('name') or '')
        eng = _engine_of(label)
        if eng is None:
            continue
        ops[eng] += 1
        n_ops += 1
    cycles = max_ts if max_ts > 0 else 0
    engines = {}
    for name in ENGINES:
        limit = int(SLOT_LIMITS[name])
        count = int(ops.get(name) or 0)
        denom = cycles * limit
        engines[name] = {
            'ops': count,
            'limit': limit,
            'occupancy': (count / denom) if denom else 0.0,
        }
    return {
        'path': str(path),
        'events': n_events,
        'ops': n_ops,
        'cycles': cycles,
        'engines': engines,
    }


def _print_summary(row: dict) -> None:
    print(
        f'  events={row["events"]}  ops={row["ops"]}  cycles={row["cycles"]}',
        flush=True,
    )
    for name in ENGINES:
        eng = row['engines'][name]
        print(
            f'  {name:<5}  ops={eng["ops"]:<8}  '
            f'occ={100.0 * eng["occupancy"]:5.1f}%  limit={eng["limit"]}',
            flush=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Chrome trace occupancy without Perfetto')
    parser.add_argument(
        'trace',
        nargs='?',
        default='trace.json',
        help='trace.json (default: ./trace.json)',
    )
    args = parser.parse_args(argv)
    path = Path(args.trace)
    if not path.is_file():
        cand = ROOT / args.trace
        path = cand if cand.is_file() else path
    if not path.is_file():
        print(f'trace not found: {args.trace}', flush=True)
        return 1
    print(f'query_trace  {path}', flush=True)
    t0 = time.perf_counter()
    row = summarize_trace(path)
    _print_summary(row)
    print(f'done  {_ms(t0):.0f} ms', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
