'''Quality-diversity primitives (Phase 2): descriptors, novelty, MAP-Elites, islands.

All pure data structures over Candidate lists - no LLM, no simulator. Behavioral
descriptors default to (complexity, point_rate_b4); a richer FeatureDescriptor can read
a `--mode features` TSV when available. Used by the QD engines in engine/qd.py.
'''
from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Callable, Protocol, Sequence

from .store import Candidate

Vector = tuple[float, ...]


class Descriptor(Protocol):
    dims: int

    def describe(self, cand: Candidate) -> Vector:
        ...


class StaticDescriptor:
    '''Cheap behavioral descriptor from candidate meta: (complexity, point_rate_b4).'''

    dims = 2

    def describe(self, cand: Candidate) -> Vector:
        complexity = float(cand.complexity if cand.complexity is not None else 0)
        b4 = float(cand.point_rate_b4 if cand.point_rate_b4 is not None else 0.0)
        return (complexity, b4)


def parse_feature_descriptor(tsv_path: Path, columns: Sequence[str] | None = None) -> Vector:
    '''Aggregate a `--mode features` TSV into a mean-vector behavioral descriptor.'''
    if not tsv_path.exists():
        return ()
    lines = tsv_path.read_text(encoding='utf-8').splitlines()
    if len(lines) < 2:
        return ()
    header = lines[0].split('\t')
    idxs = [header.index(c) for c in (columns or header) if c in header]
    sums = [0.0] * len(idxs)
    count = 0
    for line in lines[1:]:
        cells = line.split('\t')
        if len(cells) < len(header):
            continue
        ok = True
        vals = []
        for j in idxs:
            try:
                vals.append(float(cells[j]))
            except ValueError:
                ok = False
                break
        if not ok:
            continue
        for i, v in enumerate(vals):
            sums[i] += v
        count += 1
    if count == 0:
        return ()
    return tuple(s / count for s in sums)


class FeatureDescriptor:
    '''Descriptor from a per-candidate features TSV, falling back to StaticDescriptor.'''

    def __init__(self, tsv_for: Callable[[Candidate], Path], columns: Sequence[str] | None = None) -> None:
        self.tsv_for = tsv_for
        self.columns = columns
        self._fallback = StaticDescriptor()
        self.dims = self._fallback.dims

    def describe(self, cand: Candidate) -> Vector:
        vec = parse_feature_descriptor(self.tsv_for(cand), self.columns)
        return vec if vec else self._fallback.describe(cand)


def distance(a: Vector, b: Vector) -> float:
    n = min(len(a), len(b))
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(n))) if n else 0.0


def novelty_scores(vectors: list[Vector], k: int = 3) -> list[float]:
    '''Mean distance to the k nearest neighbours (gridless novelty).'''
    out = []
    for i, vi in enumerate(vectors):
        dists = sorted(distance(vi, vj) for j, vj in enumerate(vectors) if j != i)
        nearest = dists[:k] if dists else [0.0]
        out.append(sum(nearest) / len(nearest))
    return out


class MapElitesGrid:
    '''Coarse MAP-Elites: keep the best-performing elite per descriptor cell.'''

    def __init__(self, descriptor: Descriptor, bounds: list[tuple[float, float]], bins: int = 8) -> None:
        self.descriptor = descriptor
        self.bounds = bounds
        self.bins = bins
        self.cells: dict[tuple[int, ...], Candidate] = {}

    def _cell(self, vec: Vector) -> tuple[int, ...]:
        idx = []
        for i, (lo, hi) in enumerate(self.bounds):
            v = vec[i] if i < len(vec) else lo
            span = (hi - lo) or 1.0
            b = int((v - lo) / span * self.bins)
            idx.append(max(0, min(self.bins - 1, b)))
        return tuple(idx)

    @staticmethod
    def _perf(cand: Candidate) -> float:
        return cand.selection_alpha if cand.selection_alpha is not None else (cand.search_alpha or 0.0)

    def build(self, candidates: list[Candidate]) -> None:
        self.cells.clear()
        for cand in candidates:
            cell = self._cell(self.descriptor.describe(cand))
            current = self.cells.get(cell)
            if current is None or self._perf(cand) > self._perf(current):
                self.cells[cell] = cand

    def elites(self) -> list[Candidate]:
        return list(self.cells.values())

    @property
    def coverage(self) -> int:
        return len(self.cells)


def assign_islands(candidates: list[Candidate], n_islands: int) -> dict[int, list[Candidate]]:
    '''Stable partition of candidates into islands by id hash.'''
    islands: dict[int, list[Candidate]] = {i: [] for i in range(n_islands)}
    for cand in candidates:
        islands[hash(cand.id) % n_islands].append(cand)
    return islands


# --- QD selectors -----------------------------------------------------------------

class NoveltySelector:
    '''Gridless selection weighted by novelty (optionally curiosity = novelty*perf).'''

    name = 'novelty'

    def __init__(self, descriptor: Descriptor, k_nn: int = 3, perf_weight: float = 0.0) -> None:
        self.descriptor = descriptor
        self.k_nn = k_nn
        self.perf_weight = perf_weight

    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        if not pool:
            return []
        vectors = [self.descriptor.describe(c) for c in pool]
        nov = novelty_scores(vectors, self.k_nn)
        weights = []
        for cand, n in zip(pool, nov):
            perf = cand.selection_alpha if cand.selection_alpha is not None else (cand.search_alpha or 0.0)
            w = n + self.perf_weight * perf
            weights.append(max(w, 1e-9))
        return rng.choices(pool, weights=weights, k=k)


class ModifiableSelector:
    '''Meta-editable weighted selector. Policy weights live in select_policy.json.'''

    name = 'modifiable'
    DEFAULT_POLICY = {'performance': 1.0, 'novelty': 0.5, 'recency': 0.0, 'fewer_children': 0.5}

    def __init__(self, descriptor: Descriptor, policy: dict[str, float] | None = None, k_nn: int = 3) -> None:
        self.descriptor = descriptor
        self.policy = {**self.DEFAULT_POLICY, **(policy or {})}
        self.k_nn = k_nn

    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        if not pool:
            return []
        vectors = [self.descriptor.describe(c) for c in pool]
        nov = novelty_scores(vectors, self.k_nn)
        weights = []
        for cand, n in zip(pool, nov):
            perf = cand.selection_alpha if cand.selection_alpha is not None else (cand.search_alpha or 0.0)
            recency = 1.0 / (1.0 + max(0, cand.round))
            fewer = 1.0 / (1.0 + cand.n_children)
            w = (
                self.policy['performance'] * perf
                + self.policy['novelty'] * n
                + self.policy['recency'] * recency
                + self.policy['fewer_children'] * fewer
            )
            weights.append(max(w, 1e-9))
        return rng.choices(pool, weights=weights, k=k)
