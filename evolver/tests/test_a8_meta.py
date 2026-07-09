'''A8 Claude CLI meta-agent: config, factory, command build, gates.'''
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evolver.agents import (
    COMPLETED,
    ERROR,
    TURN_LIMIT,
    AgentContext,
    AgentResult,
    ClaudeCliAgent,
    CursorCliAgent,
    StubAgent,
    append_line,
    behavior_valid_edit,
    make_agent,
    make_meta_agent,
)
from evolver.config import load_config
from evolver.meta import MetaController, _meta_diff_in_scope
from evolver.meta_delivery import scan_meta_tools_audit, tool_access_violation
from evolver.tests.stubs import StubEvaluator, make_fixture
from evolver.tests.test_phase0 import build_loop, git

ROOT = Path(__file__).resolve().parents[2]
A8_CFG = ROOT / 'scripts' / 'ladder_configs' / 'A8.json'
A8S_CFG = ROOT / 'scripts' / 'ladder_configs' / 'A8s.json'
A8_CONST = ROOT / 'evolve' / 'mechanism' / 'a8_meta_constitution.md'
A8S_SKILL = ROOT / 'evolve' / 'mechanism' / 'a8s_meta_skill.md'
A8S_CONST = ROOT / 'evolve' / 'mechanism' / 'a8s_meta_constitution.md'


