'''Append-only candidate archive (runtime store, OUTSIDE the repo).

Three statuses (plan mechanical contract 4):
  invalid               -> failed build/test/eval/protection, empty diff, crash
  valid_stepping_stone  -> builds + evaluates, may be worse, SELECTABLE
  official_best         -> passed the locked holdout keep rule, advanced best_commit

A `valid_stepping_stone` never advances best_commit; an `official_best` is never
chosen by search_alpha alone. Records are append-only and never deleted: the live
view is `archive.json` (atomic full rewrite) and the immutable log is `history.jsonl`.
'''
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

from .config import Paths
from .util import append_jsonl, atomic_write_json, atomic_write_text, read_json

INVALID = 'invalid'
STEPPING_STONE = 'valid_stepping_stone'
OFFICIAL_BEST = 'official_best'
VALID_STATUSES = (STEPPING_STONE, OFFICIAL_BEST)


@dataclass
class Candidate:
    '''One archive record (the `meta.json` schema).'''

    id: str
    parent_id: str | None
    base_commit: str
    round: int
    status: str
    created_by: str
    schema_version: int = 1
    search_alpha: float | None = None
    holdout_alpha: float | None = None
    selection_alpha: float | None = None
    search_score: float | None = None
    point_rate_b4: float | None = None
    lower_ci: float | None = None
    complexity: int | None = None
    n_children: int = 0
    children_invalid_count: int = 0
    eval_bank: str | None = None
    score_kind: str | None = None
    tokens: int = 0
    eval_seconds: float = 0.0
    reason: str = ''

    @property
    def is_valid(self) -> bool:
        return self.status in VALID_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Candidate':
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class UsageRecord:
    '''Mutable lifecycle sidecar (kept out of the immutable meta.json).'''

    pinned: bool = False
    state: str = 'active'
    selection_count: int = 0
    last_selected: int = -1
    last_improvement: int = -1


