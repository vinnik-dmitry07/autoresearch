'''Parent selection over the flat archive.

Selectors read `selection_alpha` (holdout-confirmed when available, else a penalized
search score) and never write scores. P0 default = random over valid; P1 default =
score_child_prop (HyperAgents handcrafted winner), down-weighted by failed children.
'''
from __future__ import annotations

import math
import random
from typing import Protocol

from .population import novelty_scores
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

    def _weights(self, pool: list[Candidate]) -> list[float]:
        alphas = sorted((_alpha(c) for c in pool), reverse=True)
        top = alphas[: self.topk] if alphas else [0.0]
        mid = sum(top) / len(top)
        weights = []
        for cand in pool:
            s = sigmoid(self.scale * (_alpha(cand) - mid))
            h = 1.0 / (1.0 + cand.n_children)
            penalty = 1.0 / (1.0 + cand.children_invalid_count)
            weights.append(max(s * h * penalty, 1e-9))
        return weights

    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        if not pool:
            return []
        return rng.choices(pool, weights=self._weights(pool), k=k)


class ScoreChildPropNoveltySelector(ScoreChildPropSelector):
    '''A2 gridless novelty: score_child_prop weight x (1 + lambda * norm_novelty(b(x))).

    Novelty is the mean k-NN distance in behavioral-descriptor space, normalized to
    [0, 1] across the pool so the multiplier lands in [1, 1 + lambda] -- a gentle
    de-collapse pressure that never overrides quality (per the A2 plan). Only candidates
    carrying a real stored b(x) contribute (consistent dims); the rest get novelty 0
    (multiplier 1), so the seed and any b-less rows stay neutral. lambda <= 0 reduces
    to plain score_child_prop, byte-identical to the baseline.
    '''

    name = 'score_child_prop+novelty'

    def __init__(
        self, novelty_lambda: float, scale: float = 10.0, topk: int = 3, k_nn: int = 3,
    ) -> None:
        super().__init__(scale=scale, topk=topk)
        self.novelty_lambda = max(0.0, float(novelty_lambda))
        self.k_nn = max(1, int(k_nn))

    def _novelty_factor(self, pool: list[Candidate]) -> list[float]:
        factor = [1.0] * len(pool)
        if self.novelty_lambda <= 0.0:
            return factor
        real = [(i, c.b_descriptor) for i, c in enumerate(pool)
                if getattr(c, 'b_descriptor', None)]
        if len(real) < 2:
            return factor
        vectors = [tuple(float(x) for x in bd) for _, bd in real]
        nov = novelty_scores(vectors, self.k_nn)
        peak = max(nov) if nov else 0.0
        if peak <= 0.0:
            return factor
        for (i, _), n in zip(real, nov):
            factor[i] = 1.0 + self.novelty_lambda * (n / peak)
        return factor

    def select(self, pool: list[Candidate], k: int, rng: random.Random) -> list[Candidate]:
        if not pool:
            return []
        base = self._weights(pool)
        factor = self._novelty_factor(pool)
        weights = [max(b * f, 1e-9) for b, f in zip(base, factor)]
        return rng.choices(pool, weights=weights, k=k)


def make_selector(
    name: str, scale: float = 10.0, topk: int = 3,
    novelty_lambda: float = 0.0, novelty_k: int = 3,
) -> Selector:
    if name == 'score_child_prop':
        if novelty_lambda and novelty_lambda > 0.0:
            return ScoreChildPropNoveltySelector(
                novelty_lambda=novelty_lambda, scale=scale, topk=topk, k_nn=novelty_k,
            )
        return ScoreChildPropSelector(scale=scale, topk=topk)
    if name == 'random':
        return RandomSelector()
    raise ValueError(f'unknown selector: {name!r}')
