'''EvolutionEngine ABC (corrected from A-Evolve engine/base.py).

The engine is a pluggable *proposal strategy*: given the archive, it chooses which
parent(s) to mutate this round. It does not score and it cannot stop the run.

Locked contract:
  - `manages_own_evaluation` is LOCKED False - the harness owns scoring.
  - `StepResult` has NO `stop` field - termination is harness-owned.
  - `on_cycle_end(accepted, score)` is advisory only (telemetry / internal counters).
'''
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..select import Selector
from ..store import Candidate, Store


@dataclass
class StepResult:
    '''Outcome of one engine proposal step (no `stop`: the harness owns termination).'''

    mutated: bool
    summary: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)


class EvolutionEngine(ABC):
    '''Pluggable parent-proposal strategy. Never evaluates, never stops.'''

    manages_own_evaluation: bool = False  # LOCKED False
    name: str = 'base'

    @abstractmethod
    def select_parents(
        self, store: Store, k: int, rng: random.Random, state: dict[str, Any],
    ) -> list[Candidate]:
        '''Return up to k parents to mutate this round (valid candidates only).'''

    def on_cycle_end(self, accepted: bool, score: float | None) -> None:  # noqa: D401
        '''Advisory hook after a candidate is scored. Default: no-op.'''
        return None


class DefaultEngine(EvolutionEngine):
    '''Phase-1 baseline: delegate to the configured selector over the valid pool.'''

    name = 'default'

    def __init__(self, selector: Selector) -> None:
        self.selector = selector

    def select_parents(self, store, k, rng, state):
        return self.selector.select(store.parents_pool(), k, rng)


class GreedyEngine(EvolutionEngine):
    '''Ablation: always mutate the single current best (no stepping-stone exploration).

    Reproduces the HyperAgents finding that greedy "replace-the-best" search makes
    little to no progress once local edits dry up. The archive is still recorded; this
    engine just refuses to branch from it. NOT a gate on the real system - a control.
    '''

    name = 'greedy'

    def select_parents(self, store, k, rng, state):
        pool = store.parents_pool()
        if not pool:
            return []
        best_id = state.get('best_id')
        best = store.get(best_id) if best_id else None
        if best is None or not best.is_valid:
            best = max(pool, key=lambda c: (c.selection_alpha or c.search_alpha or 0.0))
        return [best for _ in range(k)]


def make_engine(name: str, selector: Selector) -> EvolutionEngine:
    if name in ('default', '', None):
        return DefaultEngine(selector)
    if name == 'greedy':
        return GreedyEngine()
    # QD engines are registered lazily to avoid importing numpy-free heavy modules early.
    from . import qd

    return qd.make_qd_engine(name, selector)
