'''Harness-owned evaluation. ONLY this module computes official scores.

Pipeline (plan): forbidden_check -> build.bat fast -> ctest -> triage.bat gates.
- cheap search bank (quick gate)   -> search_alpha   (every valid candidate)
- disjoint holdout (dual gate)      -> holdout_alpha  (promotion track only)
- full gate                         -> search_full + lower_ci for the keep rule

The agent never writes these numbers; success is a process exit code, not self-report.
'''
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Config
from .util import CommandResult, log, run_command

_RE_QUICK = re.compile(r'Gate 2 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)')
_RE_FULL = re.compile(r'Gate 3 search_score=([\d.]+)\s+B4 point_rate=([\d.]+)')
_RE_DUAL_SEED1 = re.compile(r'Dual seed 1: search=([\d.]+).*?B4=([\d.]+)')
_RE_LOWER_CI_REPORT = re.compile(r'lower_ci=([\d.]+)')
_RE_LOWER_CI_B4 = re.compile(r'B2 vs B4\s+point_rate=[\d.]+\s+ci95=\[([\d.]+)')


@dataclass
class Scores:
    '''A single evaluation result on one bank.'''

    score_kind: str
    eval_bank: str
    search_score: float
    point_rate_b4: float
    lower_ci: float
    eval_seconds: float = 0.0


@dataclass
class Verdict:
    '''Keep-rule decision for the official-best pointer.'''

    accept: bool
    rollback: bool
    reason: str


def parse_quick(text: str) -> tuple[float, float] | None:
    match = _RE_QUICK.search(text)
    return (float(match.group(1)), float(match.group(2))) if match else None


def parse_full(text: str) -> tuple[float, float] | None:
    match = _RE_FULL.search(text)
    return (float(match.group(1)), float(match.group(2))) if match else None


def parse_dual_seed1(text: str) -> tuple[float, float] | None:
    match = _RE_DUAL_SEED1.search(text)
    return (float(match.group(1)), float(match.group(2))) if match else None


def parse_lower_ci(text: str) -> float:
    '''Best-effort lower CI on the B4 reporting metric (0.0 when absent).'''
    match = _RE_LOWER_CI_B4.search(text)
    if match:
        return float(match.group(1))
    match = _RE_LOWER_CI_REPORT.search(text)
    return float(match.group(1)) if match else 0.0


def read_best_from_results(repo_root: Path) -> tuple[float, float, float] | None:
    '''Return (best_search, best_b4, best_lower_ci) from the max-search row of results.tsv.

    Read-only; lets a real run start from the true current best instead of a stale config.
    '''
    path = repo_root / 'results.tsv'
    if not path.exists():
        return None
    lines = path.read_text(encoding='utf-8').splitlines()
    if len(lines) < 2:
        return None
    header = lines[0].split('\t')

    def col(name: str) -> int:
        return header.index(name) if name in header else -1

    i_search, i_point, i_lower = col('search_score'), col('point_rate'), col('lower_ci')
    if i_search < 0:
        return None
    best: tuple[float, float, float] | None = None
    for line in lines[1:]:
        cells = line.split('\t')
        if len(cells) <= i_search or not cells[i_search]:
            continue
        try:
            search = float(cells[i_search])
        except ValueError:
            continue
        point = float(cells[i_point]) if 0 <= i_point < len(cells) and cells[i_point] else 0.0
        lower = float(cells[i_lower]) if 0 <= i_lower < len(cells) and cells[i_lower] else 0.0
        if best is None or search > best[0]:
            best = (search, point, lower)
    return best


def keep_rule(
    search_full: float,
    lower_ci: float,
    best_search: float,
    best_lower_ci: float,
    search_delta: float,
) -> Verdict:
    '''The locked keep rule: search_full >= best+delta AND lower_ci >= best_lower_ci.'''
    threshold = best_search + search_delta
    if search_full >= threshold and lower_ci >= best_lower_ci:
        return Verdict(
            True, False,
            f'keep: search_full={search_full:.5f}>={threshold:.5f} and lower_ci={lower_ci:.5f}>={best_lower_ci:.5f}',
        )
    return Verdict(
        False, True,
        f'reject: search_full={search_full:.5f} vs {threshold:.5f}, lower_ci={lower_ci:.5f} vs {best_lower_ci:.5f}',
    )


