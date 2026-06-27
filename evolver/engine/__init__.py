'''Optional Phase-2 evolution engines (default OFF, measured vs the Phase-1 baseline).

Every engine obeys the locked contract: it proposes which parent(s) to mutate, but it
NEVER evaluates (the harness scores) and NEVER stops the run (termination is harness-
owned). `manages_own_evaluation` is locked False and `StepResult` has no `stop` field.
'''
from __future__ import annotations

from .base import EvolutionEngine, StepResult, make_engine

__all__ = ['EvolutionEngine', 'StepResult', 'make_engine']
