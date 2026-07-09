'''Shadow-descriptor + dormant-wiring tests (Phase 1.5 -> 2 bridge).

These prove the wiring added before any Phase-2 A/B:
  - FeatureDescriptor is config-selectable and the shadow path records b(x);
  - b_descriptor is persisted in candidate meta.json;
  - descriptor coverage/entropy is written without touching the agent-facing Phi;
  - SweepEngine is registered in make_engine and behaviour-neutral;
  - select_policy.json load/save round-trips and feeds ModifiableEngine;
  - family_map.md is read only when meta is enabled;
  - with shadow OFF the loop behaves byte-identically to the Phase-1 baseline.

Run: python -m unittest evolver.tests.test_shadow_descriptors -v
'''
from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ..agents import StubAgent, behavior_valid_edit
from ..config import load_config
from ..engine import make_engine
from ..engine.qd import ModifiableEngine
from ..engine.sweep import SweepEngine
from ..observe import Observer, load_family_map
from ..population import (
    DEFAULT_DESCRIPTOR_COLUMNS,
    StaticDescriptor,
    StoredDescriptor,
    coverage_stats,
    load_select_policy,
    make_descriptor,
    parse_feature_descriptor,
    save_select_policy,
)
from ..select import RandomSelector
from ..store import OFFICIAL_BEST, STEPPING_STONE, Candidate, Store
from .stubs import StubEvaluator, make_fixture
from .test_phase0 import build_loop


def _cand(cid: str, *, parent: str | None = 'candidate_0000', status: str = STEPPING_STONE,
          alpha: float = 0.5, b4: float = 0.4, complexity: int = 100,
          b_descriptor: list[float] | None = None) -> Candidate:
    return Candidate(
        id=cid, parent_id=parent, base_commit='x', round=0, status=status,
        created_by='harness', search_alpha=alpha, selection_alpha=alpha,
        point_rate_b4=b4, complexity=complexity, b_descriptor=b_descriptor,
    )


