'''CLI ladder flags and promotion-track gate tests.'''
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evolver.cli import build_parser
from evolver.config import load_config
from evolver.evaluate import Scores
from evolver.tests.stubs import StubEvaluator, make_fixture
from evolver.tests.test_phase0 import build_loop


class CliLadderTestCase(unittest.TestCase):
    def test_run_parser_accepts_repo_root_and_no_results_baseline(self) -> None:
        parser = build_parser()
        args = parser.parse_args(['run', '--repo-root', '/tmp/wt', '--no-results-baseline'])
        self.assertEqual(str(args.repo_root), '/tmp/wt')
        self.assertTrue(args.no_results_baseline)

    def test_no_results_baseline_skips_legacy_tsv(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo, run_dir, _base = make_fixture(Path(tmp.name))
        (repo / 'results.tsv').write_text(
            'x\tB4\t0.99\t0.99\t0.99\t0\t100\tkeep\tlegacy\n', encoding='utf-8',
        )
        config = load_config(repo, overrides={
            'run_dir': str(run_dir),
            'baseline': {'best_search': 0.5, 'best_b4': 0.4, 'best_lower_ci': 0.4},
        })
        self.assertAlmostEqual(config.best_search, 0.5)
        with patch('evolver.cli._apply_results_baseline') as mock_apply, \
             patch('evolver.loop.Loop') as MockLoop:
            from evolver.cli import _cmd_run
            parser = build_parser()
            args = parser.parse_args([
                'run', '--repo-root', str(repo), '--no-results-baseline',
                '--run-dir', str(run_dir), '--max-rounds', '0',
            ])
            MockLoop.return_value.run.return_value = 0
            _cmd_run(args)
            mock_apply.assert_not_called()
        tmp.cleanup()


class PromotionTriggerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, _base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _loop(self, **overrides):
        _config, loop = build_loop(
            self.repo, self.run_dir,
            agent=__import__('evolver.agents', fromlist=['StubAgent']).StubAgent(
                __import__('evolver.agents', fromlist=['behavior_valid_edit']).behavior_valid_edit(),
            ),
            evaluator=StubEvaluator(search_score=0.5),
            promotion={'holdout_trigger_delta': 0.006, 'holdout_trigger_b4_delta': 0.005},
            **overrides,
        )
        loop.state['best_search'] = 0.684
        loop.state['best_b4'] = 0.492
        return loop

    def test_search_delta_triggers_promotion_track(self) -> None:
        loop = self._loop()
        search = Scores('search', 'quick', 0.691, 0.49, 0.0)
        self.assertTrue(loop._should_run_promotion_track(search))

    def test_b4_delta_triggers_when_search_flat(self) -> None:
        loop = self._loop()
        search = Scores('search', 'quick', 0.685, 0.498, 0.0)
        self.assertTrue(loop._should_run_promotion_track(search))

    def test_below_both_thresholds_skips(self) -> None:
        loop = self._loop()
        search = Scores('search', 'quick', 0.688, 0.496, 0.0)
        self.assertFalse(loop._should_run_promotion_track(search))


if __name__ == '__main__':
    unittest.main(verbosity=2)
