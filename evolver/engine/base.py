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
from typing import TYPE_CHECKING, Any

from ..select import Selector
from ..store import Candidate, Store

if TYPE_CHECKING:
    from ..config import Config


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

    def propose_snapshot(
        self, store: Store, state: dict[str, Any], rng: random.Random,
    ) -> str | None:
        '''Optional LLM-free candidate source (e.g. a parameter-sweep variant).

        Default None -> the harness runs the bounded agent session as usual. An engine
        that returns a strategy-file snapshot makes the harness skip the agent and score
        that snapshot directly (still through the locked precheck/keep gate).
        '''
        return None

    def exhausted(self) -> bool:
        '''True when an LLM-free engine has no proposals left (harness terminates).'''
        return False

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


def make_engine(name: str, selector: Selector, config: 'Config | None' = None) -> EvolutionEngine:
    if name in ('default', '', None):
        return DefaultEngine(selector)
    if name == 'greedy':
        return GreedyEngine()
    if name == 'sweep':
        # LLM-free parameter sweep. Registered but default OFF; behaviour-neutral
        # (delegates to selector) until a template + axes are supplied via config.
        from .sweep import SweepEngine, SweepSpec

        engine = SweepEngine(selector)
        if config is not None and config.sweep_template and config.sweep_axes:
            template_path = config.repo_root / config.sweep_template
            spec = SweepSpec(
                base_snapshot=template_path.read_text(encoding='utf-8'),
                axes={token: list(values) for token, values in config.sweep_axes.items()},
            )
            engine.load_spec(spec)
        return engine
    # QD engines are registered lazily to avoid importing heavy modules early.
    from . import qd

    return qd.make_qd_engine(name, selector, config)
