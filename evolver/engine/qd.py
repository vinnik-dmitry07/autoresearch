'''Quality-diversity engines (Phase 2, default OFF).

Each is a parent-proposal strategy over the flat archive; none evaluates or stops.
They are kept only if they beat the Phase-1 baseline on holdout-confirmed gain per $.
'''
from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..population import (
    Descriptor,
    MapElitesGrid,
    ModifiableSelector,
    NoveltySelector,
    ProjectedDescriptor,
    StaticDescriptor,
    assign_islands,
    load_select_policy,
    make_descriptor,
)
from ..select import Selector
from ..store import Candidate, Store
from .base import EvolutionEngine

if TYPE_CHECKING:
    from ..config import Config


class NoveltyEngine(EvolutionEngine):
    '''Gridless novelty (or curiosity when perf_weight > 0).'''

    def __init__(self, descriptor: Descriptor | None = None, k_nn: int = 3, perf_weight: float = 0.0) -> None:
        self.selector = NoveltySelector(descriptor or StaticDescriptor(), k_nn, perf_weight)
        self.name = 'curiosity' if perf_weight > 0 else 'novelty'

    def select_parents(self, store, k, rng, state):
        return self.selector.select(store.parents_pool(), k, rng)


class MapElitesEngine(EvolutionEngine):
    '''MAP-Elites: sample parents from per-cell elites over a coarse behavior grid.

    Quality-diversity *parent selection only* - it never scores, promotes, or touches
    official_best (the locked keep rule is unchanged). Two A4 refinements over the bare
    grid: a coarse low-D projection of b(x) (so cells stay populated) and a ROBUST elite
    rule that prefers holdout-confirmed scores and breaks noisy ties by lower_ci, so a
    rare-cell candidate with a lucky search bump cannot enthrone itself as an elite.
    '''

    name = 'map_elites'

    def __init__(
        self, descriptor: Descriptor | None = None, bins: int = 8,
        dims: 'tuple[int, ...] | None' = None, robust: bool = False,
    ) -> None:
        base = descriptor or StaticDescriptor()
        self.descriptor = ProjectedDescriptor(base, dims) if dims else base
        self.bins = bins
        self.robust = robust

    @staticmethod
    def _robust_key(cand: Candidate) -> tuple[float, int, float]:
        '''Robust elite ordering: confirmed score > penalized search, tie-break lower_ci.'''
        confirmed = cand.holdout_alpha is not None
        base = cand.holdout_alpha if confirmed else (cand.selection_alpha or cand.search_alpha or 0.0)
        lci = cand.lower_ci if cand.lower_ci is not None else 0.0
        return (round(float(base), 6), 1 if confirmed else 0, float(lci))

    def _grid_pool(self, pool: list[Candidate]) -> list[Candidate]:
        '''Grid only candidates carrying a real b(x); fall back to the pool if too few.'''
        real = [c for c in pool if getattr(c, 'b_descriptor', None)]
        return real if len(real) >= 2 else pool

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
        gpool = self._grid_pool(pool)
        key = self._robust_key if self.robust else None
        grid = MapElitesGrid(self.descriptor, self._bounds(gpool), self.bins, key=key)
        grid.build(gpool)
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


def _select_policy(config: 'Config | None') -> dict[str, float]:
    '''Load the ModifiableSelector policy from config.select_policy_path ({} if unset).'''
    if config is None or not getattr(config, 'select_policy_path', ''):
        return {}
    path = Path(config.select_policy_path)
    if not path.is_absolute():
        path = config.repo_root / path
    return load_select_policy(path)


def make_qd_engine(name: str, selector: Selector, config: 'Config | None' = None) -> EvolutionEngine:
    # Config-selectable descriptor: 'feature' reads the shadow-collected b(x), else
    # StaticDescriptor. Defaults preserve the previous StaticDescriptor behaviour.
    descriptor = make_descriptor(config) if config is not None else StaticDescriptor()
    if name == 'novelty':
        return NoveltyEngine(descriptor)
    if name == 'curiosity':
        return NoveltyEngine(descriptor, perf_weight=1.0)
    if name == 'map_elites':
        bins = getattr(config, 'map_elites_bins', 8) if config is not None else 8
        dims = tuple(getattr(config, 'map_elites_dims', ()) or ()) if config is not None else ()
        robust = bool(getattr(config, 'map_elites_robust', False)) if config is not None else False
        return MapElitesEngine(descriptor, bins=bins, dims=(dims or None), robust=robust)
    if name == 'islands':
        return IslandEngine(selector)
    if name == 'modifiable':
        return ModifiableEngine(descriptor, _select_policy(config))
    raise ValueError(f'unknown engine: {name!r}')
