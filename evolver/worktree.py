'''Optional Option-B candidate isolation via throwaway git worktrees (Phase 1.5).

When enabled, the inner agent edits a disposable worktree checked out at the base
commit instead of the main working tree. The agent therefore CANNOT touch the main
sandbox at all; the harness copies only the allowlist snapshot/diff back for
evaluation. Default OFF - the in-place allowlist reset already proves the invariants.
'''
from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .util import run_command


class WorktreeError(RuntimeError):
    pass


def _git(repo_root: Path, *args: str, check: bool = True):
    result = run_command(['git', *args], cwd=repo_root)
    if check and not result.ok:
        raise WorktreeError(f'git {" ".join(args)} failed: {result.stdout}')
    return result


@contextmanager
def worktree(repo_root: Path, base: str, label: str) -> Iterator[Path]:
    '''Yield a detached worktree at `base`, removing it (and its dir) on exit.'''
    root = repo_root.resolve()
    holder = root.parent / '.evolver_worktrees'
    holder.mkdir(parents=True, exist_ok=True)
    path = holder / label
    if path.exists():
        _git(root, 'worktree', 'remove', '--force', str(path), check=False)
        shutil.rmtree(path, ignore_errors=True)
    _git(root, 'worktree', 'add', '--detach', str(path), base)
    try:
        yield path
    finally:
        _git(root, 'worktree', 'remove', '--force', str(path), check=False)
        shutil.rmtree(path, ignore_errors=True)
        _git(root, 'worktree', 'prune', check=False)