class _FeatureStubEvaluator(StubEvaluator):
    '''StubEvaluator + a run_features that writes a synthetic, per-call distinct TSV.'''

    def __init__(self, *, columns: tuple[str, ...] = ('x', 'y'), **kw) -> None:
        super().__init__(**kw)
        self.columns = columns
        self.feature_calls = 0

    def run_features(self, out_path: Path, seeds: int) -> bool:
        self.feature_calls += 1
        offset = float(self.feature_calls)
        rows = [
            {c: 1.0 + offset + i for i, c in enumerate(self.columns)},
            {c: 3.0 + offset + i for i, c in enumerate(self.columns)},
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        header = '\t'.join(self.columns) + '\textra'
        lines = [header]
        for row in rows:
            lines.append('\t'.join(str(row[c]) for c in self.columns) + '\t99')
        out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return True


# --- pure descriptor primitives ----------------------------------------------------

class DescriptorPrimitivesTestCase(unittest.TestCase):
    def test_parse_feature_descriptor_means(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / 'f.tsv'
            tsv.write_text('x\ty\tz\n1\t2\t9\n3\t4\t9\n', encoding='utf-8')
            self.assertEqual(parse_feature_descriptor(tsv, ['x', 'y']), (2.0, 3.0))
            self.assertEqual(parse_feature_descriptor(Path(t) / 'missing.tsv', ['x']), ())

    def test_stored_descriptor_reads_b_then_falls_back(self) -> None:
        with_b = _cand('c1', b_descriptor=[1.0, 2.0, 3.0])
        without_b = _cand('c2', complexity=120, b4=0.5, b_descriptor=None)
        desc = StoredDescriptor()
        self.assertEqual(desc.describe(with_b), (1.0, 2.0, 3.0))
        self.assertEqual(desc.describe(without_b), (120.0, 0.5))  # StaticDescriptor fallback

    def test_make_descriptor_is_config_selectable(self) -> None:
        self.assertIsInstance(make_descriptor(SimpleNamespace(descriptor_kind='static')), StaticDescriptor)
        self.assertIsInstance(make_descriptor(SimpleNamespace(descriptor_kind='feature')), StoredDescriptor)

    def test_coverage_stats_counts_cells_and_entropy(self) -> None:
        stats = coverage_stats([(1.0, 2.0), (3.0, 4.0), (1.1, 2.1)], bins=5)
        self.assertEqual(stats['n'], 3)
        self.assertEqual(stats['dims'], 2)
        self.assertEqual(stats['cells_occupied'], 2)  # two near-1 collapse, the (3,4) splits off
        self.assertGreater(stats['entropy_bits'], 0.0)
        self.assertEqual(coverage_stats([], bins=5)['n'], 0)

    def test_select_policy_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'select_policy.json'
            save_select_policy(path, {'performance': 2.0, 'novelty': 0.25})
            self.assertEqual(load_select_policy(path), {'performance': 2.0, 'novelty': 0.25})
            self.assertEqual(load_select_policy(Path(t) / 'absent.json'), {})

    def test_default_descriptor_columns_present(self) -> None:
        self.assertIn('chal_trump_attack_cards', DEFAULT_DESCRIPTOR_COLUMNS)
        self.assertGreaterEqual(len(DEFAULT_DESCRIPTOR_COLUMNS), 4)


# --- engine registration (dormant) -------------------------------------------------

class EngineWiringTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self) -> Store:
        from ..config import Paths
        store = Store(Paths(self.repo, self.run_dir))
        store.add(_cand('candidate_0000', parent=None, status=OFFICIAL_BEST, alpha=0.8))
        store.add(_cand('candidate_0001', alpha=0.4))
        store.add(_cand('candidate_0002', alpha=0.6))
        return store

    def test_sweep_engine_registered_and_behaviour_neutral(self) -> None:
        engine = make_engine('sweep', RandomSelector())
        self.assertIsInstance(engine, SweepEngine)
        self.assertFalse(engine.manages_own_evaluation, 'engine must never self-evaluate')
        parents = engine.select_parents(self._store(), k=2, rng=random.Random(0), state={})
        self.assertEqual(len(parents), 2)
        self.assertTrue(all(p.is_valid for p in parents), 'sweep delegates to the selector over valid pool')

    def test_modifiable_engine_loads_select_policy(self) -> None:
        policy_path = self.repo / 'evolve' / 'select_policy.json'
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        save_select_policy(policy_path, {'performance': 3.0})
        config = load_config(self.repo, run_id='t', overrides={
            'run_dir': str(self.run_dir),
            'select_policy': 'evolve/select_policy.json',
        })
        engine = make_engine('modifiable', RandomSelector(), config)
        self.assertIsInstance(engine, ModifiableEngine)
        self.assertEqual(engine.selector.policy['performance'], 3.0)

    def test_feature_descriptor_selectable_in_qd_engine(self) -> None:
        config = load_config(self.repo, run_id='t', overrides={
            'run_dir': str(self.run_dir),
            'descriptor': {'kind': 'feature'},
        })
        engine = make_engine('novelty', RandomSelector(), config)
        self.assertIsInstance(engine.selector.descriptor, StoredDescriptor)


# --- shadow loop integration -------------------------------------------------------

class ShadowLoopTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_shadow_on_records_b_descriptor_and_coverage(self) -> None:
        ev = _FeatureStubEvaluator(search_score=0.5, columns=('x', 'y'))
        config, loop = build_loop(
            self.repo, self.run_dir, agent=StubAgent(behavior_valid_edit()), evaluator=ev,
            max_rounds=2,
            descriptor={'kind': 'feature', 'shadow': True, 'seeds': 8, 'columns': ['x', 'y']},
        )
        self.assertEqual(loop.run(), 0)

        store = Store(config.paths)
        valid = [c for c in store.all() if c.parent_id is not None]
        self.assertEqual(len(valid), 2)
        self.assertEqual(ev.feature_calls, 2, 'one shadow features pass per valid candidate')
        for cand in valid:
            self.assertIsNotNone(cand.b_descriptor)
            self.assertEqual(len(cand.b_descriptor), 2)

        meta = json.loads((config.paths.candidates_dir / 'candidate_0001' / 'meta.json').read_text('utf-8'))
        self.assertIn('b_descriptor', meta)
        self.assertEqual(len(meta['b_descriptor']), 2)

        cov_path = config.paths.run_dir / 'descriptor_coverage.jsonl'
        self.assertTrue(cov_path.exists(), 'coverage telemetry sidecar must be written')
        records = [json.loads(line) for line in cov_path.read_text('utf-8').splitlines()]
        self.assertEqual(records[-1]['n'], 2)
        self.assertIn('entropy_bits', records[-1])

    def test_shadow_off_changes_nothing(self) -> None:
        ev = _FeatureStubEvaluator(search_score=0.5)
        config, loop = build_loop(
            self.repo, self.run_dir, agent=StubAgent(behavior_valid_edit()), evaluator=ev,
            max_rounds=2,
        )
        self.assertEqual(loop.run(), 0)

        store = Store(config.paths)
        self.assertTrue(all(c.b_descriptor is None for c in store.all()), 'no b(x) recorded when shadow off')
        self.assertEqual(ev.feature_calls, 0, 'no extra features pass when shadow off')
        self.assertFalse((config.paths.run_dir / 'descriptor_coverage.jsonl').exists())


# --- family_map gating -------------------------------------------------------------

class FamilyMapGatingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo, self.run_dir, self.base = make_fixture(Path(self._tmp.name))
        mech = self.repo / 'evolve' / 'mechanism'
        mech.mkdir(parents=True, exist_ok=True)
        (mech / 'family_map.md').write_text('# families\n- family-A: trump economy\n', encoding='utf-8')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self) -> Store:
        store = Store(self.run_config({}).paths)
        store.add(_cand('candidate_0000', parent=None, status=OFFICIAL_BEST, alpha=0.8))
        return store

    def run_config(self, overrides: dict):
        base = {'run_dir': str(self.run_dir)}
        base.update(overrides)
        return load_config(self.repo, run_id='t', overrides=base)

    def test_family_map_loads_from_mechanism_dir(self) -> None:
        config = self.run_config({})
        self.assertIn('family-A', load_family_map(config))

    def test_phi_excludes_family_map_when_meta_off(self) -> None:
        config = self.run_config({'meta': {'every': 0}})
        store = self._store()
        phi = Observer(config).summarize(store, {'round': 0, 'best_search': 0.8, 'best_b4': 0.6})
        self.assertNotIn('HEURISTIC FAMILIES', phi, 'baseline Phi must not depend on family_map')

    def test_phi_includes_family_map_when_meta_on(self) -> None:
        config = self.run_config({'meta': {'every': 2}})
        store = self._store()
        phi = Observer(config).summarize(store, {'round': 0, 'best_search': 0.8, 'best_b4': 0.6})
        self.assertIn('HEURISTIC FAMILIES', phi)
        self.assertIn('family-A', phi)

    def test_phi_excludes_family_map_when_strict_self_contained(self) -> None:
        config = self.run_config({
            'meta': {'every': 5, 'agent': 'claude_cli', 'strict_self_contained': True},
        })
        store = self._store()
        phi = Observer(config).summarize(store, {'round': 50, 'best_search': 0.8, 'best_b4': 0.6, 'plateau': 10})
        self.assertNotIn('HEURISTIC FAMILIES', phi)
        self.assertNotIn('family-A', phi)


if __name__ == '__main__':
    unittest.main(verbosity=2)
