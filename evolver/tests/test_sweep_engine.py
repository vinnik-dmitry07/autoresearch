'''A3 SweepEngine tests: LLM-free parameter expansion wired through the keep gate.

Proves:
  - SweepSpec.expand is a cartesian product with token substitution + stable labels;
  - load_spec/propose_snapshot serve variants in order then stop; exhausted() flips;
  - without a spec the engine is behaviour-neutral (delegates to the selector);
  - make_engine builds variants from config template+axes; config parses the block;
  - a full loop run scores every variant through precheck/keep, marks them
    created_by='sweep' (zero agent calls), and terminates with 'sweep complete'.

Run: python -m unittest evolver.tests.test_sweep_engine -v
'''
from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from ..agents import StubAgent, behavior_valid_edit
from ..config import Paths, load_config
from ..engine import make_engine
from ..engine.sweep import SweepEngine, SweepSpec
from ..select import RandomSelector
from ..store import OFFICIAL_BEST, STEPPING_STONE, Candidate, Store
from .stubs import STRATEGY_REL, StubEvaluator, make_fixture
from .test_phase0 import build_loop

TEMPLATE_REL = 'evolve/sweep/template.cpp'
TEMPLATE = '''namespace durak {
constexpr int kHeuristicCount = 5;
constexpr int kParameterCount = 0;
int defend_deck = __H2_DECK__;
int strip_opp = __H4_OPP__;
}
'''


def _cand(cid: str, *, parent='candidate_0000', status=STEPPING_STONE, alpha=0.5) -> Candidate:
    return Candidate(
        id=cid, parent_id=parent, base_commit='x', round=0, status=status,
        created_by='harness', search_alpha=alpha, selection_alpha=alpha,
    )


class SweepSpecTestCase(unittest.TestCase):
    def test_expand_cartesian_and_substitution(self) -> None:
        spec = SweepSpec(base_snapshot='a=__A__ b=__B__',
                         axes={'__A__': ['1', '2'], '__B__': ['9']})
        variants = SweepEngine().expand(spec)
        self.assertEqual(len(variants), 2)
        snaps = sorted(v.snapshot for v in variants)
        self.assertEqual(snaps, ['a=1 b=9', 'a=2 b=9'])
        self.assertTrue(all('__' not in v.snapshot for v in variants), 'all tokens substituted')

    def test_expand_no_axes_is_single_base(self) -> None:
        variants = SweepEngine().expand(SweepSpec(base_snapshot='plain'))
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].snapshot, 'plain')


class SweepEngineQueueTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.eng = SweepEngine(RandomSelector())
        self.n = self.eng.load_spec(SweepSpec(base_snapshot='v=__V__',
                                              axes={'__V__': ['1', '2', '3']}))

    def test_load_spec_counts_variants(self) -> None:
        self.assertEqual(self.n, 3)
        self.assertTrue(self.eng.active)

    def test_propose_serves_in_order_then_none(self) -> None:
        rng = random.Random(0)
        served = []
        for _ in range(5):
            snap = self.eng.propose_snapshot(store=None, state={}, rng=rng)
            if snap is not None:
                served.append(snap)
        self.assertEqual(served, ['v=1', 'v=2', 'v=3'])

    def test_exhausted_transitions(self) -> None:
        rng = random.Random(0)
        self.assertFalse(self.eng.exhausted())
        for _ in range(3):
            self.eng.propose_snapshot(store=None, state={}, rng=rng)
        self.assertTrue(self.eng.exhausted())


class SweepEngineNeutralTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self) -> Store:
        store = Store(Paths(self.repo, self.run_dir))
        store.add(_cand('candidate_0000', parent=None, status=OFFICIAL_BEST, alpha=0.8))
        store.add(_cand('candidate_0001', alpha=0.5))
        return store

    def test_no_spec_is_neutral(self) -> None:
        eng = SweepEngine(RandomSelector())
        self.assertFalse(eng.active)
        self.assertIsNone(eng.propose_snapshot(self._store(), {}, random.Random(0)))
        self.assertFalse(eng.exhausted())
        parents = eng.select_parents(self._store(), 2, random.Random(0), {})
        self.assertEqual(len(parents), 2, 'neutral sweep delegates to the selector')

    def test_active_select_parents_anchors_on_best(self) -> None:
        eng = SweepEngine(RandomSelector())
        eng.load_spec(SweepSpec(base_snapshot='x=__X__', axes={'__X__': ['1', '2']}))
        parents = eng.select_parents(self._store(), 2, random.Random(0), {'best_id': 'candidate_0000'})
        self.assertEqual([p.id for p in parents], ['candidate_0000', 'candidate_0000'])


class SweepConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))
        (self.repo / 'evolve' / 'sweep').mkdir(parents=True, exist_ok=True)
        (self.repo / TEMPLATE_REL).write_text(TEMPLATE, encoding='utf-8')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _config(self, axes):
        return load_config(self.repo, run_id='t', overrides={
            'run_dir': str(self.run_dir),
            'engine': 'sweep',
            'sweep': {'template': TEMPLATE_REL, 'axes': axes},
        })

    def test_config_parses_sweep_block(self) -> None:
        config = self._config({'__H2_DECK__': ['4', '5', '6'], '__H4_OPP__': ['2', '3']})
        self.assertEqual(config.sweep_template, TEMPLATE_REL)
        self.assertEqual(config.sweep_axes['__H2_DECK__'], ('4', '5', '6'))
        self.assertEqual(config.sweep_axes['__H4_OPP__'], ('2', '3'))

    def test_sweep_defaults_empty(self) -> None:
        config = load_config(self.repo, run_id='t', overrides={'run_dir': str(self.run_dir)})
        self.assertEqual(config.sweep_template, '')
        self.assertEqual(config.sweep_axes, {})

    def test_make_engine_loads_variants_from_config(self) -> None:
        config = self._config({'__H2_DECK__': ['4', '5', '6'], '__H4_OPP__': ['2', '3']})
        engine = make_engine('sweep', RandomSelector(), config)
        self.assertIsInstance(engine, SweepEngine)
        self.assertTrue(engine.active)
        self.assertEqual(engine._idx, 0)  # not yet served
        self.assertEqual(len(engine._variants), 6)  # 3 x 2 cartesian


class SweepLoopIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))
        (self.repo / 'evolve' / 'sweep').mkdir(parents=True, exist_ok=True)
        (self.repo / TEMPLATE_REL).write_text(TEMPLATE, encoding='utf-8')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sweep_run_scores_every_variant_then_completes(self) -> None:
        # A pure sweep must never invoke the agent (asserted via agent.calls below).
        agent = StubAgent(behavior_valid_edit())
        ev = StubEvaluator(search_score=0.5)
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=ev,
            engine='sweep', max_rounds=50, K=1,
            sweep={'template': TEMPLATE_REL, 'axes': {'__H2_DECK__': ['4', '5', '6'],
                                                      '__H4_OPP__': ['2', '3']}},
        )
        self.assertEqual(loop.run(), 0)

        self.assertEqual(agent.calls, 0, 'a pure parameter sweep must make zero agent calls')
        store = Store(config.paths)
        sweep_cands = [c for c in store.all() if c.created_by == 'sweep']
        self.assertEqual(len(sweep_cands), 6, 'all 3x2 variants scored as candidates')
        self.assertEqual(ev.search_calls, 6, 'each variant ran the search gate once')
        self.assertTrue(all(c.parent_id == 'candidate_0000' for c in sweep_cands),
                        'variants are lineage children of the swept family')

        # Stored snapshots are the substituted templates (real token expansion).
        decks = {store.snapshot_text(c.id).split('defend_deck = ')[1].split(';')[0]
                 for c in sweep_cands}
        self.assertEqual(decks, {'4', '5', '6'})
        self.assertTrue(loop.state['finished'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
