'''Harness RNG seed config and replicate helpers.'''
from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from evolver.agents import StubAgent, behavior_valid_edit  # noqa: E402
from evolver.config import load_config  # noqa: E402
from evolver.tests.stubs import StubEvaluator, make_fixture  # noqa: E402
from evolver.tests.test_phase0 import build_loop  # noqa: E402
from ladder_lib import (  # noqa: E402
    DEFAULT_RNG_SEED,
    EXPERIMENTAL_ARMS,
    PHASE1_ARMS,
    arm_rng_seed,
    manifest_spawn_id,
    manifest_spawn_ids,
    parse_manifest_arm,
    validate_replicate_concurrency,
)


class RngSeedConfigTestCase(unittest.TestCase):
    def test_load_config_rng_seed_default(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        (repo / 'evolve').mkdir()
        (repo / 'evolve' / 'config.json').write_text('{}', encoding='utf-8')
        config = load_config(repo)
        self.assertEqual(config.rng_seed, DEFAULT_RNG_SEED)
        tmp.cleanup()

    def test_load_config_rng_seed_override(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        (repo / 'evolve').mkdir()
        (repo / 'evolve' / 'config.json').write_text(
            json.dumps({'rng_seed': 42}), encoding='utf-8',
        )
        config = load_config(repo)
        self.assertEqual(config.rng_seed, 42)
        tmp.cleanup()

    def test_loop_uses_config_rng_seed(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo, run_dir, _base = make_fixture(Path(tmp.name))
        _config, loop = build_loop(
            repo, run_dir,
            agent=StubAgent(behavior_valid_edit()),
            evaluator=StubEvaluator(),
            rng_seed=777,
        )
        expected = random.Random(777)
        draws = [loop.rng.random() for _ in range(5)]
        self.assertEqual(draws, [expected.random() for _ in range(5)])
        tmp.cleanup()


class ReplicateHelpersTestCase(unittest.TestCase):
    def test_arm_rng_seed_offsets_replicate(self) -> None:
        self.assertEqual(arm_rng_seed('A6', 0), DEFAULT_RNG_SEED)
        self.assertEqual(arm_rng_seed('A6', 2), DEFAULT_RNG_SEED + 2)
        self.assertEqual(arm_rng_seed('A8', 1), arm_rng_seed('A6', 1))

    def test_manifest_spawn_ids(self) -> None:
        arms = {
            'A6@r0': {},
            'A6@r1': {},
            'A8@r0': {},
        }
        self.assertEqual(manifest_spawn_ids(arms, ['A6']), ['A6@r0', 'A6@r1'])
        self.assertEqual(manifest_spawn_id('A6', 0, replicates=1), 'A6')
        self.assertEqual(manifest_spawn_id('A6', 2, replicates=3), 'A6@r2')
        self.assertEqual(parse_manifest_arm('A6@r2'), 'A6')

    def test_a9_excluded_from_default_phase1_launch(self) -> None:
        self.assertNotIn('A9', PHASE1_ARMS)
        self.assertIn('A9', EXPERIMENTAL_ARMS)
        sys.path.insert(0, str(ROOT / 'scripts'))
        from launch_ladder_parallel import main as launch_main  # noqa: E402
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--arms', nargs='*', default=list(PHASE1_ARMS))
        args = parser.parse_args([])
        self.assertNotIn('A9', args.arms)

    def test_arm_rng_seed_a9_three_distinct(self) -> None:
        seeds = [arm_rng_seed('A9', r) for r in range(3)]
        self.assertEqual(len(set(seeds)), 3)

    def test_validate_replicate_concurrency_guard(self) -> None:
        self.assertIsNone(validate_replicate_concurrency(1, 3))
        self.assertIsNotNone(validate_replicate_concurrency(3, 3))
        self.assertIn('max_concurrent', validate_replicate_concurrency(2, 2) or '')

    @patch('subprocess.Popen')
    @patch('builtins.open', new_callable=mock_open)
    def test_spawn_arm_passes_rng_seed(self, _mock_file, mock_popen) -> None:
        from ladder_lib import spawn_arm  # noqa: E402

        mock_popen.return_value = MagicMock()
        tmp = tempfile.TemporaryDirectory()
        wt = Path(tmp.name) / 'wt'
        wt.mkdir()
        run_dir = Path(tmp.name) / 'run'
        spawn_arm('A9', wt, run_dir, rng_seed=20260628)
        cmd = mock_popen.call_args.args[0]
        self.assertIn('--rng-seed', cmd)
        idx = cmd.index('--rng-seed')
        self.assertEqual(cmd[idx + 1], '20260628')
        tmp.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
