'''SweepEngine (Phase 2): LLM-FREE parameter expansion (zero Agent.prompt calls).

The meta-agent writes ONE sweep spec; the harness expands it into many candidate
snapshots by templating the strategy file, and the evaluator scores each one. Useful for
ablations / parameter sweeps where a per-candidate agent session would be pure cost.
Maps conceptually to sweep_atk_trump.py / a SWEEP mode. Candidates are created_by='sweep'.
'''
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SweepSpec:
    '''One sweep: a base snapshot + named axes of textual substitutions.

    `axes` maps a placeholder token (present in `base_snapshot`) to a list of values.
    The cartesian product of axes yields the candidate snapshots.
    '''

    base_snapshot: str
    axes: dict[str, list[str]] = field(default_factory=dict)

    def size(self) -> int:
        total = 1
        for values in self.axes.values():
            total *= max(1, len(values))
        return total


@dataclass
class SweepVariant:
    label: str
    snapshot: str
    assignment: dict[str, str]


class SweepEngine:
    '''Expands a SweepSpec into concrete candidate snapshots without any agent calls.'''

    name = 'sweep'
    manages_own_evaluation = False  # the harness still scores every variant

    def expand(self, spec: SweepSpec) -> list[SweepVariant]:
        if not spec.axes:
            return [SweepVariant('base', spec.base_snapshot, {})]
        keys = list(spec.axes.keys())
        variants: list[SweepVariant] = []
        for combo in itertools.product(*(spec.axes[k] for k in keys)):
            assignment = dict(zip(keys, combo))
            snapshot = spec.base_snapshot
            for token, value in assignment.items():
                snapshot = snapshot.replace(token, value)
            label = '_'.join(f'{k}={v}' for k, v in assignment.items())
            variants.append(SweepVariant(label, snapshot, assignment))
        return variants
