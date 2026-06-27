'''Archive hygiene + restart durability (Phase 1.5).

Pre-run and periodic backups of the small state files give crash-resume a fallback if
the live files are ever corrupted. Backups are append-only snapshots in run_dir/backups;
none of this is on the hot path and none of it deletes archive history.
'''
from __future__ import annotations

import shutil
from pathlib import Path

from .config import Paths
from .util import log, utc_stamp

_BACKUP_FILES = ('state.json', 'archive.json', 'usage.json', 'history.jsonl')


class Hygiene:
    '''Backup/restore the durable state files under run_dir/backups.'''

    def __init__(self, paths: Paths, keep: int = 10) -> None:
        self.paths = paths
        self.keep = keep

    def backup(self, label: str) -> Path | None:
        '''Snapshot the durable files into run_dir/backups/<utc>_<label>/.'''
        present = [self.paths.run_dir / name for name in _BACKUP_FILES]
        present = [p for p in present if p.exists()]
        if not present:
            return None
        dest = self.paths.backups_dir / f'{utc_stamp()}_{label}'
        dest.mkdir(parents=True, exist_ok=True)
        for src in present:
            shutil.copy2(src, dest / src.name)
        self._prune()
        return dest

    def _prune(self) -> None:
        backups = sorted(
            (p for p in self.paths.backups_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        for old in backups[:-self.keep]:
            shutil.rmtree(old, ignore_errors=True)

    def latest_backup(self) -> Path | None:
        if not self.paths.backups_dir.exists():
            return None
        backups = sorted(
            (p for p in self.paths.backups_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        return backups[-1] if backups else None

    def restore_latest(self) -> bool:
        '''Restore durable files from the most recent backup (corruption recovery).'''
        latest = self.latest_backup()
        if latest is None:
            return False
        for name in _BACKUP_FILES:
            src = latest / name
            if src.exists():
                shutil.copy2(src, self.paths.run_dir / name)
        log(f'restored durable state from backup {latest.name}')
        return True