class Store:
    '''Owns all candidate persistence under run_dir. The agent never writes here.'''

    def __init__(self, paths: Paths, schema_version: int = 1) -> None:
        self.paths = paths
        self.schema_version = schema_version
        self._candidates: dict[str, Candidate] = {}
        self._order: list[str] = []
        self._usage: dict[str, UsageRecord] = {}
        self._load()

    def _load(self) -> None:
        for meta in read_json(self.paths.archive_json, default=[]) or []:
            cand = Candidate.from_dict(meta)
            self._candidates[cand.id] = cand
            self._order.append(cand.id)
        usage = read_json(self.paths.usage_json, default={}) or {}
        for cid, rec in usage.items():
            self._usage[cid] = UsageRecord(**rec)

    def next_id(self) -> str:
        return f'candidate_{len(self._order):04d}'

    def get(self, cid: str) -> Candidate | None:
        return self._candidates.get(cid)

    def all(self) -> list[Candidate]:
        return [self._candidates[cid] for cid in self._order]

    def parents_pool(self) -> list[Candidate]:
        '''Valid, selectable candidates (active or pinned, never archived).'''
        pool = []
        for cid in self._order:
            cand = self._candidates[cid]
            usage = self._usage.get(cid, UsageRecord())
            if cand.is_valid and (usage.state != 'archived' or usage.pinned):
                pool.append(cand)
        return pool

    def usage(self, cid: str) -> UsageRecord:
        return self._usage.setdefault(cid, UsageRecord())

    def _scores_payload(self, cand: Candidate) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'candidate_id': cand.id,
            'parent_id': cand.parent_id,
            'eval_bank': cand.eval_bank,
            'score_kind': cand.score_kind,
            'created_by': 'harness',
            'search_alpha': cand.search_alpha,
            'holdout_alpha': cand.holdout_alpha,
            'selection_alpha': cand.selection_alpha,
            'search_score': cand.search_score,
            'point_rate_b4': cand.point_rate_b4,
            'lower_ci': cand.lower_ci,
        }

    def _write_candidate_dir(self, cand: Candidate, patch: str, snapshot: str) -> None:
        cdir = self.paths.candidates_dir / cand.id
        cdir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(cdir / 'model_patch.diff', patch)
        atomic_write_text(cdir / 'snapshot.cpp', snapshot)
        atomic_write_json(cdir / 'meta.json', cand.to_dict())
        atomic_write_json(cdir / 'scores.json', self._scores_payload(cand))

    def _flush_archive(self) -> None:
        atomic_write_json(self.paths.archive_json, [self._candidates[c].to_dict() for c in self._order])

    def _flush_usage(self) -> None:
        atomic_write_json(self.paths.usage_json, {cid: asdict(rec) for cid, rec in self._usage.items()})

    def add(self, cand: Candidate, patch: str = '', snapshot: str = '') -> Candidate:
        '''Persist a candidate (any status). Never deletes or overwrites prior records.'''
        cand.schema_version = self.schema_version
        self._candidates[cand.id] = cand
        if cand.id not in self._order:
            self._order.append(cand.id)
        self._usage.setdefault(cand.id, UsageRecord())

        parent = self._candidates.get(cand.parent_id) if cand.parent_id else None
        if parent is not None:
            if cand.status == INVALID:
                parent.children_invalid_count += 1
            else:
                parent.n_children += 1
            # Only the parent's meta.json counter changes; its snapshot/patch are untouched.
            parent_meta = self.paths.candidates_dir / parent.id / 'meta.json'
            if parent_meta.parent.exists():
                atomic_write_json(parent_meta, parent.to_dict())

        self._write_candidate_dir(cand, patch, snapshot)
        self._flush_archive()
        self._flush_usage()
        append_jsonl(self.paths.history_jsonl, {'event': 'add', **cand.to_dict()})
        return cand

    def pin_lineage(self, cid: str, round_idx: int) -> None:
        '''Pin a candidate and its ancestors (exempt from archive transitions).'''
        node: str | None = cid
        seen: set[str] = set()
        while node and node in self._candidates and node not in seen:
            seen.add(node)
            usage = self.usage(node)
            usage.pinned = True
            usage.state = 'active'
            usage.last_improvement = round_idx
            node = self._candidates[node].parent_id
        self._flush_usage()

    def mark_selected(self, cid: str, round_idx: int) -> None:
        usage = self.usage(cid)
        usage.selection_count += 1
        usage.last_selected = round_idx
        self._flush_usage()

    def archive_stale(self, round_idx: int, min_idle_rounds: int = 8) -> int:
        '''Move dead records (unpinned, valid, 0 children, long idle) to state=archived.

        Conservative and reversible: archived records are NEVER deleted and remain
        restorable; pinned lineages and official bests are exempt. Returns the count moved.
        '''
        moved = 0
        for cid, cand in self._candidates.items():
            usage = self.usage(cid)
            if usage.pinned or usage.state != 'active':
                continue
            if cand.status != STEPPING_STONE:
                continue
            idle = round_idx - max(usage.last_selected, cand.round)
            if cand.n_children == 0 and idle >= min_idle_rounds:
                usage.state = 'archived'
                moved += 1
        if moved:
            self._flush_usage()
        return moved

    def snapshot_text(self, cid: str) -> str:
        '''Read the stored strategy snapshot for a candidate.'''
        path = self.paths.candidates_dir / cid / 'snapshot.cpp'
        return path.read_text(encoding='utf-8') if path.exists() else ''

    def regenerate_results(self) -> None:
        '''Rewrite the canonical results.tsv view in run_dir (git-safe) atomically.

        The harness never overwrites the repo's own tracked results.tsv (the human
        experiment log); its authoritative view lives beside the archive in run_dir.
        '''
        header = 'commit\topponent\tpoint_rate\tsearch_score\tlower_ci\tgames\tcomplexity\tstatus\tdescription'
        lines = [header]
        for cid in self._order:
            cand = self._candidates[cid]
            lines.append(
                '\t'.join([
                    cand.id,
                    'B4',
                    f'{(cand.point_rate_b4 or 0.0):.5f}',
                    f'{(cand.search_score or 0.0):.5f}',
                    f'{(cand.lower_ci or 0.0):.5f}',
                    '0',
                    str(cand.complexity if cand.complexity is not None else ''),
                    cand.status,
                    cand.reason.replace('\t', ' ').replace('\n', ' '),
                ])
            )
        text = '\n'.join(lines) + '\n'
        atomic_write_text(self.paths.results_tsv, text)