class Evaluator(Protocol):
    '''Interface the loop depends on (tests inject a stub; runs use RealEvaluator).'''

    def precheck(self) -> tuple[bool, str]:
        '''forbidden + build + ctest; (ok, reason).'''
        ...

    def run_search(self) -> Scores | None:
        '''Cheap search-bank evaluation -> search_alpha.'''
        ...

    def run_holdout(self) -> Scores | None:
        '''Disjoint-seed holdout evaluation -> holdout_alpha.'''
        ...

    def run_full(self) -> Scores | None:
        '''Full evaluation -> search_full + lower_ci for the keep rule.'''
        ...


class RealEvaluator:
    '''Drives the locked C++ evaluator through build.bat / triage.bat on the repo.'''

    def __init__(self, config: Config) -> None:
        self.config = config
        self.repo_root = config.repo_root

    def _triage_env(self) -> dict[str, str]:
        return {
            'BEST_SEARCH': f'{self.config.best_search:.5f}',
            'BEST_B4': f'{self.config.best_b4:.5f}',
            'SKIP_BUILD': '1',
        }

    def _read_score_file(self, eval_tag: str, seed: int) -> float | None:
        path = self.repo_root / 'durak' / 'triage_parts' / f'search_score_{eval_tag}_{seed}.txt'
        if not path.exists():
            return None
        try:
            return float(path.read_text(encoding='utf-8').strip())
        except ValueError:
            return None

    def precheck(self) -> tuple[bool, str]:
        allow = self.config.allowlist[0]
        forbidden = run_command(
            ['cmake', f'-DSRC={allow}', '-P', 'durak/cmake/check_forbidden.cmake'],
            cwd=self.repo_root,
            timeout_s=120,
        )
        if not forbidden.ok:
            return False, f'forbidden_check failed: {forbidden.stdout.strip()[-300:]}'
        build = run_command(
            ['cmd', '/c', 'durak\\build.bat', 'fast', 'test'],
            cwd=self.repo_root,
            timeout_s=self.config.session.wall_timeout_s,
        )
        if not build.ok:
            return False, f'build/ctest failed ({build.returncode}): {build.stdout.strip()[-300:]}'
        return True, 'precheck ok'

    def _run_triage(self, stage: str, extra_env: dict[str, str] | None = None) -> CommandResult:
        env = self._triage_env()
        if extra_env:
            env.update(extra_env)
        log(f'eval: triage.bat {stage}')
        return run_command(
            ['cmd', '/c', 'scripts\\triage.bat', stage],
            cwd=self.repo_root,
            timeout_s=self.config.session.wall_timeout_s,
            env=env,
        )

    def run_search(self) -> Scores | None:
        result = self._run_triage(self.config.gate_search)
        if not result.ok:
            return None
        parsed = parse_quick(result.stdout)
        search = self._read_score_file('quick', 0)
        if parsed is None and search is None:
            return None
        search_score = search if search is not None else parsed[0]
        b4 = parsed[1] if parsed is not None else 0.0
        return Scores('search', 'search_seed_0', search_score, b4, 0.0, result.seconds)

    def run_holdout(self) -> Scores | None:
        result = self._run_triage(self.config.gate_holdout)
        if not result.ok:
            return None
        parsed = parse_dual_seed1(result.stdout)
        search = self._read_score_file('quick', 1)
        if parsed is None and search is None:
            return None
        search_score = search if search is not None else parsed[0]
        b4 = parsed[1] if parsed is not None else 0.0
        return Scores('holdout', 'holdout_seed_1', search_score, b4, parse_lower_ci(result.stdout), result.seconds)

    def run_full(self) -> Scores | None:
        result = self._run_triage(self.config.gate_full, extra_env={'FORCE_FULL': '1'})
        if not result.ok:
            return None
        parsed = parse_full(result.stdout)
        search = self._read_score_file('full', 0)
        if parsed is None and search is None:
            return None
        search_score = search if search is not None else parsed[0]
        b4 = parsed[1] if parsed is not None else 0.0
        return Scores('full', 'full_seed_0', search_score, b4, parse_lower_ci(result.stdout), result.seconds)
