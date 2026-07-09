'''Leak scrubbing, allowlist init, and runtime gate tests (Tier A v5 lean).'''
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

from ladder_lib import (  # noqa: E402
    ALLOWLIST_PATH,
    assert_git_isolation,
    load_allowed_paths,
    materialize_base_tree,
    quarantine_contaminated_runs,
    discover_overlay_runs,
    scrub_leaky_text,
    unexpected_paths,
    unsafe_restore_quarantined_runs,
    verify_leak_free,
)
from leak_scan import (  # noqa: E402
    LEAK_MARKER_HASHES,
    marker_hash,
    scan_file,
    scan_text,
)
from evolver.agents import (  # noqa: E402
    AgentContext,
    AgentResult,
    COMPLETED,
    StubAgent,
    behavior_valid_edit,
)
from evolver.config import LeakPolicy  # noqa: E402
from evolver.leak_gate import gate_scan, snapshot_digest  # noqa: E402
from evolver.store import INVALID, Store  # noqa: E402
from evolver.tests.stubs import STRATEGY_REL, StubEvaluator, make_fixture  # noqa: E402
from evolver.tests.test_phase0 import build_loop  # noqa: E402


class LadderLeakTestCase(unittest.TestCase):
    def test_allowed_paths_file_nonempty(self) -> None:
        paths = load_allowed_paths()
        self.assertGreater(len(paths), 50)
        self.assertNotIn('evolve/sweep/template.cpp', paths)
        self.assertTrue(ALLOWLIST_PATH.exists())

    def test_scrub_leaky_text(self) -> None:
        raw = '// near-winner 0.77648 archive family'
        out = scrub_leaky_text(raw)
        self.assertNotIn('0.77648', out)
        self.assertNotIn('near-winner', out)
        self.assertNotIn('archive family', out)

    def test_marker_hash_fixture(self) -> None:
        digest = marker_hash('0.77648')
        self.assertIn(digest, LEAK_MARKER_HASHES)
        hits = scan_text('score was 0.77648 on template path')
        self.assertTrue(hits)

    def test_gate_scan_stdout(self) -> None:
        hits = gate_scan('adapt the sweep template midgame logic', '')
        self.assertTrue(hits)
        self.assertFalse(gate_scan('conservation_take candidate_0019 homonym', ''))

    def test_isolated_git_has_no_main_history(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name) / 'wt'
        wt.mkdir()
        subprocess.run(['git', 'init', '-b', 'scratch/test'], cwd=wt, check=True)
        subprocess.run(['git', 'config', 'user.email', 't@local'], cwd=wt, check=True)
        subprocess.run(['git', 'config', 'user.name', 't'], cwd=wt, check=True)
        (wt / 'README.md').write_text('ok', encoding='utf-8')
        subprocess.run(['git', 'add', '-A'], cwd=wt, check=True)
        subprocess.run(['git', 'commit', '-m', 'init'], cwd=wt, check=True)
        iso = assert_git_isolation(wt)
        self.assertEqual(iso['reachability'], 'isolated_standalone')
        tmp.cleanup()

    def test_materialize_no_sweep_dir(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name) / 'wt'
        materialize_base_tree(wt, ROOT)
        self.assertFalse((wt / 'evolve/sweep/template.cpp').exists())
        bad = unexpected_paths(wt, stage='post_materialize')
        self.assertEqual(bad, [])
        tmp.cleanup()

    def test_pre_agent_marker_in_patch_file(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name)
        leak_file = wt / 'durak/src/strategy_heuristic.cpp'
        leak_file.parent.mkdir(parents=True)
        leak_file.write_text('// near-winner template\n', encoding='utf-8')
        issues = verify_leak_free(wt, stage='post_scratch', pre_agent=True)
        self.assertTrue(any('near-winner' in i or 'marker' in i or 'regex' in i for i in issues))
        tmp.cleanup()

    def test_pre_agent_marker_in_extensionless_patch(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name)
        patch = wt / 'model_patch'
        patch.write_text('adapt sweep template near-winner\n', encoding='utf-8')
        self.assertTrue(scan_file(patch))
        issues = verify_leak_free(wt, stage='post_scratch', pre_agent=True)
        self.assertTrue(
            any('model_patch' in i for i in issues),
            msg=f'expected marker or unexpected-path hit, got {issues}',
        )
        tmp.cleanup()

    def test_discover_runs_skips_contaminated_batch(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        run_root = Path(tmp.name) / 'runs'
        run_root.mkdir()
        bad = run_root / 'A1_20260629_150224'
        good = run_root / 'A1_20260629_999999'
        for d in (bad, good):
            d.mkdir()
            (d / 'archive.json').write_text('[]', encoding='utf-8')
        found = discover_overlay_runs(run_root)
        self.assertIn('A1', found)
        self.assertEqual(found['A1'].name, good.name)
        tmp.cleanup()

    def test_unsafe_restore_requires_explicit_flag(self) -> None:
        with self.assertRaises(RuntimeError):
            unsafe_restore_quarantined_runs()

    def test_quarantine_path_helper(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        run_root = Path(tmp.name) / 'runs'
        q_root = run_root / '_quarantine'
        fake = run_root / 'A1_20260629_150224'
        fake.mkdir(parents=True)
        (fake / 'archive.json').write_text('[]', encoding='utf-8')
        with patch('ladder_lib.RUN_ROOT', run_root), patch('ladder_lib.QUARANTINE_ROOT', q_root):
            moved = quarantine_contaminated_runs(('A1',), batch='150224')
        self.assertEqual(len(moved), 1)
        self.assertTrue((q_root / fake.name / 'QUARANTINED.txt').exists())
        tmp.cleanup()

    def test_leak_in_stdout_skips_scorer_and_store(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        repo, run_dir, _base = make_fixture(root)

        def leaky_agent(ctx: AgentContext) -> AgentResult:
            path = ctx.strategy_path
            path.write_text(path.read_text(encoding='utf-8') + '\n// tweak\n', encoding='utf-8')
            return AgentResult(
                status=COMPLETED,
                agent_stdout='use the sweep template from near-winner',
                leak_hits=('stdout: regex',),
            )

        config, loop = build_loop(
            repo, run_dir,
            agent=StubAgent(leaky_agent),
            evaluator=StubEvaluator(search_score=0.99),
            leak_policy={'enabled': True},
        )
        config.leak_policy = LeakPolicy(enabled=True)
        loop.config = config
        calls = {'precheck': 0}
        real_precheck = loop.evaluator.precheck

        def counted_precheck():
            calls['precheck'] += 1
            return real_precheck()

        loop.evaluator.precheck = counted_precheck  # type: ignore[method-assign]
        loop.run(resume=False)
        self.assertEqual(calls['precheck'], 0)
        archive = run_dir / 'archive.json'
        rows = json.loads(archive.read_text(encoding='utf-8')) if archive.exists() else []
        self.assertEqual(len(rows), 1)  # seed baseline only
        tmp.cleanup()

    def test_leak_in_stdout_without_edit_records_hit(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        repo, run_dir, _base = make_fixture(root)

        def stdout_only_leak(ctx: AgentContext) -> AgentResult:
            return AgentResult(
                status=COMPLETED,
                agent_stdout='adapt the sweep template near-winner 0.77648',
            )

        config, loop = build_loop(
            repo, run_dir,
            agent=StubAgent(stdout_only_leak),
            evaluator=StubEvaluator(search_score=0.99),
            leak_policy={'enabled': True, 'stop_after_hits': 1},
        )
        config.leak_policy = LeakPolicy(enabled=True, stop_after_hits=1)
        loop.config = config
        loop.run(resume=False)
        self.assertGreaterEqual(loop.state.get('leak_hits', 0), 1)
        tmp.cleanup()

    def test_leak_in_snapshot_skips_scorer(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        repo, run_dir, _base = make_fixture(root)

        def snapshot_leak_agent(ctx: AgentContext) -> AgentResult:
            ctx.strategy_path.write_text(
                ctx.strategy_path.read_text(encoding='utf-8')
                + '\n// copied from sweep template near-winner\n',
                encoding='utf-8',
            )
            return AgentResult(status=COMPLETED, agent_stdout='')

        config, loop = build_loop(
            repo, run_dir,
            agent=StubAgent(snapshot_leak_agent),
            evaluator=StubEvaluator(search_score=0.99),
            leak_policy={'enabled': True},
        )
        calls = {'precheck': 0}
        real_precheck = loop.evaluator.precheck

        def counted_precheck():
            calls['precheck'] += 1
            return real_precheck()

        loop.evaluator.precheck = counted_precheck  # type: ignore[method-assign]
        loop.run(resume=False)
        self.assertEqual(calls['precheck'], 0)
        rows = json.loads((run_dir / 'archive.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows), 1)
        tmp.cleanup()

    def test_linked_worktree_fails_isolation(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name) / 'linked'
        wt.mkdir()
        main_git = ROOT / '.git'
        (wt / '.git').write_text(f'gitdir: {main_git}\n', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            assert_git_isolation(wt)
        tmp.cleanup()

    def test_untracked_forbidden_file_fails(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name)
        materialize_base_tree(wt, ROOT)
        forbidden = wt / 'evolve/sweep/template.cpp'
        forbidden.parent.mkdir(parents=True, exist_ok=True)
        forbidden.write_text('// leak\n', encoding='utf-8')
        bad = unexpected_paths(wt, stage='post_materialize')
        self.assertIn('evolve/sweep/template.cpp', bad)
        tmp.cleanup()

    def test_promote_blocked_on_snapshot_hash_change(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        repo, run_dir, base = make_fixture(root)

        class MutatingOnFull(StubEvaluator):
            def run_full(self):
                path = repo / STRATEGY_REL
                path.write_text(
                    path.read_text(encoding='utf-8') + '\n// scorer post-gate mutation\n',
                    encoding='utf-8',
                )
                return super().run_full()

        config, loop = build_loop(
            repo,
            run_dir,
            agent=StubAgent(behavior_valid_edit('improve')),
            evaluator=MutatingOnFull(
                search_score=0.9,
                full_score=0.9,
                holdout_score=0.9,
                lower_ci=1.0,
            ),
            leak_policy={'enabled': True},
            baseline={'best_search': 0.5, 'best_b4': 0.4, 'best_lower_ci': 0.0},
        )
        config.leak_policy = LeakPolicy(enabled=True)
        loop.config = config
        promote_calls = {'n': 0}
        real_promote = loop._promote

        def tracked_promote(full):
            promote_calls['n'] += 1
            return real_promote(full)

        loop._promote = tracked_promote  # type: ignore[method-assign]
        loop.run(resume=False)

        store = Store(config.paths)
        cand = store.get('candidate_0001')
        self.assertIsNotNone(cand)
        self.assertEqual(cand.status, INVALID)
        self.assertIn('promote blocked: snapshot changed after leak gate', cand.reason)
        self.assertEqual(promote_calls['n'], 0)
        self.assertEqual(loop.state['best_commit'], base)
        self.assertNotIn('scorer post-gate mutation', store.snapshot_text('candidate_0001'))
        tmp.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
