'''AEvo evolution harness for the Durak autoresearch loop.

The harness (not the coding agent) owns rounds, budget, scoring, the keep/rollback
gate, and termination. The agent is a bounded, stateless patch generator. See
.cursor/plans/aevo_harness_for_autoresearch_b2455abd.plan.md for the full contract.
'''
from __future__ import annotations

__all__ = ['__version__']
__version__ = '0.1.0'
