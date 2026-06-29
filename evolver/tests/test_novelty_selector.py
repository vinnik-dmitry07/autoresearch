'''A2 gridless-novelty selector tests (dormant by default).

Proves the smallest Phase-2 treatment after shadow descriptors:
  - lambda <= 0 reduces to plain score_child_prop (byte-identical baseline);
  - lambda > 0 reweights parents by normalized behavioral novelty of b(x);
  - the multiplier stays in [1, 1 + lambda] (never overrides quality);
  - candidates without a real b(x) get a neutral factor (1.0), seed-safe;
  - the novelty knob is config-selectable and OFF by default.

Run: python -m unittest evolver.tests.test_novelty_selector -v
'''
from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from ..config import load_config
from ..select import (
    ScoreChildPropNoveltySelector,
    ScoreChildPropSelector,
    make_selector,
)
from ..store import STEPPING_STONE, Candidate
from .stubs import make_fixture


def _cand(cid: str, alpha: float = 0.7, n_children: int = 0, invalid: int = 0,
          b: list[float] | None = None) -> Candidate:
    return Candidate(
        id=cid, parent_id='candidate_0000', base_commit='x', round=0, status=STEPPING_STONE,
        created_by='harness', selection_alpha=alpha, search_alpha=alpha,
        n_children=n_children, children_invalid_count=invalid, b_descriptor=b,
    )


class NoveltyFactorTestCase(unittest.TestCase):
    '''Direct, deterministic checks of the novelty multiplier itself.'''

    def test_lambda_zero_is_all_neutral(self) -> None:
        sel = ScoreChildPropNoveltySelector(novelty_lambda=0.0, k_nn=1)
        pool = [_cand('a', b=[0.0, 0.0]), _cand('b', b=[9.0, 9.0])]
        self.assertEqual(sel._novelty_factor(pool), [1.0, 1.0])

    def test_fewer_than_two_real_b_is_neutral(self) -> None:
        sel = ScoreChildPropNoveltySelector(novelty_lambda=0.5, k_nn=1)
        pool = [_cand('a', b=[1.0, 1.0]), _cand('b', b=None), _cand('c', b=None)]
        self.assertEqual(sel._novelty_factor(pool), [1.0, 1.0, 1.0])

    def test_outlier_gets_highest_factor_within_bounds(self) -> None:
        lam = 0.5
        sel = ScoreChildPropNoveltySelector(novelty_lambda=lam, k_nn=1)
        # tight cluster + one far outlier + one b-less candidate (must stay neutral)
        pool = [
            _cand('c0', b=[1.0, 1.0]),
            _cand('c1', b=[1.05, 1.0]),
            _cand('c2', b=[0.95, 1.0]),
            _cand('out', b=[20.0, 20.0]),
            _cand('bless', b=None),
        ]
        factor = sel._novelty_factor(pool)
        self.assertTrue(all(1.0 <= f <= 1.0 + lam + 1e-9 for f in factor), factor)
        self.assertEqual(factor[4], 1.0, 'b-less candidate must stay neutral')
        self.assertAlmostEqual(max(factor), factor[3], msg='outlier must be most novel')
        self.assertGreater(factor[3], factor[0], 'outlier boosted above cluster')


class MakeSelectorTestCase(unittest.TestCase):
    def test_lambda_zero_returns_plain_selector(self) -> None:
        sel = make_selector('score_child_prop', novelty_lambda=0.0)
        self.assertIsInstance(sel, ScoreChildPropSelector)
        self.assertNotIsInstance(sel, ScoreChildPropNoveltySelector)

    def test_lambda_positive_returns_novelty_selector(self) -> None:
        sel = make_selector('score_child_prop', scale=8.0, topk=2,
                            novelty_lambda=0.25, novelty_k=4)
        self.assertIsInstance(sel, ScoreChildPropNoveltySelector)
        self.assertEqual(sel.novelty_lambda, 0.25)
        self.assertEqual(sel.k_nn, 4)
        self.assertEqual(sel.scale, 8.0)
        self.assertEqual(sel.topk, 2)
        self.assertEqual(sel.name, 'score_child_prop+novelty')


class NoveltySamplingTestCase(unittest.TestCase):
    '''With equal base weights, novelty should shift sampling toward the outlier.'''

    def _pool(self) -> list[Candidate]:
        return [
            _cand('c0', b=[1.0, 1.0]),
            _cand('c1', b=[1.05, 1.0]),
            _cand('c2', b=[0.95, 1.0]),
            _cand('out', b=[20.0, 20.0]),
        ]

    def _pick_rate(self, novelty_lambda: float, target: str, draws: int = 4000) -> int:
        sel = make_selector('score_child_prop', novelty_lambda=novelty_lambda, novelty_k=1)
        rng = random.Random(12345)
        pool = self._pool()
        return sum(sel.select(pool, 1, rng)[0].id == target for _ in range(draws))

    def test_novelty_boosts_outlier_pick_rate(self) -> None:
        off = self._pick_rate(0.0, 'out')
        on = self._pick_rate(1.0, 'out')
        self.assertGreater(on, off, f'novelty should raise outlier rate (off={off}, on={on})')

    def test_outlier_beats_cluster_member_when_on(self) -> None:
        out = self._pick_rate(1.0, 'out')
        cluster = self._pick_rate(1.0, 'c0')
        self.assertGreater(out, cluster, f'outlier should outdraw a cluster peer (out={out}, c0={cluster})')

    def test_off_matches_plain_selector_sequence(self) -> None:
        pool = self._pool()
        a = make_selector('score_child_prop', novelty_lambda=0.0)
        b = ScoreChildPropSelector()
        seq_a = [a.select(pool, 1, random.Random(7))[0].id for _ in range(50)]
        seq_b = [b.select(pool, 1, random.Random(7))[0].id for _ in range(50)]
        self.assertEqual(seq_a, seq_b, 'lambda=0 must be byte-identical to baseline selector')


class NoveltyConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_novelty_defaults_off(self) -> None:
        config = load_config(self.repo, run_id='t', overrides={'run_dir': str(self.run_dir)})
        self.assertEqual(config.novelty_lambda, 0.0)
        self.assertEqual(config.novelty_k, 3)

    def test_novelty_block_parsed(self) -> None:
        config = load_config(self.repo, run_id='t', overrides={
            'run_dir': str(self.run_dir),
            'novelty': {'lambda': 0.25, 'k': 5},
        })
        self.assertEqual(config.novelty_lambda, 0.25)
        self.assertEqual(config.novelty_k, 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
