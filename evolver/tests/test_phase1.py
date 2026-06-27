'''Phase-1 search-quality tests: selection + child-only invalidation (no API).

Run: python -m unittest evolver.tests.test_phase1 -v
'''
from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path

from ..agents import StubAgent, behavior_crash, behavior_valid_edit
from ..select import RandomSelector, ScoreChildPropSelector, make_selector
from ..store import OFFICIAL_BEST, STEPPING_STONE, INVALID, Candidate, Store
from .stubs import StubEvaluator, make_fixture
from .test_phase0 import build_loop


def _cand(cid: str, alpha: float, n_children: int = 0, invalid: int = 0) -> Candidate:
    return Candidate(
        id=cid, parent_id=None, base_commit='x', round=0, status=STEPPING_STONE,
        created_by='harness', selection_alpha=alpha, search_alpha=alpha,
        n_children=n_children, children_invalid_count=invalid,
    )


class SelectorTestCase(unittest.TestCase):
    def test_score_child_prop_prefers_high_alpha_low_children(self) -> None:
        rng = random.Random(0)
        sel = ScoreChildPropSelector()
        pool = [_cand('hi', 0.90, n_children=0), _cand('lo', 0.50, n_children=6, invalid=4)]
        picks = [sel.select(pool, 1, rng)[0].id for _ in range(500)]
        self.assertGreater(picks.count('hi'), picks.count('lo'))

    def test_score_child_prop_down_weights_invalid_children(self) -> None:
        rng = random.Random(1)
        sel = ScoreChildPropSelector()
        clean = _cand('clean', 0.80, n_children=0, invalid=0)
        flaky = _cand('flaky', 0.80, n_children=0, invalid=8)
        pool = [clean, flaky]
        picks = [sel.select(pool, 1, rng)[0].id for _ in range(500)]
        self.assertGreater(picks.count('clean'), picks.count('flaky'))

    def test_empty_pool_returns_empty(self) -> None:
        self.assertEqual(ScoreChildPropSelector().select([], 3, random.Random(0)), [])
        self.assertEqual(RandomSelector().select([], 3, random.Random(0)), [])

    def test_make_selector(self) -> None:
        self.assertIsInstance(make_selector('score_child_prop'), ScoreChildPropSelector)
        self.assertIsInstance(make_selector('random'), RandomSelector)
        with self.assertRaises(ValueError):
            make_selector('nope')


class ChildInvalidationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_failed_child_only_invalidates_child(self) -> None:
        agent = StubAgent(behavior_crash())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator())
        loop.run()
        store = Store(config.paths)
        root = store.get('candidate_0000')
        child = store.get('candidate_0001')
        self.assertEqual(child.status, INVALID)
        self.assertEqual(root.status, OFFICIAL_BEST, 'parent must NOT be invalidated by a failed child')
        self.assertEqual(root.children_invalid_count, 1)
        self.assertIn('candidate_0000', [c.id for c in store.parents_pool()])

    def test_stepping_stone_selection_alpha_is_penalized(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent,
            evaluator=StubEvaluator(search_score=0.5), nonconfirm_penalty=0.9,
        )
        loop.run()
        cand = Store(config.paths).get('candidate_0001')
        self.assertEqual(cand.status, STEPPING_STONE)
        self.assertIsNone(cand.holdout_alpha)
        self.assertAlmostEqual(cand.selection_alpha, 0.5 * 0.9, places=6)

    def test_loop_runs_with_score_child_prop_selector(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5),
            selector='score_child_prop', max_rounds=2, K=2,
        )
        loop.run()
        self.assertEqual(loop.state['round'], 2)
        self.assertEqual(loop.selector.name, 'score_child_prop')

    # invariant 9: search vs holdout split --------------------------------------
    def test_stepping_stone_is_search_only(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5))
        loop.run()
        cand = Store(config.paths).get('candidate_0001')
        self.assertEqual(cand.status, STEPPING_STONE)
        self.assertIsNone(cand.holdout_alpha, 'stepping stone must not have a holdout score')
        self.assertEqual(cand.score_kind, 'search')
        self.assertEqual(cand.eval_bank, 'search_seed_0')
        self.assertAlmostEqual(cand.search_alpha, 0.5)

    def test_official_best_requires_holdout(self) -> None:
        agent = StubAgent(behavior_valid_edit('up'))
        evaluator = StubEvaluator(search_score=0.9, full_score=0.9, holdout_score=0.9, lower_ci=1.0)
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=evaluator,
            baseline={'best_search': 0.5, 'best_b4': 0.4, 'best_lower_ci': 0.0},
        )
        loop.run()
        cand = Store(config.paths).get('candidate_0001')
        self.assertEqual(cand.status, OFFICIAL_BEST)
        self.assertIsNotNone(cand.holdout_alpha, 'official best must be holdout-confirmed')
        self.assertEqual(cand.score_kind, 'full')
        self.assertEqual(cand.eval_bank, 'full_seed_0')

    # invariant 11: best lineage pinned -----------------------------------------
    def test_best_lineage_is_pinned(self) -> None:
        agent = StubAgent(behavior_valid_edit('up'))
        evaluator = StubEvaluator(search_score=0.9, full_score=0.9, holdout_score=0.9, lower_ci=1.0)
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=evaluator,
            baseline={'best_search': 0.5, 'best_b4': 0.4, 'best_lower_ci': 0.0},
        )
        loop.run()
        store = Store(config.paths)
        self.assertTrue(store.usage('candidate_0001').pinned)
        self.assertTrue(store.usage('candidate_0000').pinned, 'ancestor of best must be pinned')

    def test_agent_factory_is_invoked(self) -> None:
        calls = {'n': 0}

        def factory(cfg):
            calls['n'] += 1
            return StubAgent(behavior_valid_edit())

        config, _ = build_loop(self.repo, self.run_dir, agent=StubAgent(behavior_valid_edit()),
                               evaluator=StubEvaluator(search_score=0.5))
        from ..loop import Loop
        loop = Loop(config, agent_factory=factory, evaluator=StubEvaluator(search_score=0.5))
        loop.run()
        self.assertEqual(calls['n'], 1, 'agent_factory must be used exactly once (lazy)')
        self.assertEqual(loop.state['round'], 1)

    @unittest.skipIf(os.environ.get('CURSOR_API_KEY'), 'API key present; skip fail-fast check')
    def test_cursor_agent_requires_api_key(self) -> None:
        from ..agents import CursorAgent
        config, _ = build_loop(self.repo, self.run_dir, agent=StubAgent(behavior_valid_edit()),
                               evaluator=StubEvaluator())
        with self.assertRaises(RuntimeError):
            CursorAgent(config)


if __name__ == '__main__':
    unittest.main(verbosity=2)
