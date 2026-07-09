#!/usr/bin/env python
'''Monitor Cursor Auto usage and stop ladder arms at a threshold.

Polls cursor.com/api/usage-summary (Auto %% from local Cursor IDE session).
When autoPercentUsed >= threshold, writes stop.flag for all ladder arms.
The evolver pauses until usage resets (does not terminate). This monitor also
waits until auto drops below threshold, then clears stop.flag and keeps polling.

Usage:
  python scripts/monitor_cursor_usage.py
  python scripts/monitor_cursor_usage.py --threshold 80 --interval 300 --once
  python scripts/monitor_cursor_usage.py --dry-run

Auth: reads cursorAuth/accessToken from %%APPDATA%%\\Cursor\\...\\state.vscdb,
      or CURSOR_SESSION_TOKEN env override.
'''
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO))

from cursor_usage import fetch_cursor_usage  # noqa: E402
from evolver.usage_limit import (  # noqa: E402
    CURSOR_AUTO_STOP_MARKER,
    wait_for_cursor_auto_reset,
)
from ladder_lib import EXPERIMENTAL_ARMS, PHASE1_ARMS, RUN_ROOT, load_manifest  # noqa: E402

MONITORED_ARMS = PHASE1_ARMS + EXPERIMENTAL_ARMS


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def _manifest_run_dirs() -> list[tuple[str, Path]]:
    manifest = load_manifest()
    out: list[tuple[str, Path]] = []
    for arm in MONITORED_ARMS:
        entry = manifest.get('arms', {}).get(arm)
        if not entry:
            continue
        run_dir = Path(entry['run_dir'])
        if run_dir.exists():
            out.append((arm, run_dir))
    return out


def _stop_flag_body(*, auto: float, threshold: float) -> str:
    return (
        f'{CURSOR_AUTO_STOP_MARKER}\n'
        f'autoPercentUsed={auto}\n'
        f'threshold={threshold}\n'
    )


def _stop_all(*, auto: float, threshold: float, dry_run: bool) -> int:
    if dry_run:
        _log('dry-run: would stop all ladder arms')
        return 0
    n = 0
    for arm, run_dir in _manifest_run_dirs():
        (run_dir / 'stop.flag').write_text(
            _stop_flag_body(auto=auto, threshold=threshold), encoding='utf-8',
        )
        _log(f'stop.flag -> {arm} ({run_dir.name})')
        n += 1
    return 0 if n else 1


def _resume_all(*, dry_run: bool) -> None:
    if dry_run:
        _log('dry-run: would clear usage stop flags')
        return
    for arm, run_dir in _manifest_run_dirs():
        stop = run_dir / 'stop.flag'
        if not stop.exists():
            continue
        text = stop.read_text(encoding='utf-8')
        if CURSOR_AUTO_STOP_MARKER not in text:
            continue
        stop.unlink(missing_ok=True)
        _log(f'stop.flag cleared -> {arm} ({run_dir.name})')
    marker = RUN_ROOT / 'USAGE_STOP_80.txt'
    if marker.exists():
        marker.unlink(missing_ok=True)


def _check(threshold: float, *, dry_run: bool) -> bool:
    '''Return True if threshold triggered (arms stopped).'''
    usage = fetch_cursor_usage()
    auto = usage.auto_percent
    api = usage.api_percent
    total = usage.total_percent
    parts = []
    if auto is not None:
        parts.append(f'auto={auto:.1f}%')
    if api is not None:
        parts.append(f'api={api:.1f}%')
    if total is not None:
        parts.append(f'total={total:.1f}%')
    extra = f" ({usage.membership_type})" if usage.membership_type else ''
    _log('cursor usage: ' + ', '.join(parts) + extra)

    if auto is None:
        _log('WARN: autoPercentUsed missing from API payload — not stopping')
        return False

    if auto >= threshold:
        _log(f'THRESHOLD auto {auto:.1f}% >= {threshold:.0f}% — stopping ladder arms')
        _stop_all(auto=auto, threshold=threshold, dry_run=dry_run)
        marker = RUN_ROOT / 'USAGE_STOP_80.txt'
        if not dry_run:
            marker.write_text(
                f'autoPercentUsed={auto}\nthreshold={threshold}\n'
                f'at={datetime.now(timezone.utc).isoformat()}\n',
                encoding='utf-8',
            )
        return True
    return False


def _wait_for_reset(threshold: float, interval: int, *, dry_run: bool) -> None:
    _log(f'waiting for autoPercentUsed < {threshold:.0f}% before resuming arms')
    if dry_run:
        _log('dry-run: would wait for usage reset')
        return
    wait_for_cursor_auto_reset(
        threshold,
        poll_interval_s=float(interval),
        fetch_fn=fetch_cursor_usage,
    )
    _resume_all(dry_run=dry_run)
    _log('usage reset — arms may resume')


def main() -> int:
    parser = argparse.ArgumentParser(description='Stop ladder when Cursor Auto usage hits threshold')
    parser.add_argument('--threshold', type=float, default=80.0,
                        help='autoPercentUsed stop threshold (default 80)')
    parser.add_argument('--interval', type=int, default=300,
                        help='poll interval seconds (default 300)')
    parser.add_argument('--once', action='store_true', help='single check then exit')
    parser.add_argument('--dry-run', action='store_true', help='log only, no stop.flag')
    args = parser.parse_args()

    manifest = load_manifest()
    arms = [a for a in MONITORED_ARMS if a in manifest.get('arms', {})]
    _log(f'monitor start threshold={args.threshold}% interval={args.interval}s arms={arms}')

    paused = False
    while True:
        try:
            if paused:
                _wait_for_reset(args.threshold, args.interval, dry_run=args.dry_run)
                paused = False
                if args.once:
                    return 0
            else:
                triggered = _check(args.threshold, dry_run=args.dry_run)
                if triggered:
                    paused = True
                    if args.once:
                        _wait_for_reset(args.threshold, args.interval, dry_run=args.dry_run)
                        return 0
                    continue
        except Exception as exc:
            _log(f'ERROR: {exc}')
        if args.once:
            return 0
        _log(f'sleep {args.interval}s')
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
