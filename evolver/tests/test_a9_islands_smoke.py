'''A9 v1: islands-rich Phi/prompt smoke + meta tool trace expectations.'''
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from evolver.agents import COMPLETED, AgentContext, AgentResult, StubAgent
from evolver.config import load_config, overlay_claude_meta_session
from evolver.meta import Attribution, MetaController
from evolver.meta_delivery import scan_meta_tools_audit
from evolver.observe import Observer
from evolver.store import OFFICIAL_BEST, Candidate, Store

A9_CFG = ROOT / 'scripts' / 'ladder_configs' / 'A9.json'
A8S_SKILL = ROOT / 'evolve' / 'mechanism' / 'evolve_skill_a8s.md'
A8S_CONST = ROOT / 'evolve' / 'mechanism' / 'a8s_meta_constitution.md'

ISLANDS_STATE = {
    'round': 25,
    'plateau': 5,
    'last_official_round': 0,
    'best_search': 0.684,
    'best_b4': 0.492,
    'best_id': 'candidate_0000',
    'cost_usd': 1.0,
}


def _setup_a9_repo(tmp: Path) -> Path:
    repo = tmp / 'a9'
    mech = repo / 'evolve' / 'mechanism'
    mech.mkdir(parents=True)
    raw = json.loads(A9_CFG.read_text(encoding='utf-8'))
    (repo / 'evolve' / 'config.json').write_text(json.dumps(raw), encoding='utf-8')
    (mech / 'evolve_skill.md').write_text(A8S_SKILL.read_text(encoding='utf-8'), encoding='utf-8')
    (mech / 'a8s_meta_constitution.md').write_text(A8S_CONST.read_text(encoding='utf-8'), encoding='utf-8')
    settings = ROOT / 'evolve' / 'mechanism' / 'a8_meta_claude_settings.json'
    if settings.is_file():
        (mech / 'a8_meta_claude_settings.json').write_text(
            settings.read_text(encoding='utf-8'), encoding='utf-8',
        )
    return repo


def _islands_phi(config, repo: Path) -> str:
    store = Store(config.paths)
    store.add(Candidate(
        id='candidate_0100',
        parent_id='candidate_0000',
        base_commit='abc123',
        round=100,
        status=OFFICIAL_BEST,
        created_by='harness',
        search_alpha=0.74477,
        search_score=0.74477,
        selection_alpha=0.74477,
        point_rate_b4=0.60561,
        reason='search_alpha=0.74477',
    ))
    return Observer(config).summarize(store, ISLANDS_STATE)


