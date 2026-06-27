'''Quality-diversity engines (Phase 2, default OFF).

Each is a parent-proposal strategy over the flat archive; none evaluates or stops.
They are kept only if they beat the Phase-1 baseline on holdout-confirmed gain per $.
'''
from __future__ import annotations

import random
from typing import Any

from ..population import (
    Descriptor,
    MapElitesGrid,
    ModifiableSelector,
    NoveltySelector,
    StaticDescriptor,
    assign_islands,
)
from ..select import Selector
from ..store import Candidate, Store
from .base import EvolutionEngine


class NoveltyEngine(EvolutionEngine):
    '''Gridless novelty (or curiosity when perf_weight > 0).'''

    def __init__(self, descriptor: Descriptor | None = None, k_nn: int = 3, perf_weight: float = 0.0) -> None:
        self.selector = NoveltySelector(descriptor or StaticDescriptor(), k_nn, perf_weight)
        self.name = 'curiosity' if perf_weight > 0 else 'novelty'

    def select_parents(self, store, k, rng, state):
        return self.selector.select(store.parents_pool(), k, rng)


class MapElitesEngine(EvolutionEngine):
    '''MAP-Elites: sample parents from per-cell elites over an adaptive grid.'''

    name = 'map_elites'

    def __init__(self, descriptor: Descriptor | None = None, bins: int = 8) -> None:
        self.descriptor = descriptor or StaticDescriptor()
        self.bins = bins

    def _bounds(self, pool: list[Candidate]) -> list[tuple[float, float]]:
        vecs = [self.descriptor.describe(c) for c in pool]
        dims = max((len(v) for v in vecs), default=self.descriptor.dims)
        bounds = []
        for i in range(dims):
            vals = [v[i] for v in vecs if i < len(v)] or [0.0]
            lo, hi = min(vals), max(vals)
            bounds.append((lo, hi if hi > lo else lo + 1.0))
        return bounds

    def select_parents(self, store, k, rng, state):
        pool = store.parents_pool()
        if not pool:
            return []
        grid = MapElitesGrid(self.descriptor, self._bounds(pool), self.bins)
        grid.build(pool)
        elites = grid.elites() or pool
        state['map_elites_coverage'] = grid.coverage
        return [rng.choice(elites) for _ in range(k)]


class IslandEngine(EvolutionEngine):
    '''Island model: partition the archive and select within islands (with migration).'''

    name = 'islands'

    def __init__(self, inner: Selector, n_islands: int = 3, migrate_every: int = 5) -> None:
        self.inner = inner
        self.n_islands = n_islands
        self.migrate_every = migrate_every

    def select_parents(self, store, k, rng, state):
        pool = store.parents_pool()
        if not pool:
            return []
        islands = assign_islands(pool, self.n_islands)
        # Migration: every migrate_every rounds, let the global best seed all islands.
        if self.migrate_every and state.get('round', 0) % self.migrate_every == 0:
            best = max(pool, key=lambda c: (c.selection_alpha or c.search_alpha or 0.0))
            for members in islands.values():
                if best not in members:
                    members.append(best)
        chosen: list[Candidate] = []
        keys = [i for i in islands if islands[i]]
        for j in range(k):
            members = islands[keys[j % len(keys)]]
            chosen.extend(self.inner.select(members, 1, rng))
        return chosen


class ModifiableEngine(EvolutionEngine):
    '''Meta-editable weighted selector driven by a policy dict (select_policy.json).'''

    name = 'modifiable'

    def __init__(self, descriptor: Descriptor | None = None, policy: dict[str, float] | None = None) -> None:
        self.selector = ModifiableSelector(descriptor or StaticDescriptor(), policy)

    def select_parents(self, store, k, rng, state):
        return self.selector.select(store.parents_pool(), k, rng)


def make_qd_engine(name: str, selector: Selector) -> EvolutionEngine:
    if name == 'novelty':
        return NoveltyEngine()
    if name == 'curiosity':
        return NoveltyEngine(perf_weight=1.0)
    if name == 'map_elites':
        return MapElitesEngine()
    if name == 'islands':
        return IslandEngine(selector)
    if name == 'modifiable':
        return ModifiableEngine()
    raise ValueError(f'unknown engine: {name!r}')
