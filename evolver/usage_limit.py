'''Pause/resume helpers when Cursor Auto or agent session usage limits are hit.'''
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from .util import log

CURSOR_AUTO_STOP_MARKER = 'stop: cursor auto usage threshold'
SESSION_LIMIT_MARKERS = (
    'session limit',
    'hit your session limit',
    'resets 12:10am',
    'rate limit',
    'usage limit',
    'usage cap',
    'included total usage',
    'included api usage',
)
_RESET_TIME_RE = re.compile(
    r'resets\s+'
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'
    r'(?:\s*\(([^)]+)\))?',
    re.IGNORECASE,
)
_THRESHOLD_RE = re.compile(r'^threshold=(\d+(?:\.\d+)?)\s*$', re.MULTILINE)
_POST_RESET_BUFFER_S = 30.0
_DEFAULT_POLL_S = 60.0


def is_session_limit_error(error: str) -> bool:
    low = (error or '').lower()
    return any(m in low for m in SESSION_LIMIT_MARKERS)


def session_limit_message(*parts: str) -> str:
    '''Return the first part that looks like a usage/session limit message.'''
    for part in parts:
        if part and is_session_limit_error(part):
            return part
    return ''


def is_cursor_auto_stop_flag(text: str) -> bool:
    return CURSOR_AUTO_STOP_MARKER in (text or '')


def parse_threshold_from_stop_flag(text: str, *, default: float = 80.0) -> float:
    match = _THRESHOLD_RE.search(text or '')
    if not match:
        return default
    try:
        return float(match.group(1))
    except ValueError:
        return default


def parse_billing_cycle_end_unix(iso: str | None) -> float | None:
    if not iso:
        return None
    text = iso.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_reset_unix_from_error(error: str, *, now: datetime | None = None) -> float | None:
    '''Parse reset times like "resets 8pm (America/Los_Angeles)" or "resets 12:10am".'''
    match = _RESET_TIME_RE.search(error or '')
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = (match.group(3) or '').lower()
    tz_name = (match.group(4) or '').strip()

    if ampm == 'pm' and hour != 12:
        hour += 12
    elif ampm == 'am' and hour == 12:
        hour = 0

    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except (KeyError, ValueError):
            tz = datetime.now().astimezone().tzinfo
    else:
        tz = datetime.now().astimezone().tzinfo

    now = now or datetime.now(tz)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def resolve_reset_unix(
    *,
    error: str = '',
    usage_reset_at: float | None = None,
    billing_cycle_end: str | None = None,
) -> float | None:
    now = time.time()
    if usage_reset_at is not None and usage_reset_at > now:
        return float(usage_reset_at)
    parsed = parse_reset_unix_from_error(error)
    if parsed is not None and parsed > now:
        return parsed
    cycle = parse_billing_cycle_end_unix(billing_cycle_end)
    if cycle is not None and cycle > now:
        return cycle
    if usage_reset_at is not None:
        return float(usage_reset_at)
    return parsed if parsed is not None else cycle


def _default_fetch_usage():
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from cursor_usage import fetch_cursor_usage  # noqa: WPS433

    return fetch_cursor_usage()


def wait_until_unix(
    until_unix: float,
    *,
    poll_interval_s: float = _DEFAULT_POLL_S,
    label: str = 'usage limit',
) -> None:
    '''Sleep until ``until_unix + buffer``, logging remaining time periodically.'''
    target = until_unix + _POST_RESET_BUFFER_S
    while True:
        now = time.time()
        if now >= target:
            log(f'  {label}: reset window reached — resuming')
            return
        remaining = target - now
        mins = remaining / 60.0
        log(f'  {label}: waiting {mins:.1f} min until reset')
        time.sleep(min(poll_interval_s, max(1.0, remaining)))


def wait_for_cursor_auto_reset(
    threshold: float,
    *,
    poll_interval_s: float = _DEFAULT_POLL_S,
    fetch_fn: Callable[[], object] | None = None,
) -> None:
    '''Wait until Cursor Auto usage resets (percent drop or billing cycle end).'''
    fetch = fetch_fn or _default_fetch_usage
    log(f'  CURSOR AUTO: waiting for autoPercentUsed < {threshold:.0f}% or billing reset')
    while True:
        usage = fetch()
        auto = getattr(usage, 'auto_percent', None)
        if auto is not None and auto < threshold:
            log(f'  CURSOR AUTO: reset (auto={auto:.1f}% < {threshold:.0f}%) — resuming')
            return
        cycle_end = parse_billing_cycle_end_unix(getattr(usage, 'billing_cycle_end', None))
        if cycle_end is not None and cycle_end > time.time():
            if auto is not None and auto >= threshold:
                log(
                    f'  CURSOR AUTO: still at {auto:.1f}% — '
                    f'waiting for billing cycle reset',
                )
                wait_until_unix(cycle_end, poll_interval_s=poll_interval_s, label='CURSOR AUTO')
                continue
        parts = [f'auto={auto:.1f}%' if auto is not None else 'auto=?']
        api = getattr(usage, 'api_percent', None)
        if api is not None:
            parts.append(f'api={api:.1f}%')
        log(f'  CURSOR AUTO: still limited ({", ".join(parts)} >= {threshold:.0f}%)')
        time.sleep(poll_interval_s)


def wait_for_usage_reset(
    *,
    error: str = '',
    usage_reset_at: float | None = None,
    poll_interval_s: float = _DEFAULT_POLL_S,
    fetch_fn: Callable[[], object] | None = None,
) -> None:
    '''Wait for an agent/session limit to reset (timestamp first, then Cursor Auto poll).'''
    fetch = fetch_fn or _default_fetch_usage
    usage = fetch()
    billing = getattr(usage, 'billing_cycle_end', None)
    reset_at = resolve_reset_unix(
        error=error,
        usage_reset_at=usage_reset_at,
        billing_cycle_end=billing,
    )
    if reset_at is not None and reset_at > time.time():
        wait_until_unix(reset_at, poll_interval_s=poll_interval_s, label='SESSION LIMIT')
        return
    log('  SESSION LIMIT: no reset timestamp — polling Cursor Auto usage')
    wait_for_cursor_auto_reset(80.0, poll_interval_s=poll_interval_s, fetch_fn=fetch)


def pause_for_cursor_auto_stop_flag(
    stop_text: str,
    *,
    poll_interval_s: float = _DEFAULT_POLL_S,
    fetch_fn: Callable[[], object] | None = None,
) -> None:
    threshold = parse_threshold_from_stop_flag(stop_text)
    wait_for_cursor_auto_reset(
        threshold, poll_interval_s=poll_interval_s, fetch_fn=fetch_fn,
    )
