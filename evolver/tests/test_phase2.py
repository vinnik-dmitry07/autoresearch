'''Phase-2 tests: engine ABC + greedy ablation, QD primitives, cost-hygiene, meta layer.

Every Phase-2 feature is default OFF; these tests exercise the opt-in paths directly and
re-assert the locked invariants (engines never evaluate/stop; curator never deletes; meta
edits only the mechanism layer; convergence respects the min_rounds floor).

Run: python -m unittest evolver.tests.test_phase2 -v
'''
from __future__ import annotations

import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from ..agents import COMPLETED, AgentContext, AgentResult, StubAgent, append_line, behavior_valid_edit
from ..config import Paths, load_config
from ..curator import Curator
from ..db import EvolutionDB
from ..engine import make_engine
from ..engine.base import DefaultEngine, GreedyEngine
from ..engine.qd import IslandEngine, MapElitesEngine, ModifiableEngine, NoveltyEngine
from ..engine.sweep import SweepEngine, SweepSpec
from ..loop import Loop
from ..meta import Attribution, ConvergencePolicy, MetaController
from ..population import (
    MapElitesGrid,
    ModifiableSelector,
    NoveltySelector,
    StaticDescriptor,
    novelty_scores,
)
from ..select import RandomSelector
from ..store import OFFICIAL_BEST, STEPPING_STONE, Candidate, Store
from .stubs import STRATEGY_REL, StubEvaluator, git, make_fixture
from .test_phase0 import build_loop


def _cand(cid, *, parent='candidate_0000', status=STEPPING_STONE, alpha=0.5,
          b4=0.4, complexity=100, created_by='harness', rnd=0, children=0) -> Candidate:
    return Candidate(
        id=cid, parent_id=parent, base_commit='x', round=rnd, status=status,
        created_by=created_by, search_alpha=alpha, selection_alpha=alpha,
        point_rate_b4=b4, complexity=complexity, n_children=children,
    )


# --- p2-measure-engine -------------------------------------------------------------

class EngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self) -> Store:
        store = Store(Paths(self.repo, self.run_dir))
        store.add(_cand('candidate_0000', parent=None, status=OFFICIAL_BEST, alpha=0.8))
        store.add(_cand('candidate_0001', alpha=0.4))
        store.add(_cand('candidate_0002', alpha=0.6))
        return store

    def test_make_engine_dispatch(self) -> None:
        sel = RandomSelector()
        self.assertIsInstance(make_engine('default', sel), DefaultEngine)
        self.assertIsInstance(make_engine('greedy', sel), GreedyEngine)
        self.assertIsInstance(make_engine('novelty', sel), NoveltyEngine)
        self.assertIsInstance(make_engine('map_elites', sel), MapElitesEngine)
        self.assertIsInstance(make_engine('islands', sel), IslandEngine)
        self.assertIsInstance(make_engine('modifiable', sel), ModifiableEngine)
        with self.assertRaises(ValueError):
            make_engine('nope', sel)

    def test_greedy_always_picks_best(self) -> None:
        store = self._store()
        rng = random.Random(0)
        parents = GreedyEngine().select_parents(store, k=3, rng=rng, state={'best_id': 'candidate_0000'})
        self.assertEqual([p.id for p in parents], ['candidate_0000'] * 3)

    def test_default_engine_matches_selector(self) -> None:
        store = self._store()
        engine = DefaultEngine(RandomSelector())
        parents = engine.select_parents(store, k=2, rng=random.Random(1), state={})
        self.assertEqual(len(parents), 2)
        self.assertTrue(all(p.is_valid for p in parents))

    def test_engine_never_evaluates_or_stops(self) -> None:
        for name in ('default', 'greedy', 'novelty', 'map_elites', 'islands', 'modifiable'):
            engine = make_engine(name, RandomSelector())
            self.assertFalse(engine.manages_own_evaluation, f'{name} must not self-evaluate')
            from ..engine.base import StepResult
            self.assertNotIn('stop', StepResult('x').__dict__, 'StepResult must not carry a stop flag')

    def test_loop_runs_with_greedy_engine(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        _, loop = build_loop(self.repo, self.run_dir, agent=agent,
                             evaluator=StubEvaluator(search_score=0.5), engine='greedy', max_rounds=3)
        self.assertEqual(loop.run(), 0)
        self.assertEqual(loop.state['round'], 3)
        self.assertEqual(loop.engine.name, 'greedy')


# --- p2-qd -------------------------------------------------------------------------

class QualityDiversityTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_novelty_scores_reward_outliers(self) -> None:
        vecs = [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (10.0, 10.0)]
        nov = novelty_scores(vecs, k=2)
        self.assertGreater(nov[3], max(nov[:3]), 'the outlier is the most novel')

    def test_map_elites_keeps_best_per_cell(self) -> None:
        cands = [
            _cand('candidate_0001', b4=0.10, alpha=0.5),
            _cand('candidate_0002', b4=0.15, alpha=0.7),  # same cell as 0001, higher perf
            _cand('candidate_0003', b4=0.90, alpha=0.3),  # different cell
        ]
        grid = MapElitesGrid(StaticDescriptor(), bounds=[(100.0, 100.0), (0.0, 1.0)], bins=2)
        grid.build(cands)
        elite_ids = {c.id for c in grid.elites()}
        self.assertEqual(grid.coverage, 2)
        self.assertIn('candidate_0002', elite_ids)
        self.assertNotIn('candidate_0001', elite_ids, 'lower-perf cell-mate is dominated')
        self.assertIn('candidate_0003', elite_ids)

    def test_novelty_selector_favours_novel(self) -> None:
        pool = [
            _cand('candidate_0001', b4=0.40, complexity=100),
            _cand('candidate_0002', b4=0.40, complexity=100),
            _cand('candidate_0003', b4=0.40, complexity=100),
            _cand('candidate_0004', b4=0.95, complexity=100),  # novel outlier
        ]
        sel = NoveltySelector(StaticDescriptor(), k_nn=2)
        rng = random.Random(7)
        picks = Counter(sel.select(pool, 1, rng)[0].id for _ in range(400))
        self.assertGreater(picks['candidate_0004'] / 400, 0.7)

    def test_modifiable_selector_respects_policy(self) -> None:
        pool = [
            _cand('candidate_0001', alpha=0.9),
            _cand('candidate_0002', alpha=0.5),
            _cand('candidate_0003', alpha=0.1),
        ]
        sel = ModifiableSelector(StaticDescriptor(),
                                 policy={'performance': 1.0, 'novelty': 0.0,
                                         'recency': 0.0, 'fewer_children': 0.0})
        rng = random.Random(3)
        picks = Counter(sel.select(pool, 1, rng)[0].id for _ in range(400))
        self.assertEqual(picks.most_common(1)[0][0], 'candidate_0001')

    def test_qd_engines_run_in_loop(self) -> None:
        for name in ('novelty', 'curiosity', 'map_elites', 'islands', 'modifiable'):
            with tempfile.TemporaryDirectory() as t:
                repo, run_dir, _ = make_fixture(Path(t))
                _, loop = build_loop(repo, run_dir, agent=StubAgent(behavior_valid_edit()),
                                     evaluator=StubEvaluator(search_score=0.5),
                                     engine=name, max_rounds=2)
                self.assertEqual(loop.run(), 0, f'engine {name} should complete')
                self.assertEqual(loop.state['round'], 2)


# --- p2-cost-hygiene ---------------------------------------------------------------

class CostHygieneTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sweep_engine_is_llm_free_cartesian(self) -> None:
        spec = SweepSpec(base_snapshot='val=@A@ mode=@B@', axes={'@A@': ['1', '2'], '@B@': ['x', 'y']})
        self.assertEqual(spec.size(), 4)
        variants = SweepEngine().expand(spec)
        snaps = {v.snapshot for v in variants}
        self.assertEqual(len(variants), 4)
        self.assertIn('val=1 mode=x', snaps)
        self.assertIn('val=2 mode=y', snaps)

    def test_curator_suggests_and_never_deletes(self) -> None:
        store = Store(Paths(self.repo, self.run_dir))
        store.add(_cand('candidate_0000', parent=None, status=OFFICIAL_BEST, alpha=0.8))
        store.add(_cand('candidate_0001', alpha=0.4, rnd=0))            # stale, harness
        store.add(_cand('candidate_0002', alpha=0.4, rnd=0, created_by='external'))  # stale, foreign
        store.usage('candidate_0000').pinned = False  # force an unpinned best to trigger pin suggestion
        curator = Curator(store.paths, min_idle_rounds=2)
        suggestions = curator.suggest(store, round_idx=20)
        kinds = {s.kind for s in suggestions}
        self.assertIn('archive_stale', kinds)
        self.assertIn('pin_lineage', kinds)
        self.assertTrue(all(not s.destructive for s in suggestions), 'curator never proposes deletes')
        before = len(store.all())
        curator.apply_safe(store, suggestions, round_idx=20)
        self.assertEqual(len(store.all()), before, 'apply_safe must never delete records')
        self.assertEqual(store.usage('candidate_0001').state, 'archived')
        self.assertEqual(store.usage('candidate_0002').state, 'active',
                         'foreign-provenance record is not touched')

    def test_evolution_db_search(self) -> None:
        db = EvolutionDB(self.run_dir / 'evolution.db')
        try:
            db.index('candidate_0001', STEPPING_STONE, 'tried trump-economy thresholds')
            db.index('candidate_0002', STEPPING_STONE, 'card-counting endgame switch')
            hits = db.search('trump')
            self.assertEqual([h.candidate_id for h in hits], ['candidate_0001'])
        finally:
            db.close()


# --- p2-meta-convergence -----------------------------------------------------------

class MetaConvergenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))
        mech = self.repo / 'evolve' / 'mechanism'
        mech.mkdir(parents=True)
        (mech / 'evolve_skill.md').write_text('# inner skill v0\n', encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'add mechanism')
        self.base = git(self.repo, 'rev-parse', 'HEAD').strip()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_convergence_respects_floor_then_patience(self) -> None:
        policy = ConvergencePolicy(enabled=True, min_rounds=3, patience=2)
        self.assertIsNone(policy.reason({'round': 2, 'last_official_round': 0}), 'floor blocks early stop')
        self.assertIsNotNone(policy.reason({'round': 3, 'last_official_round': 0}), 'patience exceeded')
        self.assertIsNone(policy.reason({'round': 3, 'last_official_round': 2}), 'recent gain keeps going')
        self.assertIsNone(ConvergencePolicy(False, 0, 1).reason({'round': 99, 'last_official_round': 0}))

    def test_attribution_links_edit_to_delta(self) -> None:
        path = self.run_dir / 'attribution.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        attr = Attribution(path)
        attr.record_edit(2, 'sharpened family rule', best_before=0.80)
        attr.record_round(3, best_search=0.85)
        events = [json.loads(line) for line in path.read_text('utf-8').splitlines()]
        outcome = [e for e in events if e['event'] == 'meta_outcome'][0]
        self.assertAlmostEqual(outcome['delta'], 0.05, places=6)

    def test_meta_edits_only_mechanism_and_resets_strategy(self) -> None:
        def meta_behavior(ctx: AgentContext) -> AgentResult:
            append_line(ctx, 'META-EDIT improve family rule')
            return AgentResult(status=COMPLETED, summary='meta edit')

        config = load_config(self.repo, run_id='m', overrides={
            'run_dir': str(self.run_dir),
            'meta': {'every': 2, 'target': 'evolve/mechanism/evolve_skill.md'},
            'baseline': {'best_search': 0.8},
        })
        config.paths.ensure()
        attr = Attribution(config.paths.run_dir / 'attribution.jsonl')
        mc = MetaController(config, StubAgent(meta_behavior), attr)
        self.assertFalse(mc.due(1))
        self.assertTrue(mc.due(2))
        new_commit, _result = mc.run(round_idx=2, phi='phi', best_commit=self.base, best_before=0.8)
        self.assertNotEqual(new_commit, self.base, 'a mechanism edit advances the commit')
        committed = git(self.repo, 'show', f'{new_commit}:evolve/mechanism/evolve_skill.md')
        self.assertIn('META-EDIT', committed)
        self.assertNotIn('HACK', (self.repo / STRATEGY_REL).read_text('utf-8'))

    def test_loop_converges_after_floor(self) -> None:
        _, loop = build_loop(self.repo, self.run_dir, agent=StubAgent(behavior_valid_edit()),
                             evaluator=StubEvaluator(search_score=0.5), max_rounds=10,
                             convergence={'enabled': True, 'min_rounds': 2, 'patience': 1})
        self.assertEqual(loop.run(), 0)
        self.assertEqual(loop.state['round'], 2, 'stops at the floor, not before and not at max_rounds')
        self.assertTrue(loop.state['finished'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
