'''Phase-0 authority-separation proof (invariants 1-8), stub agents only, no API.

Run: python -m unittest evolver.tests.test_phase0 -v
'''
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ..agents import COMPLETED, AgentResult, StubAgent, append_line, behavior_illegal_edit, \
    behavior_timeout, behavior_valid_edit, behavior_write_scores, behavior_done_text
from ..config import load_config
from ..loop import Loop
from ..store import OFFICIAL_BEST, STEPPING_STONE, INVALID, Store
from ..util import atomic_write_json
from .stubs import LOCKED_REL, STRATEGY_REL, StubEvaluator, git, make_fixture


def build_loop(repo: Path, run_dir: Path, *, agent, evaluator, **overrides) -> tuple:
    base_overrides = {
        'run_dir': str(run_dir),
        'max_rounds': 1,
        'K': 1,
        'cost_cap_usd': 100.0,
        'selector': 'random',
        'baseline': {'best_search': 0.8, 'best_b4': 0.6, 'best_lower_ci': 0.0},
        'session': {'cost_per_session_usd': 0.0},
    }
    base_overrides.update(overrides)
    config = load_config(repo_root=repo, run_id='t', overrides=base_overrides)
    loop = Loop(config, agent=agent, evaluator=evaluator)
    return config, loop


class Phase0TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo, self.run_dir, self.base = make_fixture(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _candidate(self, store: Store, cid: str):
        cand = store.get(cid)
        self.assertIsNotNone(cand, f'missing {cid}')
        return cand

    # 1 -------------------------------------------------------------------------
    def test_invariant_1_no_early_stop(self) -> None:
        agent = StubAgent(behavior_done_text())  # emits DONE/PLATEAU every session
        evaluator = StubEvaluator(search_score=0.5)  # flat, below best -> no progress
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=evaluator, max_rounds=4)
        loop.run()
        self.assertEqual(loop.state['round'], 4, 'DONE/PLATEAU must not stop the outer loop')
        self.assertTrue(loop.state['finished'])
        store = Store(config.paths)
        non_root = [c for c in store.all() if c.parent_id is not None]
        self.assertEqual(len(non_root), 4)
        self.assertTrue(all(c.status == STEPPING_STONE for c in non_root))
        self.assertEqual(loop.state['best_id'], 'candidate_0000')  # never self-promoted

    # 2 -------------------------------------------------------------------------
    def test_invariant_2_illegal_edit_reset(self) -> None:
        agent = StubAgent(behavior_illegal_edit(LOCKED_REL))
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator())
        loop.run()
        locked = (self.repo / LOCKED_REL).read_text(encoding='utf-8')
        self.assertNotIn('HACKED', locked, 'illegal edit to the evaluator must be discarded')
        patch = (config.paths.candidates_dir / 'candidate_0001' / 'model_patch.diff').read_text(encoding='utf-8')
        self.assertIn('strategy_heuristic.cpp', patch)
        self.assertNotIn('simulate.cpp', patch)
        self.assertEqual(self._candidate(Store(config.paths), 'candidate_0001').status, STEPPING_STONE)

    # 3 -------------------------------------------------------------------------
    def test_invariant_3_no_self_scoring(self) -> None:
        agent = StubAgent(behavior_write_scores())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5))
        loop.run()
        scores = json.loads((config.paths.candidates_dir / 'candidate_0001' / 'scores.json').read_text('utf-8'))
        self.assertEqual(scores['search_score'], 0.5, 'official score must come from the harness')
        self.assertEqual(scores['created_by'], 'harness')
        self.assertFalse((self.repo / 'scores.json').exists(), 'agent scores.json must be cleaned')
        canonical = config.paths.results_tsv.read_text(encoding='utf-8')
        self.assertNotIn('FAKE', canonical)
        self.assertIn('commit\topponent', canonical)

    # 4 -------------------------------------------------------------------------
    def test_invariant_4_crash_is_not_fatal(self) -> None:
        counter = {'n': 0}

        def crash_then_valid(ctx):
            counter['n'] += 1
            if counter['n'] == 1:
                append_line(ctx, 'partial before crash')
                raise RuntimeError('boom')
            append_line(ctx, 'valid after crash')
            return AgentResult(status=COMPLETED)

        agent = StubAgent(crash_then_valid)
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(), K=2)
        loop.run()  # must not raise
        store = Store(config.paths)
        self.assertEqual(self._candidate(store, 'candidate_0001').status, INVALID)
        self.assertEqual(self._candidate(store, 'candidate_0002').status, STEPPING_STONE)
        self.assertEqual(git(self.repo, 'status', '--porcelain').strip(), '', 'tree must be clean after crash')

    def test_invariant_4b_timeout_is_invalid(self) -> None:
        agent = StubAgent(behavior_timeout())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator())
        loop.run()
        cand = self._candidate(Store(config.paths), 'candidate_0001')
        self.assertEqual(cand.status, INVALID)
        self.assertIn('timeout', cand.reason)

    # 5 -------------------------------------------------------------------------
    def test_invariant_5_regression_preserved_and_selectable(self) -> None:
        agent = StubAgent(behavior_valid_edit('regression'))
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5))
        loop.run()
        store = Store(config.paths)
        cand = self._candidate(store, 'candidate_0001')
        self.assertEqual(cand.status, STEPPING_STONE)
        self.assertEqual(loop.state['best_id'], 'candidate_0000', 'regression must not advance best')
        self.assertIn('candidate_0001', [c.id for c in store.parents_pool()])

    # 6 -------------------------------------------------------------------------
    def test_invariant_6_runtime_store_survives_reset_clean(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5), max_rounds=2)
        loop.run()
        before = len(Store(config.paths).all())
        # Worst case: a full destructive reset/clean of the repo working tree.
        git(self.repo, 'reset', '--hard', self.base)
        git(self.repo, 'clean', '-fd')
        store = Store(config.paths)
        self.assertEqual(len(store.all()), before)
        self.assertTrue(config.paths.archive_json.exists())
        self.assertTrue(config.paths.state_json.exists())
        self.assertTrue((config.paths.candidates_dir / 'candidate_0001').exists())

    # 7 -------------------------------------------------------------------------
    def test_invariant_7_atomic_artifacts(self) -> None:
        target = self.run_dir / 'atomic.json'
        config, _ = build_loop(self.repo, self.run_dir, agent=StubAgent(behavior_valid_edit()), evaluator=StubEvaluator())
        atomic_write_json(target, {'v': 1})
        with mock.patch('evolver.util.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                atomic_write_json(target, {'v': 2})
        self.assertEqual(json.loads(target.read_text('utf-8'))['v'], 1, 'crash mid-write must not corrupt prior file')

    # 8 -------------------------------------------------------------------------
    def test_invariant_8_archive_append_only(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5), max_rounds=2)
        loop.run()
        history = config.paths.history_jsonl.read_text(encoding='utf-8').strip().splitlines()
        self.assertEqual(len(history), 3, 'root + 2 candidates, each appended once')
        first_ids = [c.id for c in Store(config.paths).all()]
        # Resume one more round: archive must only grow.
        loop2 = Loop(config, agent=StubAgent(behavior_valid_edit()), evaluator=StubEvaluator(search_score=0.5))
        config.max_rounds = 3
        loop2.config.max_rounds = 3
        loop2.run(resume=True)
        grown = [c.id for c in Store(config.paths).all()]
        self.assertTrue(set(first_ids).issubset(set(grown)))
        self.assertGreater(len(grown), len(first_ids))

    # external termination: cost cap + operator stop flag ----------------------
    def test_cost_cap_halts_externally(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5),
            max_rounds=10, cost_cap_usd=1.5, session={'cost_per_session_usd': 1.0},
        )
        loop.run()
        self.assertEqual(loop.state['round'], 2, 'cost cap, not the agent, must stop the run')
        self.assertGreaterEqual(loop.state['cost_usd'], 1.5)

    def test_operator_stop_flag(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(), max_rounds=5)
        (config.paths.run_dir / 'stop.flag').write_text('stop\n', encoding='utf-8')
        loop.run()
        self.assertEqual(loop.state['round'], 0, 'operator stop halts at the round boundary')
        self.assertTrue(loop.state['finished'])

    # promotion (exercises _promote: invariant-9 preview) -----------------------
    def test_promotion_advances_best_with_tag(self) -> None:
        agent = StubAgent(behavior_valid_edit('improve'))
        evaluator = StubEvaluator(search_score=0.9, full_score=0.9, holdout_score=0.9, lower_ci=1.0)
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=evaluator,
            baseline={'best_search': 0.5, 'best_b4': 0.4, 'best_lower_ci': 0.0},
        )
        loop.run()
        store = Store(config.paths)
        cand = self._candidate(store, 'candidate_0001')
        self.assertEqual(cand.status, OFFICIAL_BEST)
        self.assertAlmostEqual(loop.state['best_search'], 0.9)
        self.assertEqual(loop.state['best_id'], 'candidate_0001')
        self.assertIn('evo-1', git(self.repo, 'tag', '--list', 'evo-*'))
        self.assertNotEqual(loop.state['best_commit'], self.base)


if __name__ == '__main__':
    unittest.main(verbosity=2)
