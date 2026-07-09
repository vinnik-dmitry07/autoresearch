'''Fetch Cursor Auto/API usage % from the dashboard usage-summary endpoint.'''
from __future__ import annotations

import base64
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CursorUsage:
    auto_percent: float | None
    api_percent: float | None
    total_percent: float | None
    membership_type: str | None
    billing_cycle_end: str | None
    raw: dict


def _cursor_state_db() -> Path:
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise RuntimeError('APPDATA not set (Windows Cursor state path unknown)')
    return Path(appdata) / 'Cursor' / 'User' / 'globalStorage' / 'state.vscdb'


def _load_access_token() -> str:
    '''Backward-compatible wrapper around evolver.util.load_cursor_ide_access_token.'''
    import sys
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from evolver.util import load_cursor_ide_access_token
    return load_cursor_ide_access_token(email=None)


def _user_id_from_jwt(token: str) -> str:
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        sub = json.loads(base64.urlsafe_b64decode(payload)).get('sub', '')
    except (IndexError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f'invalid Cursor JWT: {exc}') from exc
    if not sub:
        raise RuntimeError('JWT missing sub claim')
    return sub.split('|')[-1] if '|' in sub else str(sub)


def _session_cookie(token: str) -> str:
    user = _user_id_from_jwt(token)
    return f'WorkosCursorSessionToken={urllib.parse.quote(user, safe="")}%3A%3A{token}'


def _plan_usage(data: dict) -> dict:
    ind = data.get('individualUsage') or {}
    plan = ind.get('plan') or {}
    if plan:
        return plan
    # newer/alternate payload shapes
    for key in ('planUsage', 'usage', 'individualPlanUsage'):
        block = data.get(key)
        if isinstance(block, dict) and block:
            return block
    return {}


def fetch_cursor_usage(*, timeout_s: float = 20.0) -> CursorUsage:
    token = _load_access_token()
    req = urllib.request.Request(
        'https://cursor.com/api/usage-summary',
        headers={
            'Cookie': _session_cookie(token),
            'User-Agent': 'autoresearch-monitor/1.0',
            'Accept': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(
                'Cursor usage API unauthorized — re-login in Cursor IDE '
                'or refresh CURSOR_SESSION_TOKEN'
            ) from exc
        raise RuntimeError(f'Cursor usage API HTTP {exc.code}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Cursor usage API unreachable: {exc.reason}') from exc

    plan = _plan_usage(data)
    def _pct(key: str) -> float | None:
        val = plan.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return CursorUsage(
        auto_percent=_pct('autoPercentUsed'),
        api_percent=_pct('apiPercentUsed'),
        total_percent=_pct('totalPercentUsed'),
        membership_type=data.get('membershipType'),
        billing_cycle_end=data.get('billingCycleEnd'),
        raw=data,
    )