class A9IslandsSmokeTestCase(unittest.TestCase):
    def test_a9_config_invariants(self) -> None:
        raw = json.loads(A9_CFG.read_text(encoding='utf-8'))
        self.assertEqual(raw['engine'], 'islands')
        self.assertEqual(raw['descriptor']['kind'], 'feature')
        self.assertTrue(raw['descriptor']['shadow'])
        self.assertFalse(raw['convergence']['enabled'])
        self.assertTrue(raw['meta']['strict_self_contained'])
        self.assertEqual(raw['meta']['ladder_template'], 'A9')

    def test_islands_rich_phi_has_deanchor_no_family_map(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = _setup_a9_repo(Path(tmp.name))
        run_dir = Path(tmp.name) / 'run'
        config = load_config(repo, overrides={'run_dir': str(run_dir)})
        config.paths.ensure()
        phi = _islands_phi(config, repo)
        self.assertIn('DE-ANCHOR', phi)
        self.assertNotIn('HEURISTIC FAMILIES', phi)
        self.assertNotIn('family_map.md', phi)
        tmp.cleanup()

    def test_islands_rich_meta_prompt_self_contained(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = _setup_a9_repo(Path(tmp.name))
        run_dir = Path(tmp.name) / 'run'
        config = load_config(repo, overrides={'run_dir': str(run_dir)})
        overlay_claude_meta_session(config, harness_root=ROOT)
        config.paths.ensure()
        phi = _islands_phi(config, repo)
        mc = MetaController(
            config,
            StubAgent(lambda ctx: AgentResult(status=COMPLETED)),
            Attribution(run_dir / 'attr.jsonl'),
        )
        prompt = mc._prompt(phi)
        self.assertIn('self-contained', prompt)
        self.assertNotIn('Known heuristic families', prompt)
        self.assertNotIn('Maintain `family_map.md`', prompt)
        tmp.cleanup()

    def test_overlay_resolves_a9_not_a8s(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = _setup_a9_repo(Path(tmp.name))
        config = load_config(repo)
        arm = overlay_claude_meta_session(config, harness_root=ROOT)
        self.assertEqual(arm, 'A9')
        tmp.cleanup()

    def test_meta_tool_trace_scope_violation_detected(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = _setup_a9_repo(Path(tmp.name))
        run_dir = Path(tmp.name) / 'run'
        run_dir.mkdir()
        audit = run_dir / 'meta_tools.jsonl'
        rows = [
            {'ts': 1.0, 'tool': 'Read', 'raw': 'evolve/mechanism/evolve_skill.md', 'parent_traversal': False},
            {'ts': 2.0, 'tool': 'Edit', 'raw': 'evolve/mechanism/evolve_skill.md', 'parent_traversal': False},
        ]
        audit.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
        scan = scan_meta_tools_audit(audit, repo, since_ts=0.0, strict_meta=True)
        self.assertIsNone(scan.outcome())
        bad_rows = [
            {'ts': 3.0, 'tool': 'Read', 'raw': 'evolve/mechanism/family_map.md', 'parent_traversal': False},
        ]
        audit.write_text(
            '\n'.join(json.dumps(r) for r in rows + bad_rows) + '\n',
            encoding='utf-8',
        )
        scan_bad = scan_meta_tools_audit(audit, repo, since_ts=0.0, strict_meta=True)
        self.assertNotEqual(scan_bad.outcome(), 'ok')

    @patch('evolver.agents.ClaudeCliAgent.run')
    def test_live_meta_agent_tool_trace_ok(self, mock_run) -> None:
        from evolver.agents import make_meta_agent

        tmp = tempfile.TemporaryDirectory()
        repo = _setup_a9_repo(Path(tmp.name))
        run_dir = Path(tmp.name) / 'run'
        config = load_config(repo, overrides={'run_dir': str(run_dir)})
        overlay_claude_meta_session(config, harness_root=ROOT)
        config.paths.ensure()
        phi = _islands_phi(config, repo)
        mc = MetaController(
            config,
            StubAgent(lambda ctx: AgentResult(status=COMPLETED)),
            Attribution(run_dir / 'attr.jsonl'),
        )
        prompt = mc._prompt(phi)

        audit_path = run_dir / 'meta_tools.jsonl'
        audit_path.write_text(
            '\n'.join(
                json.dumps(r) for r in (
                    {'ts': 1.0, 'tool': 'Read', 'raw': 'evolve/mechanism/evolve_skill.md', 'parent_traversal': False},
                    {'ts': 2.0, 'tool': 'Edit', 'raw': 'evolve/mechanism/evolve_skill.md', 'parent_traversal': False},
                )
            ) + '\n',
            encoding='utf-8',
        )
        mock_run.return_value = AgentResult(
            status=COMPLETED,
            meta_invocation={'audit_path': str(audit_path)},
        )
        agent = make_meta_agent(config)
        ctx = AgentContext(
            repo_root=repo,
            strategy_rel=config.meta_target,
            prompt=prompt,
            phi=phi,
            round_idx=25,
            parent_id=None,
            run_dir=run_dir,
        )
        agent.run(ctx)
        rows = [json.loads(l) for l in audit_path.read_text(encoding='utf-8').splitlines() if l.strip()]
        tools = {r['tool'] for r in rows}
        self.assertIn('Read', tools)
        self.assertIn('Edit', tools)
        self.assertNotIn('Bash', tools)
        self.assertNotIn('Grep', tools)
        raw_joined = ' '.join(str(r.get('raw', '')) for r in rows).lower()
        self.assertNotIn('family_map', raw_joined)
        tmp.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
