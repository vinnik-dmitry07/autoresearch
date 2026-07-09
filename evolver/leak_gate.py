'''Runtime leak gate (imports scripts/leak_scan without duplicating markers).'''
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def _ensure_scripts_path() -> None:
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    path = str(scripts)
    if path not in sys.path:
        sys.path.insert(0, path)


def gate_scan(stdout: str, snapshot: str) -> list[str]:
    '''POST_AGENT backstop on stdout + strategy snapshot. Returns hit descriptions.'''
    _ensure_scripts_path()
    from leak_scan import scan_text  # noqa: WPS433

    hits: list[str] = []
    for hit in scan_text(stdout, surface='stdout'):
        hits.append(str(hit))
    for hit in scan_text(snapshot, surface='snapshot'):
        hits.append(str(hit))
    return hits


def snapshot_digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
