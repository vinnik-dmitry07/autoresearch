'''A4 MAP-Elites tests: coarse projected grid + robust elite replacement.

Proves:
  - ProjectedDescriptor keeps only the chosen low-D axes (coarse grid);
  - the robust elite key prefers holdout-confirmed scores and breaks noisy ties by
    lower_ci, so an unconfirmed search bump cannot evict a confirmed elite, while a
    clear gain is still admitted;
  - the default grid key is unchanged (raw perf) -> backward compatible;
  - the engine grids only real-b(x) candidates and threads bins/dims/robust from config;
  - a full map_elites run is parent-selection only: it records coverage and NEVER
    promotes / advances official_best under the locked keep rule.

Run: python -m unittest evolver.tests.test_map_elites -v
'''
from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from ..agents import StubAgent, behavior_valid_edit
from ..config import Paths, load_config
from ..engine import make_engine
from ..engine.qd import MapElitesEngine
from ..population import MapElitesGrid, ProjectedDescriptor, StoredDescriptor
from ..select import RandomSelector
from ..store import OFFICIAL_BEST, STEPPING_STONE, Candidate, Store
from .stubs import StubEvaluator, make_fixture
from .test_phase0 import build_loop


def _c(cid, *, search, sel, holdout=None, lci=0.0, b=(1.0, 1.0, 1.0),
       status=STEPPING_STONE, parent='candidate_0000') -> Candidate:
    return Candidate(
        id=cid, parent_id=parent, base_commit='x', round=0, status=status,
        created_by='harness', search_alpha=search, holdout_alpha=holdout,
        selection_alpha=sel, lower_ci=lci, b_descriptor=list(b),
    )


class ProjectedDescriptorTestCase(unittest.TestCase):
    def test_selects_chosen_axes(self) -> None:
        pd = ProjectedDescriptor(StoredDescriptor(), [2, 3, 5])
        c = _c('c', search=0.5, sel=0.5, b=(10, 11, 12, 13, 14, 15))
        self.assertEqual(pd.describe(c), (12.0, 13.0, 15.0))
        self.assertEqual(pd.dims, 3)

    def test_short_vector_falls_through(self) -> None:
        pd = ProjectedDescriptor(StoredDescriptor(), [2, 3, 5])
        c = _c('c', search=0.5, sel=0.5, b=(1.0, 2.0))  # too short to project
        self.assertEqual(pd.describe(c), (1.0, 2.0))


class RobustEliteKeyTestCase(unittest.TestCase):
    '''bins=1 -> one cell; the elite is decided purely by the replacement key.'''

    def setUp(self) -> None:
        self.desc = StoredDescriptor()
        self.bounds = [(0.0, 1.0)] * 3

    def test_default_key_is_raw_perf(self) -> None:
        # selection_alpha tie -> default (perf) keeps the first seen, ignoring confirmation.
        a = _c('a', search=0.78, sel=0.7644)
        b = _c('b', search=0.7644, holdout=0.7644, sel=0.7644)
        grid = MapElitesGrid(self.desc, self.bounds, bins=1)
        grid.build([a, b])
        self.assertEqual(grid.elites()[0].id, 'a')

    def test_robust_prefers_confirmed_on_tie(self) -> None:
        a = _c('a', search=0.78, sel=0.7644)  # unconfirmed, higher raw search
        b = _c('b', search=0.7644, holdout=0.7644, sel=0.7644)  # confirmed, equal sel
        grid = MapElitesGrid(self.desc, self.bounds, bins=1, key=MapElitesEngine._robust_key)
        grid.build([a, b])
        self.assertEqual(grid.elites()[0].id, 'b', 'confirmed elite must win the tie')

    def test_robust_tiebreaks_by_lower_ci(self) -> None:
        a = _c('a', search=0.77, holdout=0.77, sel=0.77, lci=0.60)
        b = _c('b', search=0.77, holdout=0.77, sel=0.77, lci=0.66)  # tighter confidence
        grid = MapElitesGrid(self.desc, self.bounds, bins=1, key=MapElitesEngine._robust_key)
        grid.build([a, b])
        self.assertEqual(grid.elites()[0].id, 'b')

    def test_robust_still_admits_clear_gain(self) -> None:
        a = _c('a', search=0.70, sel=0.686)
        b = _c('b', search=0.80, sel=0.784)  # clearly better, unconfirmed
        grid = MapElitesGrid(self.desc, self.bounds, bins=1, key=MapElitesEngine._robust_key)
        grid.build([a, b])
        self.assertEqual(grid.elites()[0].id, 'b', 'robustness must not block a real gain')


class MapElitesEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self) -> Store:
        store = Store(Paths(self.repo, self.run_dir))
        # Seed has no b(x); three distinct-cell candidates carry b(x).
        seed = Candidate(id='candidate_0000', parent_id=None, base_commit='x', round=0,
                         status=OFFICIAL_BEST, created_by='harness', search_alpha=0.8,
                         selection_alpha=0.8)
        store.add(seed)
        store.add(_c('candidate_0001', search=0.50, sel=0.50, b=(0.0, 0.0, 0.0)))
        store.add(_c('candidate_0002', search=0.55, sel=0.55, b=(5.0, 5.0, 5.0)))
        store.add(_c('candidate_0003', search=0.60, sel=0.60, b=(9.0, 9.0, 9.0)))
        return store

    def test_grids_only_bx_candidates_and_records_coverage(self) -> None:
        eng = MapElitesEngine(StoredDescriptor(), bins=5, dims=(0, 1, 2), robust=True)
        state: dict = {}
        parents = eng.select_parents(self._store(), 4, random.Random(0), state)
        self.assertEqual(len(parents), 4)
        # 3 b(x) candidates land in 3 distinct cells; the b(x)-less seed is excluded.
        self.assertEqual(state['map_elites_coverage'], 3)
        self.assertTrue(all(p.id != 'candidate_0000' for p in parents))

    def test_uses_projection(self) -> None:
        eng = MapElitesEngine(StoredDescriptor(), bins=5, dims=(0, 1, 2), robust=True)
        self.assertIsInstance(eng.descriptor, ProjectedDescriptor)
        self.assertEqual(eng.descriptor.dims, 3)


class MapElitesConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_config_parses_and_threads(self) -> None:
        config = load_config(self.repo, run_id='t', overrides={
            'run_dir': str(self.run_dir),
            'engine': 'map_elites',
            'descriptor': {'kind': 'feature'},
            'map_elites': {'bins': 5, 'dims': [2, 3, 5], 'robust': True},
        })
        self.assertEqual(config.map_elites_bins, 5)
        self.assertEqual(config.map_elites_dims, (2, 3, 5))
        self.assertTrue(config.map_elites_robust)
        engine = make_engine('map_elites', RandomSelector(), config)
        self.assertIsInstance(engine, MapElitesEngine)
        self.assertTrue(engine.robust)
        self.assertEqual(engine.bins, 5)
        self.assertIsInstance(engine.descriptor, ProjectedDescriptor)

    def test_defaults_reproduce_bare_engine(self) -> None:
        config = load_config(self.repo, run_id='t', overrides={'run_dir': str(self.run_dir)})
        self.assertEqual(config.map_elites_bins, 8)
        self.assertEqual(config.map_elites_dims, ())
        self.assertFalse(config.map_elites_robust)
        engine = make_engine('map_elites', RandomSelector(), config)
        self.assertFalse(engine.robust)
        self.assertNotIsInstance(engine.descriptor, ProjectedDescriptor)


class MapElitesNeverPromotesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_run_is_selection_only(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        ev = StubEvaluator(search_score=0.5)  # below the 0.8 seed -> never triggers keep
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=ev,
            engine='map_elites', descriptor={'kind': 'feature'},
            map_elites={'bins': 5, 'dims': [0, 1], 'robust': True},
            max_rounds=3, K=1,
        )
        self.assertEqual(loop.run(), 0)
        self.assertEqual(loop.state['best_id'], 'candidate_0000', 'official_best must not move')
        self.assertEqual(loop.state['evo_count'], 0, 'no promotions under flat eval')
        self.assertIn('map_elites_coverage', loop.state)
        self.assertEqual(loop.state['round'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
