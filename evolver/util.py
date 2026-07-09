'''Shared low-level helpers: atomic artifact writes, JSONL append, subprocess.

Every official artifact is written with the tmp -> fsync -> os.replace pattern so a
crash mid-write can never corrupt a restart (plan mechanical contract 6).
'''
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CURSOR_IDE_EMAIL = 'dimitry@bobyard.com'


def utc_stamp() -> str:
    '''Compact UTC timestamp usable in run ids and filenames.'''
    return time.strftime('%Y%m%d_%H%M%S', time.gmtime())


def atomic_write_text(path: Path, text: str) -> None:
    '''Write text atomically: write to <path>.tmp, fsync, then os.replace.'''
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    '''Serialize payload to JSON and write it atomically.'''
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + '\n')


def read_json(path: Path, default: Any = None) -> Any:
    '''Read JSON, returning default when the file is missing or unreadable.'''
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    '''Append one JSON record as a line (append-only history).'''
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True)
    with path.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(line + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    '''Read every record from a JSONL file (empty list when missing).'''
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _cursor_state_db() -> Path:
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise RuntimeError('APPDATA not set (Windows Cursor state path unknown)')
    return Path(appdata) / 'Cursor' / 'User' / 'globalStorage' / 'state.vscdb'


def load_cursor_ide_access_token(*, email: str | None = CURSOR_IDE_EMAIL) -> str:
    '''JWT access token from ``CURSOR_SESSION_TOKEN`` or Cursor IDE state DB.

    When *email* is set, ``cursorAuth/cachedEmail`` must match (bobyard guard).
    '''
    override = os.environ.get('CURSOR_SESSION_TOKEN', '').strip()
    if override:
        if '%3A%3A' in override or '::' in override:
            return override.split('%3A%3A', 1)[-1].split('::', 1)[-1]
        return override

    db = _cursor_state_db()
    if not db.exists():
        raise RuntimeError(
            f'Cursor state DB not found: {db}. '
            'Sign in to Cursor IDE or set CURSOR_SESSION_TOKEN.'
        )
    con = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True)
    try:
        if email:
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key='cursorAuth/cachedEmail'",
            ).fetchone()
            cached = row[0] if row else ''
            if isinstance(cached, bytes):
                cached = cached.decode('utf-8', errors='replace')
            if cached.startswith('"'):
                cached = json.loads(cached)
            if str(cached).strip().lower() != email.strip().lower():
                raise RuntimeError(
                    f'Cursor IDE logged in as {cached!r}, expected {email!r}'
                )
        row = con.execute(
            "SELECT value FROM ItemTable WHERE key='cursorAuth/accessToken'",
        ).fetchone()
    finally:
        con.close()
    if not row or not row[0]:
        raise RuntimeError('cursorAuth/accessToken missing — sign in to Cursor IDE')
    token = row[0]
    if isinstance(token, bytes):
        token = token.decode('utf-8', errors='replace')
    if isinstance(token, str) and token.startswith('"'):
        token = json.loads(token)
    return str(token)


def cursor_cli_env(base: dict[str, str] | None = None) -> dict[str, str]:
    '''Subprocess env for ``cursor-agent`` (model ``auto``) via IDE session JWT.

    Strips host ``CURSOR_API_KEY`` (env API key beats login) and any stale
    ``CURSOR_AUTH_TOKEN``, then injects the bobyard Desktop JWT so inner arms
    bill against dimitry@bobyard.com Auto quota, not the Agent host key.
    '''
    env = dict(base if base is not None else os.environ)
    env.pop('CURSOR_API_KEY', None)
    env.pop('CURSOR_AUTH_TOKEN', None)
    env['CURSOR_AUTH_TOKEN'] = load_cursor_ide_access_token()
    return env


def claude_meta_env(base: dict[str, str] | None = None) -> dict[str, str]:
    '''Subprocess env for A8 meta sessions: disable auto-memory layer.'''
    env = dict(base if base is not None else os.environ)
    env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] = '1'
    return env


def agent_subprocess_popen_kwargs() -> dict[str, Any]:
    '''Extra Popen kwargs so agent timeouts can kill the full child tree.'''
    if os.name == 'nt':
        return {}
    return {'start_new_session': True}


def kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    '''Terminate a Popen process and any children (cmd /c wrappers on Windows).'''
    if proc.poll() is not None:
        return
    pid = proc.pid
    if os.name == 'nt':
        subprocess.run(
            ['taskkill', '/T', '/F', '/PID', str(pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        sig = getattr(signal, 'SIGKILL', signal.SIGTERM)
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def wait_or_kill_process_tree(proc: subprocess.Popen[Any], *, timeout: float = 10) -> None:
    '''Wait for agent exit; on hang, tear down the full process tree.'''
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


class CommandResult:
    '''Outcome of a subprocess invocation.'''

    def __init__(self, returncode: int, stdout: str, timed_out: bool, seconds: float) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.timed_out = timed_out
        self.seconds = seconds

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def run_command(
    args: list[str],
    cwd: Path,
    timeout_s: float | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    '''Run a command, capturing combined stdout/stderr, with a wall timeout.

    Never raises on a non-zero exit or a timeout; the caller inspects the result.
    '''
    full_env = {**os.environ, **(env or {})}
    start = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            env=full_env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_s,
        )
        seconds = time.monotonic() - start
        return CommandResult(proc.returncode, (proc.stdout or '') + (proc.stderr or ''), False, seconds)
    except subprocess.TimeoutExpired as exc:
        seconds = time.monotonic() - start
        captured = ''
        if exc.stdout:
            captured += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode('utf-8', 'replace')
        if exc.stderr:
            captured += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode('utf-8', 'replace')
        return CommandResult(124, captured, True, seconds)


def log(message: str) -> None:
    '''Print a flushed, timestamped progress line to the console.'''
    print(f'[{time.strftime("%H:%M:%S")}] {message}', flush=True)


def eprint(message: str) -> None:
    '''Print to stderr, flushed.'''
    print(message, file=sys.stderr, flush=True)
