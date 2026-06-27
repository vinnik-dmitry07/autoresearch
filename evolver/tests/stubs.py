'''Test doubles: an isolated git fixture repo and a fast flat-scoring evaluator.

These let Phase 0 prove the authority invariants with ZERO Cursor/API calls and
without ever touching the real repo or the slow C++ simulator.
'''
from __future__ import annotations

import subprocess
from pathlib import Path

from ..evaluate import Scores

STRATEGY_REL = 'durak/src/strategy_heuristic.cpp'
LOCKED_REL = 'durak/src/simulate.cpp'

BASE_STRATEGY = '''#include "policy_core.hpp"
namespace durak {
constexpr int kHeuristicCount = 1;
constexpr int kParameterCount = 0;
constexpr int kComplexity = 100 * kHeuristicCount + 10 * kParameterCount;
const char* strategy_name() { return "B2_base"; }
}  // namespace durak
'''


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ['git', *args], cwd=str(repo), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {proc.stdout}{proc.stderr}')
    return proc.stdout


def make_fixture(tmp: Path) -> tuple[Path, Path, str]:
    '''Create an isolated git repo + an out-of-repo run_dir. Returns (repo, run_dir, base).'''
    repo = tmp / 'repo'
    run_dir = tmp / 'runs' / 'test'
    (repo / 'durak' / 'src').mkdir(parents=True)
    (repo / 'durak' / 'tests').mkdir(parents=True)
    (repo / 'scripts').mkdir(parents=True)
    (repo / STRATEGY_REL).write_text(BASE_STRATEGY, encoding='utf-8')
    (repo / LOCKED_REL).write_text('// locked evaluator simulate.cpp\nint main(){return 0;}\n', encoding='utf-8')
    (repo / 'durak' / 'tests' / 'engine_tests.cpp').write_text('// locked tests\n', encoding='utf-8')
    (repo / 'scripts' / 'triage.bat').write_text('@echo off\nrem locked gate\n', encoding='utf-8')
    (repo / 'results.tsv').write_text(
        'commit\topponent\tpoint_rate\tsearch_score\tlower_ci\tgames\tcomplexity\tstatus\tdescription\n',
        encoding='utf-8',
    )
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'test@evolver.local')
    git(repo, 'config', 'user.name', 'evolver-test')
    git(repo, 'config', 'commit.gpgsign', 'false')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'base')
    base = git(repo, 'rev-parse', 'HEAD').strip()
    return repo, run_dir, base


class StubEvaluator:
    '''Flat / configurable evaluator implementing the Evaluator protocol.'''

    def __init__(
        self,
        *,
        precheck_ok: bool = True,
        precheck_reason: str = 'forbidden edit',
        search_score: float = 0.5,
        b4: float = 0.4,
        holdout_score: float | None = None,
        full_score: float | None = None,
        lower_ci: float = 1.0,
    ) -> None:
        self.precheck_ok = precheck_ok
        self.precheck_reason = precheck_reason
        self.search_score = search_score
        self.b4 = b4
        self.holdout_score = holdout_score
        self.full_score = full_score
        self.lower_ci = lower_ci
        self.search_calls = 0

    def precheck(self) -> tuple[bool, str]:
        return (self.precheck_ok, 'precheck ok' if self.precheck_ok else self.precheck_reason)

    def run_search(self) -> Scores | None:
        self.search_calls += 1
        return Scores('search', 'search_seed_0', self.search_score, self.b4, 0.0, 0.0)

    def run_holdout(self) -> Scores | None:
        score = self.holdout_score if self.holdout_score is not None else self.search_score
        return Scores('holdout', 'holdout_seed_1', score, self.b4, self.lower_ci, 0.0)

    def run_full(self) -> Scores | None:
        score = self.full_score if self.full_score is not None else self.search_score
        return Scores('full', 'full_seed_0', score, self.b4, self.lower_ci, 0.0)
