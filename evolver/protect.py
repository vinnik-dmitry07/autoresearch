'''VersionControl: mechanical protection via git, inverted to an allowlist.

Safety is mechanical, never trusted to the agent (HyperAgents lesson). After every
candidate the harness resets everything EXCEPT the manifest allowlist back to the
base commit, so edits to the evaluator / tests / metric / thresholds are discarded
before evaluation. Snapshots/diffs are copied to run_dir (outside the repo) BEFORE
any reset, so `reset --hard` / `clean -fd` can never destroy harness artifacts.
'''
from __future__ import annotations

import os
from pathlib import Path

from .util import CommandResult, run_command

DEVNULL = 'NUL' if os.name == 'nt' else '/dev/null'


class GitError(RuntimeError):
    '''Raised when a git command fails unexpectedly.'''


class VersionControl:
    '''Thin git wrapper enforcing the allowlist contract on `repo_root`.'''

    def __init__(
        self,
        repo_root: Path,
        allowlist: tuple[str, ...],
        harness_excludes: tuple[str, ...] = ('evolve',),
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.allowlist = tuple(a.replace('\\', '/') for a in allowlist)
        self.harness_excludes = tuple(harness_excludes)

    def _git(self, *args: str, check: bool = True) -> CommandResult:
        result = run_command(['git', *args], cwd=self.repo_root)
        if check and not result.ok:
            raise GitError(f'git {" ".join(args)} failed ({result.returncode}):\n{result.stdout}')
        return result

    def current_commit(self) -> str:
        '''Full SHA of HEAD.'''
        return self._git('rev-parse', 'HEAD').stdout.strip()

    def reset_all_but_allowlist(self, base: str) -> None:
        '''Restore every path except the allowlist to `base` (discard illegal edits).

        Tracked files are checked out from base; untracked files are removed by clean.
        The allowlist file keeps the agent's edit so it can be evaluated.
        '''
        excludes = [f':(exclude){path}' for path in self.allowlist]
        self._git('checkout', base, '--', '.', *excludes)
        clean_args = ['clean', '-fd']
        for path in (*self.allowlist, *self.harness_excludes):
            clean_args += ['-e', path]
        self._git(*clean_args)

    def reset_to_base(self, base: str) -> None:
        '''Full sandbox reset to base (the crash/finally reset). Runtime store is safe.'''
        self._git('reset', '--hard', base)
        clean_args = ['clean', '-fd']
        for path in self.harness_excludes:
            clean_args += ['-e', path]
        self._git(*clean_args)

    def diff_allowlist(self, base: str) -> str:
        '''Diff only the allowlist paths vs base (the candidate patch).'''
        return self._git('diff', base, '--', *self.allowlist).stdout

    def diff_versus_commit(self, base: str) -> str:
        '''Full tracked diff vs base plus NUL-aware diffs for untracked files.'''
        parts = [self._git('diff', base).stdout]
        others = self._git('ls-files', '--others', '--exclude-standard').stdout.split('\n')
        for rel in others:
            rel = rel.strip()
            if not rel:
                continue
            # --no-index returns exit code 1 when files differ; that is expected.
            parts.append(self._git('diff', '--no-index', DEVNULL, rel, check=False).stdout)
        return ''.join(parts)

    def commit_inline(self, message: str) -> str:
        '''Stage the allowlist and commit with an inline identity (no global config).

        Returns the new commit SHA, or the current HEAD when there is nothing to commit.
        '''
        self._git('add', '--', *self.allowlist)
        result = self._git(
            '-c', 'user.email=evolver@local',
            '-c', 'user.name=evolver',
            'commit', '-m', message,
            check=False,
        )
        if not result.ok and 'nothing to commit' not in result.stdout:
            raise GitError(f'commit failed:\n{result.stdout}')
        return self.current_commit()

    def tag_evo(self, n: int) -> str:
        '''Create an evo-N tag at HEAD (idempotent via -f).'''
        tag = f'evo-{n}'
        self._git('tag', '-f', tag)
        return tag

    def list_evo_tags(self) -> list[str]:
        out = self._git('tag', '--list', 'evo-*').stdout.split('\n')
        return [t.strip() for t in out if t.strip()]

    def read_repo_file(self, rel: str) -> str:
        '''Read a repo-relative file from the working tree.'''
        return (self.repo_root / rel).read_text(encoding='utf-8')

    def write_repo_file(self, rel: str, content: str) -> None:
        '''Write a repo-relative file (used to restore a parent snapshot).'''
        target = self.repo_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')

    def file_at_commit(self, ref: str, rel: str) -> str:
        '''Read a file's content at a given commit (empty when absent).'''
        result = self._git('show', f'{ref}:{rel}', check=False)
        return result.stdout if result.ok else ''
