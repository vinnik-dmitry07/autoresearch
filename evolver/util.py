'''Shared low-level helpers: atomic artifact writes, JSONL append, subprocess.

Every official artifact is written with the tmp -> fsync -> os.replace pattern so a
crash mid-write can never corrupt a restart (plan mechanical contract 6).
'''
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


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
