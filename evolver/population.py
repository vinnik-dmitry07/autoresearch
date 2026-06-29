'''Quality-diversity primitives (Phase 2): descriptors, novelty, MAP-Elites, islands.

All pure data structures over Candidate lists - no LLM, no simulator. Behavioral
descriptors default to (complexity, point_rate_b4); a richer FeatureDescriptor can read
a `--mode features` TSV when available. Used by the QD engines in engine/qd.py.
'''
from __future__ import annotations

import math
import random
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol, Sequence

from .store import Candidate
from .util import atomic_write_json, read_json

if TYPE_CHECKING:
    from .config import Config

Vector = tuple[float, ...]

# Curated, cheap, behavioral macro-features for b(x). Means over a small `--mode
# features` run characterize a strategy's family (trump aggression, take pressure,
# endgame trump retention, game length) without leaking the official score.
DEFAULT_DESCRIPTOR_COLUMNS: tuple[str, ...] = (
    'chal_trump_attack_cards',
    'chal_forced_takes',
    'chal_voluntary_takes',
    'chal_cards_taken',
    'chal_final_trumps',
    'battles',
)


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


class StoredDescriptor:
    '''Reads the shadow-collected `b_descriptor` from meta; falls back to StaticDescriptor.

    This is the handoff between shadow descriptors and QD: the loop records b(x) once
    via a `--mode features` pass, and any later QD engine reads it back for free.
    '''

    def __init__(self) -> None:
        self._fallback = StaticDescriptor()
        self.dims = self._fallback.dims

    def describe(self, cand: Candidate) -> Vector:
        if cand.b_descriptor:
            return tuple(float(x) for x in cand.b_descriptor)
        return self._fallback.describe(cand)


def make_descriptor(config: 'Config') -> Descriptor:
    '''Config-selectable descriptor. 'feature' reads stored b(x); else StaticDescriptor.'''
    if getattr(config, 'descriptor_kind', 'static') == 'feature':
        return StoredDescriptor()
    return StaticDescriptor()


def coverage_stats(vectors: Sequence[Vector], bins: int = 5) -> dict:
    '''Descriptor-space coverage/entropy over a coarse grid (shadow diagnostics only).

    Returns occupied-cell count, Shannon entropy of cell occupancy (bits and a
    0..1 normalized form), and per-dimension spread. Pure read-only telemetry.
    '''
    clean = [tuple(float(x) for x in v) for v in vectors if v]
    n = len(clean)
    if n == 0:
        return {
            'n': 0, 'dims': 0, 'cells_occupied': 0, 'grid_cells': 0,
            'entropy_bits': 0.0, 'entropy_norm': 0.0, 'per_dim_std': [],
        }
    dims = max(len(v) for v in clean)
    cols = [[v[i] for v in clean if i < len(v)] for i in range(dims)]
    bounds = [(min(col), max(col)) for col in cols]

    def cell(vec: Vector) -> tuple[int, ...]:
        idx = []
        for i, (lo, hi) in enumerate(bounds):
            x = vec[i] if i < len(vec) else lo
            span = (hi - lo) or 1.0
            b = int((x - lo) / span * bins)
            idx.append(max(0, min(bins - 1, b)))
        return tuple(idx)

    counts: dict[tuple[int, ...], int] = {}
    for vec in clean:
        key = cell(vec)
        counts[key] = counts.get(key, 0) + 1
    occupied = len(counts)
    probs = [c / n for c in counts.values()]
    entropy = -sum(p * math.log2(p) for p in probs) if probs else 0.0
    max_entropy = math.log2(occupied) if occupied > 1 else 0.0
    per_dim_std = []
    for col in cols:
        mean = sum(col) / len(col)
        var = sum((x - mean) ** 2 for x in col) / len(col)
        per_dim_std.append(math.sqrt(var))
    return {
        'n': n, 'dims': dims, 'cells_occupied': occupied,
        'grid_cells': bins ** dims if dims else 0,
        'entropy_bits': entropy,
        'entropy_norm': (entropy / max_entropy) if max_entropy else 0.0,
        'per_dim_std': per_dim_std,
    }


def load_select_policy(path: Path) -> dict[str, float]:
    '''Read a ModifiableSelector policy from select_policy.json ({} when absent).'''
    data = read_json(path, default={}) or {}
    out: dict[str, float] = {}
    for key, value in data.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def save_select_policy(path: Path, policy: dict[str, float]) -> None:
    '''Persist a ModifiableSelector policy atomically (meta self-modification target).'''
    atomic_write_json(path, {str(k): float(v) for k, v in policy.items()})


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