class ConfigMetaSplitTestCase(unittest.TestCase):
    def test_a8_json_loads_meta_session(self) -> None:
        cfg_path = Path(__file__).resolve().parents[2] / 'scripts' / 'ladder_configs' / 'A8.json'
        raw = json.loads(cfg_path.read_text(encoding='utf-8'))
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        (repo / 'evolve').mkdir()
        (repo / 'evolve' / 'config.json').write_text(json.dumps(raw), encoding='utf-8')
        config = load_config(repo)
        self.assertEqual(config.meta_agent_kind, 'claude_cli')
        self.assertEqual(config.meta_session.model, 'claude-opus-4-8')
        self.assertEqual(config.meta_session.effort, 'max')
        self.assertAlmostEqual(config.meta_session.max_budget_usd, 1.50)
        self.assertEqual(config.meta_session.max_turns, 6)
        tools = config.meta_session.allowed_tools
        self.assertTrue(tools)
        self.assertIn('Edit(/evolve/mechanism/evolve_skill.md)', tools)
        self.assertNotIn('Read(/evolver/**)', tools)
        self.assertNotIn('Write', str(tools))
        disallowed = config.meta_session.disallowed_tools
        self.assertTrue(disallowed)
        self.assertIn('Read(**/.claude/**)', disallowed)
        self.assertIn('Read(**/memory/**)', disallowed)
        self.assertEqual(
            config.meta_session.settings_file,
            'evolve/mechanism/a8_meta_claude_settings.json',
        )

    def test_overlay_a8_meta_session_replaces_stale_worktree(self) -> None:
        from evolver.config import overlay_a8_meta_session

        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        stale = {
            'meta': {
                'agent': 'claude_cli',
                'session': {
                    'allowed_tools': [
                        'Read(/evolve/mechanism/**)',
                        'Edit(/evolve/mechanism/evolve_skill.md)',
                    ],
                },
            },
        }
        (repo / 'evolve').mkdir()
        (repo / 'evolve' / 'config.json').write_text(json.dumps(stale), encoding='utf-8')
        config = load_config(repo)
        self.assertIn('mechanism/**', str(config.meta_session.allowed_tools))
        self.assertTrue(overlay_a8_meta_session(config, harness_root=ROOT))
        joined = ','.join(config.meta_session.allowed_tools)
        self.assertIn('evolve_skill.md', joined)
        self.assertNotIn('mechanism/**', joined)
        self.assertIn('family_map', ','.join(config.meta_session.disallowed_tools))
        tmp.cleanup()
        self.assertEqual(config.agent_kind, 'cursor_cli')
        tmp.cleanup()

    def test_claude_cli_meta_prompt_omits_family_map(self) -> None:
        from evolver.meta import Attribution, MetaController

        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        mech = repo / 'evolve' / 'mechanism'
        mech.mkdir(parents=True)
        raw = json.loads(A8_CFG.read_text(encoding='utf-8'))
        (repo / 'evolve' / 'config.json').write_text(json.dumps(raw), encoding='utf-8')
        (mech / 'family_map.md').write_text('- injected-family: must not appear\n', encoding='utf-8')
        (mech / 'meta_skill.md').write_text('# meta skill\n', encoding='utf-8')
        (mech / 'a8_meta_constitution.md').write_text(A8_CONST.read_text(encoding='utf-8'), encoding='utf-8')
        config = load_config(repo)
        run_dir = Path(tempfile.mkdtemp())
        config.paths.run_dir = run_dir
        mc = MetaController(config, StubAgent(lambda ctx: AgentResult(status=COMPLETED)), Attribution(run_dir / 'attr.jsonl'))
        prompt = mc._prompt('phi plateau=51')
        self.assertNotIn('Known heuristic families', prompt)
        self.assertNotIn('injected-family', prompt)
        tmp.cleanup()

    def test_a8s_strict_prompt_uses_self_contained_skill(self) -> None:
        from evolver.meta import Attribution, MetaController

        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        mech = repo / 'evolve' / 'mechanism'
        mech.mkdir(parents=True)
        raw = json.loads(A8S_CFG.read_text(encoding='utf-8'))
        (repo / 'evolve' / 'config.json').write_text(json.dumps(raw), encoding='utf-8')
        (mech / 'family_map.md').write_text('- injected-family: must not appear\n', encoding='utf-8')
        (mech / 'meta_skill.md').write_text('Maintain family_map.md\n', encoding='utf-8')
        (mech / 'a8s_meta_skill.md').write_text(A8S_SKILL.read_text(encoding='utf-8'), encoding='utf-8')
        (mech / 'a8s_meta_constitution.md').write_text(A8S_CONST.read_text(encoding='utf-8'), encoding='utf-8')
        config = load_config(repo)
        self.assertTrue(config.meta_strict_self_contained)
        run_dir = Path(tempfile.mkdtemp())
        config.paths.run_dir = run_dir
        mc = MetaController(config, StubAgent(lambda ctx: AgentResult(status=COMPLETED)), Attribution(run_dir / 'attr.jsonl'))
        prompt = mc._prompt('phi plateau=51')
        self.assertIn('self-contained', prompt)
        self.assertNotIn('Maintain `family_map.md`', prompt)
        self.assertNotIn('Known heuristic families', prompt)
        self.assertNotIn('injected-family', prompt)
        tmp.cleanup()

    def test_overlay_a8s_meta_session(self) -> None:
        from evolver.config import overlay_claude_meta_session

        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        (repo / 'evolve').mkdir()
        (repo / 'evolve' / 'config.json').write_text(json.dumps(json.loads(A8S_CFG.read_text())), encoding='utf-8')
        config = load_config(repo)
        arm = overlay_claude_meta_session(config, harness_root=ROOT)
        self.assertEqual(arm, 'A8s')
        self.assertTrue(config.meta_strict_self_contained)
        self.assertIn('a8s_meta_constitution.md', config.meta_session.append_system_prompt_file)
        tmp.cleanup()

    def test_overlay_a9_meta_session(self) -> None:
        from evolver.config import overlay_claude_meta_session

        a9_cfg = ROOT / 'scripts' / 'ladder_configs' / 'A9.json'
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        (repo / 'evolve').mkdir()
        (repo / 'evolve' / 'config.json').write_text(
            json.dumps(json.loads(a9_cfg.read_text(encoding='utf-8'))), encoding='utf-8',
        )
        config = load_config(repo)
        arm = overlay_claude_meta_session(config, harness_root=ROOT)
        self.assertEqual(arm, 'A9')
        self.assertNotEqual(arm, 'A8s')
        self.assertTrue(config.meta_strict_self_contained)
        self.assertEqual(config.meta_ladder_template, 'A9')


class ClaudeCliAgentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        repo = Path(self._tmp.name)
        config = load_config(repo, overrides={
            'meta': {
                'agent': 'claude_cli',
                'session': {
                    'model': 'claude-opus-4-8',
                    'effort': 'max',
                    'max_turns': 12,
                    'max_budget_usd': 1.50,
                    'allowed_tools': [
                        'Read(/evolve/mechanism/**)',
                        'Edit(/evolve/mechanism/evolve_skill.md)',
                    ],
                },
            },
        })

        class _Cfg:
            repo_root = repo
            session = config.session
            meta_session = config.meta_session

        self.repo = repo
        self.agent = ClaudeCliAgent(_Cfg(), session=config.meta_session)  # type: ignore[arg-type]
        self.ctx = AgentContext(
            repo_root=repo,
            strategy_rel='evolve/mechanism/evolve_skill.md',
            prompt='test',
            phi='',
            round_idx=1,
            parent_id=None,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_command_has_effort_max_no_bare(self) -> None:
        cmd = self.agent._command(self.ctx)
        joined = ' '.join(cmd)
        self.assertIn('--effort max', joined)
        self.assertIn('--model claude-opus-4-8', joined)
        self.assertIn('--permission-mode dontAsk', joined)
        self.assertIn('--no-session-persistence', joined)
        self.assertIn('--max-budget-usd 1.50', joined)
        self.assertNotIn('--bare', joined)

    def test_command_includes_disallowed_tools_when_configured(self) -> None:
        config = load_config(self.repo, overrides={
            'meta': {
                'agent': 'claude_cli',
                'session': {
                    'disallowed_tools': ['Read(**/.claude/**)', 'Bash(*)'],
                },
            },
        })

        class _Cfg:
            repo_root = self.repo
            session = config.session
            meta_session = config.meta_session

        agent = ClaudeCliAgent(_Cfg(), session=config.meta_session)  # type: ignore[arg-type]
        joined = ' '.join(agent._command(self.ctx))
        self.assertIn('--disallowedTools', joined)
        self.assertIn('Read(**/.claude/**)', joined)

    def test_make_meta_agent_type(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        config = load_config(repo, overrides={
            'meta': {'agent': 'claude_cli', 'session': {'effort': 'max'}},
        })
        agent = make_meta_agent(config)
        self.assertIsInstance(agent, ClaudeCliAgent)
        inner = make_agent(config, role='inner')
        self.assertIsInstance(inner, CursorCliAgent)
        tmp.cleanup()

    def test_cost_parse_from_stream(self) -> None:
        event = {'type': 'result', 'usage': {'total_cost_usd': 0.42}}
        self.assertAlmostEqual(ClaudeCliAgent._cost_usd(event), 0.42)

    def test_cost_parse_missing_returns_none(self) -> None:
        self.assertIsNone(ClaudeCliAgent._cost_usd({'type': 'result'}))

    def test_turn_limit_detection(self) -> None:
        self.assertTrue(
            self.agent._is_turn_limit('Reached maximum number of turns', 1, True),
        )

    @patch('subprocess.Popen')
    def test_turn_limit_status_from_cli(self, mock_popen) -> None:
        proc = mock_popen.return_value
        proc.stdin = None
        proc.returncode = 1
        proc.stdout = iter([
            '{"type":"result","is_error":true,"result":"max turns reached"}\n',
        ])
        proc.wait.return_value = 0
        result = self.agent.run(self.ctx)
        self.assertEqual(result.status, TURN_LIMIT)

    def test_tool_use_blocks_write_meta_tools_jsonl(self) -> None:
        fixture = Path(__file__).resolve().parent / 'fixtures' / 'claude_stream_sample.jsonl'
        run_dir = self.repo / 'runs' / 'a8_meta'
        run_dir.mkdir(parents=True)
        ctx = AgentContext(
            repo_root=self.repo,
            strategy_rel='evolve/mechanism/evolve_skill.md',
            prompt='test',
            phi='',
            round_idx=5,
            parent_id=None,
            run_dir=run_dir,
        )
        audit_path = run_dir / 'meta_tools.jsonl'
        seen: set[str] = set()
        with audit_path.open('a', encoding='utf-8') as audit_file:
            for line in fixture.read_text(encoding='utf-8').splitlines():
                event = ClaudeCliAgent._parse(line)
                if event is None:
                    continue
                ClaudeCliAgent._print_progress(event, audit_file, self.repo, seen)

        rows = [json.loads(row) for row in audit_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['tool'], 'Read')
        self.assertIn('a8_meta_constitution.md', rows[0]['raw'])
        self.assertEqual(rows[0]['tool_use_id'], 'toolu_01Ubj4RwppV44zwG5Beixhsn')
        self.assertFalse(rows[0]['parent_traversal'])

    def test_parent_traversal_on_bash_command(self) -> None:
        run_dir = self.repo / 'runs' / 'a8_meta'
        run_dir.mkdir(parents=True)
        audit_path = run_dir / 'meta_tools.jsonl'
        event = {
            'type': 'assistant',
            'message': {
                'content': [{
                    'type': 'tool_use',
                    'id': 'toolu_parent',
                    'name': 'Bash',
                    'input': {'command': 'cat ../secrets.txt'},
                }],
            },
        }
        seen: set[str] = set()
        with audit_path.open('a', encoding='utf-8') as audit_file:
            ClaudeCliAgent._print_progress(event, audit_file, self.repo, seen)
        row = json.loads(audit_path.read_text(encoding='utf-8').strip())
        self.assertTrue(row['parent_traversal'])
        self.assertEqual(row['tool'], 'Bash')


class CursorPreflightTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @patch('subprocess.run')
    def test_preflight_cursor_uses_session_not_token(self, mock_run) -> None:
        sys.path.insert(0, str(ROOT / 'scripts'))
        from ladder_lib import preflight_cursor_cli  # noqa: E402

        mock_run.return_value = type('R', (), {
            'returncode': 0,
            'stdout': '{"type":"result","is_error":false}\n',
            'stderr': '',
        })()
        with patch.dict(os.environ, {'CURSOR_API_KEY': 'crsr_test_key'}, clear=False), \
             patch('evolver.util.load_cursor_ide_access_token', return_value='jwt_bobyard'):
            issues = preflight_cursor_cli(repo_root=self.repo)
        self.assertEqual(issues, [])
        cmd = mock_run.call_args.args[0]
        joined = ' '.join(cmd)
        self.assertIn('--workspace', joined)
        self.assertIn('stream-json', joined)
        self.assertIn('--model', joined)
        self.assertIn('auto', joined)
        self.assertNotIn('AUTH_TOKEN', joined.upper())
        env = mock_run.call_args.kwargs.get('env') or {}
        self.assertNotIn('CURSOR_API_KEY', env)
        self.assertEqual(env.get('CURSOR_AUTH_TOKEN'), 'jwt_bobyard')


class ClaudePreflightTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / 'evolve' / 'mechanism').mkdir(parents=True)
        shutil.copy(A8_CFG, self.repo / 'evolve' / 'config.json')
        shutil.copy(A8_CONST, self.repo / 'evolve' / 'mechanism' / 'a8_meta_constitution.md')
        settings = ROOT / 'evolve' / 'mechanism' / 'a8_meta_claude_settings.json'
        if settings.exists():
            shutil.copy(settings, self.repo / 'evolve' / 'mechanism' / 'a8_meta_claude_settings.json')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @patch('subprocess.run')
    @patch('shutil.which', return_value='/usr/bin/claude')
    def test_preflight_uses_production_flags(self, _which, mock_run) -> None:
        sys.path.insert(0, str(ROOT / 'scripts'))
        from ladder_lib import preflight_claude_cli  # noqa: E402

        mock_run.return_value = type('R', (), {
            'returncode': 0,
            'stdout': '{"type":"result","is_error":false,"result":"OK"}\n',
            'stderr': '',
        })()

        issues = preflight_claude_cli(arm='A8', repo_root=self.repo)
        self.assertEqual(issues, [])
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        joined = ' '.join(cmd)
        self.assertIn('--output-format stream-json', joined)
        self.assertIn('--effort max', joined)
        self.assertIn('--permission-mode dontAsk', joined)
        self.assertIn('--no-session-persistence', joined)
        self.assertIn('--max-budget-usd 1.50', joined)
        self.assertIn('--max-turns 1', joined)
        self.assertIn('--model claude-opus-4-8', joined)
        self.assertIn('--append-system-prompt-file', joined)
        self.assertIn('--allowedTools', joined)
        self.assertIn('--disallowedTools', joined)
        self.assertIn('--settings', joined)
        self.assertNotIn('--output-format json', joined)
        self.assertEqual(mock_run.call_args.kwargs['input'], 'respond with OK')
        self.assertEqual(Path(mock_run.call_args.kwargs['cwd']), self.repo.resolve())

    @patch('subprocess.run')
    @patch('shutil.which', return_value='/usr/bin/claude')
    def test_preflight_surfaces_unknown_flag(self, _which, mock_run) -> None:
        sys.path.insert(0, str(ROOT / 'scripts'))
        from ladder_lib import preflight_claude_cli  # noqa: E402

        mock_run.return_value = type('R', (), {
            'returncode': 2,
            'stdout': '',
            'stderr': 'error: unknown option --effort',
        })()

        issues = preflight_claude_cli(arm='A8', repo_root=self.repo)
        self.assertEqual(len(issues), 1)
        self.assertIn('unknown option', issues[0])


class MetaCostTestCase(unittest.TestCase):
    def test_failed_meta_does_not_charge_max_budget(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo, run_dir, base = make_fixture(Path(tmp.name))
        config, loop = build_loop(
            repo,
            run_dir,
            agent=StubAgent(behavior_valid_edit()),
            evaluator=StubEvaluator(),
            meta={'every': 5, 'agent': 'claude_cli', 'session': {'max_budget_usd': 1.50}},
        )
        loop.best_commit = base
        loop.state['round'] = 5
        loop.state['cost_usd'] = 0.0
        loop.state['best_search'] = 0.5
        loop.meta = type('M', (), {
            'due': staticmethod(lambda _r: True),
            'run': staticmethod(lambda *a, **k: (
                loop.best_commit,
                AgentResult(status=ERROR, error='unknown flag', cost_usd=0.0),
            )),
        })()
        loop.attribution = type('A', (), {'record_round': lambda *a, **k: None})()
        loop._maybe_meta()
        self.assertEqual(loop.state['cost_usd'], 0.0)
        tmp.cleanup()


class MetaSafetyTestCase(unittest.TestCase):
    STRATEGY_REL = 'durak/src/strategy_heuristic.cpp'
    MECH_REL = 'evolve/mechanism/evolve_skill.md'

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))
        (self.repo / 'evolve' / 'mechanism').mkdir(parents=True, exist_ok=True)
        (self.repo / self.MECH_REL).write_text('# skill\n', encoding='utf-8')
        git(self.repo, 'add', self.MECH_REL)
        git(self.repo, 'commit', '-m', 'mech seed')
        self.base = git(self.repo, 'rev-parse', 'HEAD').strip()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_meta_diff_in_scope(self) -> None:
        good = 'diff --git a/evolve/mechanism/evolve_skill.md b/evolve/mechanism/evolve_skill.md\n'
        bad = 'diff --git a/durak/src/strategy_heuristic.cpp b/durak/src/strategy_heuristic.cpp\n'
        self.assertTrue(_meta_diff_in_scope(good))
        self.assertFalse(_meta_diff_in_scope(bad))

    def test_meta_leak_gate_blocks_commit(self) -> None:
        def leak_behavior(ctx: AgentContext) -> AgentResult:
            path = ctx.repo_root / ctx.strategy_rel
            path.write_text(path.read_text('utf-8') + '\n// sweep template\n', encoding='utf-8')
            return AgentResult(status=COMPLETED, summary='leak', agent_stdout='sweep template')

        config = load_config(self.repo, overrides={
            'run_dir': str(self.run_dir),
            'meta': {'every': 5, 'target': self.MECH_REL},
        })
        config.paths.ensure()
        from evolver.meta import Attribution

        mc = MetaController(config, StubAgent(leak_behavior), Attribution(self.run_dir / 'attr.jsonl'))
        commit, _ = mc.run(5, 'phi', self.base, 0.8)
        self.assertEqual(commit, self.base)

    def test_meta_scope_violation_blocks_commit(self) -> None:
        def hack_behavior(ctx: AgentContext) -> AgentResult:
            append_line(ctx, 'meta ok')
            hacked = ctx.repo_root / self.STRATEGY_REL
            hacked.write_text(hacked.read_text('utf-8') + '\n// HACK\n', encoding='utf-8')
            return AgentResult(status=COMPLETED, summary='hack')

        config = load_config(self.repo, overrides={
            'run_dir': str(self.run_dir),
            'meta': {'every': 5, 'target': self.MECH_REL},
        })
        config.paths.ensure()
        from evolver.meta import Attribution

        mc = MetaController(config, StubAgent(hack_behavior), Attribution(self.run_dir / 'attr.jsonl'))
        commit, _ = mc.run(5, 'phi', self.base, 0.8)
        self.assertEqual(commit, self.base)

    def test_meta_empty_patch_logs_skip(self) -> None:
        def noop_behavior(_ctx: AgentContext) -> AgentResult:
            return AgentResult(status=COMPLETED, summary='no edit')

        config = load_config(self.repo, overrides={
            'run_dir': str(self.run_dir),
            'meta': {'every': 5, 'target': self.MECH_REL},
        })
        config.paths.ensure()
        from evolver.meta import Attribution

        mc = MetaController(config, StubAgent(noop_behavior), Attribution(self.run_dir / 'attr.jsonl'))
        with patch('evolver.meta.log') as mock_log:
            commit, _ = mc.run(5, 'phi', self.base, 0.8)
        self.assertEqual(commit, self.base)
        skip_calls = [
            c for c in mock_log.call_args_list
            if 'META skip round 5: empty mechanism diff after COMPLETED' in str(c)
        ]
        self.assertEqual(len(skip_calls), 1)
        rounds = self.run_dir / 'meta_rounds.jsonl'
        self.assertTrue(rounds.exists())
        rows = [json.loads(l) for l in rounds.read_text(encoding='utf-8').splitlines() if l.strip()]
        self.assertEqual(rows[-1]['outcome'], 'empty_patch')

    def test_meta_tool_scope_blocks_commit(self) -> None:
        def scoped_behavior(_ctx: AgentContext) -> AgentResult:
            append_line(_ctx, 'meta scope test')
            return AgentResult(
                status=COMPLETED,
                summary='scope hit',
                scope_violations=('parent traversal in Read: ../../.evolver_runs/archive.json',),
            )

        config = load_config(self.repo, overrides={
            'run_dir': str(self.run_dir),
            'meta': {'every': 5, 'target': self.MECH_REL},
        })
        config.paths.ensure()
        from evolver.meta import Attribution

        mc = MetaController(config, StubAgent(scoped_behavior), Attribution(self.run_dir / 'attr.jsonl'))
        commit, _ = mc.run(5, 'phi', self.base, 0.8)
        self.assertEqual(commit, self.base)
        rows = [json.loads(l) for l in (self.run_dir / 'meta_rounds.jsonl').read_text().splitlines()]
        self.assertEqual(rows[-1]['outcome'], 'scope_violation')

    def test_strict_meta_blocks_family_map_read(self) -> None:
        hit = tool_access_violation(
            'Read',
            str(self.repo / 'evolve' / 'mechanism' / 'family_map.md'),
            self.repo,
            strict_meta=True,
        )
        self.assertIsNotNone(hit)
        self.assertIn('outside contract', hit or '')

    def test_scope_scan_classifies_after_edit(self) -> None:
        audit = self.run_dir / 'meta_tools.jsonl'
        audit.parent.mkdir(parents=True, exist_ok=True)
        t0 = 1000.0
        rows = [
            {'ts': t0 + 1, 'tool': 'Read', 'raw': '/memory/meta.md', 'parent_traversal': False},
            {'ts': t0 + 2, 'tool': 'Edit', 'raw': 'evolve/mechanism/evolve_skill.md',
             'parent_traversal': False},
            {'ts': t0 + 3, 'tool': 'Bash', 'raw': 'git commit -m x', 'parent_traversal': False},
        ]
        audit.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
        scan = scan_meta_tools_audit(
            audit, self.repo, since_ts=t0, strict_meta=True,
        )
        self.assertEqual(scan.outcome(), 'scope_violation_before_and_after_edit')
        after_only = [v for v in scan.violations if v.after_edit]
        before_only = [v for v in scan.violations if not v.after_edit]
        self.assertTrue(before_only)
        self.assertTrue(after_only)

    def test_meta_delivery_commit_records_round(self) -> None:
        def edit_behavior(ctx: AgentContext) -> AgentResult:
            append_line(ctx, 'delivery commit test')
            return AgentResult(status=COMPLETED, summary='edit ok')

        config = load_config(self.repo, overrides={
            'run_dir': str(self.run_dir),
            'meta': {'every': 5, 'target': self.MECH_REL},
        })
        config.paths.ensure()
        from evolver.meta import Attribution

        mc = MetaController(config, StubAgent(edit_behavior), Attribution(self.run_dir / 'attr.jsonl'))
        commit, result = mc.run(7, 'phi', self.base, 0.8)
        self.assertNotEqual(commit, self.base)
        self.assertEqual(result.status, COMPLETED)
        rows = [json.loads(l) for l in (self.run_dir / 'meta_rounds.jsonl').read_text().splitlines()]
        self.assertEqual(rows[-1]['outcome'], 'committed')
        self.assertTrue(rows[-1]['root_identity_ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
