'''Parent selection over the flat archive.

Selectors read `selection_alpha` (holdout-confirmed when available, else a penalized
search score) and never write scores. P0 default = random over valid; P1 default =
score_child_prop (HyperAgents handcrafted winner), down-weighted by failed children.
'''
from __future__ import annotations

import math
import random
from typing import Protocol

from .store import Candidate


def sigmoid(x: float) -> float:
    if x < -60.0:
        return 0.0
    if x > 60.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _alpha(cand: Candidate) -> float:
    if cand.selection_alpha is not None:
        return cand.selection_alpha
    if cand.search_alpha is not None:
        return cand.search_alpha
    return 0.0


class Selector(Protocol):
    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        ...


class RandomSelector:
    '''Uniform sampling over valid candidates (ablation baseline / Phase-0 default).'''

    name = 'random'

    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        if not pool:
            return []
        return [rng.choice(pool) for _ in range(k)]


class ScoreChildPropSelector:
    '''p_i proportional to sigmoid(scale*(alpha_i - mean_topk)) / (1+n_children) / (1+invalid).'''

    name = 'score_child_prop'

    def __init__(self, scale: float = 10.0, topk: int = 3) -> None:
        self.scale = scale
        self.topk = max(1, topk)

    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        if not pool:
            return []
        alphas = sorted((_alpha(c) for c in pool), reverse=True)
        top = alphas[: self.topk] if alphas else [0.0]
        mid = sum(top) / len(top)
        weights = []
        for cand in pool:
            s = sigmoid(self.scale * (_alpha(cand) - mid))
            h = 1.0 / (1.0 + cand.n_children)
            penalty = 1.0 / (1.0 + cand.children_invalid_count)
            weights.append(max(s * h * penalty, 1e-9))
        return rng.choices(pool, weights=weights, k=k)


def make_selector(name: str, scale: float = 10.0, topk: int = 3) -> Selector:
    if name == 'score_child_prop':
        return ScoreChildPropSelector(scale=scale, topk=topk)
    if name == 'random':
        return RandomSelector()
    raise ValueError(f'unknown selector: {name!r}')
