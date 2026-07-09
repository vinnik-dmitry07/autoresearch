#!/usr/bin/env python3
'''Smoke gate: one forced meta round must produce a real meta commit.

Usage:
  python scripts/meta_commit_smoke.py --repo-root D:/Projects/.evolver_ladder/worktrees/A8

Exit 0 when:
  - META edited mechanism logged
  - git log contains meta: round N
  - evolve_skill.md at HEAD differs from base
'''
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evolver.agents import AgentContext, AgentResult, COMPLETED, append_line
from evolver.config import load_config
from evolver.meta import Attribution, MetaController
from evolver.tests.test_phase0 import git


def main() -> int:
    parser = argparse.ArgumentParser(description='Meta commit delivery smoke test')
    parser.add_argument('--repo-root', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    if not (repo / 'evolve' / 'config.json').exists():
        print(f'FAIL: no evolve/config.json under {repo}', flush=True)
        return 1

    base = git(repo, 'rev-parse', 'HEAD').strip()
    git(repo, 'reset', '--hard', base)
    git(repo, 'clean', '-fd')
    run_dir = Path(tempfile.mkdtemp(prefix='meta_smoke_'))
    config = load_config(repo, overrides={'run_dir': str(run_dir)})
    config.paths.ensure()

    marker = 'meta-smoke-delivery-gate'

    def behavior(ctx: AgentContext) -> AgentResult:
        path = ctx.repo_root / ctx.strategy_rel
        text = path.read_text(encoding='utf-8')
        if marker not in text:
            path.write_text(text + f'\n\n<!-- {marker} -->\n', encoding='utf-8')
        return AgentResult(status=COMPLETED, summary='smoke edit')

    from evolver.agents import StubAgent

    mc = MetaController(config, StubAgent(behavior), Attribution(run_dir / 'attr.jsonl'))
    commit, result = mc.run(99, 'phi smoke', base, 0.5)
    if result is None or result.status != COMPLETED:
        print(f'FAIL: meta session status={getattr(result, "status", None)}', flush=True)
        return 1
    if commit == base:
        rounds = run_dir / 'meta_rounds.jsonl'
        detail = ''
        if rounds.exists():
            detail = rounds.read_text(encoding='utf-8')[-500:]
        print(f'FAIL: no meta commit (still at {base[:10]})\n{detail}', flush=True)
        return 1

    log_line = git(repo, 'log', '-1', '--oneline').strip()
    if 'meta: round 99' not in log_line:
        print(f'FAIL: HEAD commit message wrong: {log_line}', flush=True)
        git(repo, 'reset', '--hard', base)
        return 1

    skill = (repo / config.meta_target).read_text(encoding='utf-8')
    if marker not in skill:
        print('FAIL: evolve_skill.md at HEAD missing smoke marker', flush=True)
        git(repo, 'reset', '--hard', base)
        return 1

    print(f'OK meta commit {commit[:10]} | {log_line}', flush=True)
    rounds_path = run_dir / 'meta_rounds.jsonl'
    if rounds_path.exists():
        rec = json.loads(rounds_path.read_text(encoding='utf-8').strip().splitlines()[-1])
        print(f'  meta_rounds outcome={rec.get("outcome")} root_ok={rec.get("root_identity_ok")}',
              flush=True)
    git(repo, 'reset', '--hard', base)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
