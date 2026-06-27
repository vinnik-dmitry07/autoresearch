'''Phase-1.5 hardening tests: hygiene (backup/restore/stale) + worktree isolation.

Run: python -m unittest evolver.tests.test_phase15 -v
'''
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ..agents import StubAgent, behavior_illegal_edit, behavior_valid_edit
from ..config import Paths
from ..loop import Loop
from ..store import STEPPING_STONE, Candidate, Store
from ..worktree import worktree
from .stubs import LOCKED_REL, STRATEGY_REL, StubEvaluator, git, make_fixture
from .test_phase0 import build_loop


def _stone(cid: str, rnd: int, parent: str | None = 'candidate_0000') -> Candidate:
    return Candidate(
        id=cid, parent_id=parent, base_commit='x', round=rnd, status=STEPPING_STONE,
        created_by='harness', search_alpha=0.5, selection_alpha=0.49,
    )


class HygieneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_backup_created_and_restorable(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent,
                                  evaluator=StubEvaluator(search_score=0.5), max_rounds=2)
        loop.run()
        backups = list(config.paths.backups_dir.iterdir())
        self.assertTrue(backups, 'a pre-run/round backup must exist')
        config.paths.state_json.write_text('{ corrupt', encoding='utf-8')  # simulate corruption
        self.assertTrue(loop.hygiene.restore_latest())
        import json
        json.loads(config.paths.state_json.read_text('utf-8'))  # must parse again

    def test_resume_recovers_from_corrupt_state(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(self.repo, self.run_dir, agent=agent,
                                  evaluator=StubEvaluator(search_score=0.5), max_rounds=2)
        loop.run()
        config.paths.state_json.write_text('not json at all', encoding='utf-8')
        loop2 = Loop(config, agent=StubAgent(behavior_valid_edit()), evaluator=StubEvaluator(search_score=0.5))
        loop2.config.max_rounds = 3
        rc = loop2.run(resume=True)
        self.assertEqual(rc, 0)
        self.assertEqual(loop2.state['round'], 3)

    def test_archive_stale_is_reversible_and_never_deletes(self) -> None:
        store = Store(Paths(self.repo, self.run_dir))
        store.add(_stone('candidate_0000', 0, parent=None))
        store.add(_stone('candidate_0001', 0))
        store.add(_stone('candidate_0002', 0))
        store.pin_lineage('candidate_0002', 0)
        moved = store.archive_stale(round_idx=20, min_idle_rounds=2)
        self.assertGreaterEqual(moved, 1)
        pool_ids = [c.id for c in store.parents_pool()]
        self.assertNotIn('candidate_0001', pool_ids, 'stale unpinned record leaves the pool')
        self.assertIn('candidate_0002', pool_ids, 'pinned record stays selectable')
        self.assertEqual(len(store.all()), 3, 'archive_stale must never delete records')
        self.assertEqual(store.usage('candidate_0001').state, 'archived')


class WorktreeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_worktree_isolates_edits(self) -> None:
        main_strategy_before = (self.repo / STRATEGY_REL).read_text(encoding='utf-8')
        with worktree(self.repo, self.base, 'unit') as wt:
            (wt / STRATEGY_REL).write_text(main_strategy_before + '\n// wt edit\n', encoding='utf-8')
            diff = git(wt, 'diff', self.base, '--', STRATEGY_REL)
            self.assertIn('wt edit', diff)
            self.assertEqual((self.repo / STRATEGY_REL).read_text(encoding='utf-8'), main_strategy_before)
        self.assertEqual((self.repo / STRATEGY_REL).read_text(encoding='utf-8'), main_strategy_before)

    def test_loop_with_worktrees_keeps_main_clean(self) -> None:
        agent = StubAgent(behavior_illegal_edit(LOCKED_REL))
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(search_score=0.5),
            use_worktrees=True,
        )
        loop.run()
        cand = Store(config.paths).get('candidate_0001')
        self.assertEqual(cand.status, STEPPING_STONE, 'legal worktree edit still evaluates')
        self.assertNotIn('HACKED', (self.repo / LOCKED_REL).read_text(encoding='utf-8'))
        self.assertEqual(git(self.repo, 'status', '--porcelain').strip(), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
