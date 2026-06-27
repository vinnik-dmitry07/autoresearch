'''Curator (Phase 2): archive hygiene that SUGGESTS, never destroys (Hermes lesson).

The curator proposes lifecycle actions (archive stale, pin best lineages, consolidate
memory). Applying is restricted to NON-destructive, reversible actions and is provenance-
gated: it will only touch records whose `created_by` is a known harness source. It can
NEVER delete official history. An optional LLM review pass is suggest-only too.
'''
from __future__ import annotations

from dataclasses import dataclass

from .config import Paths
from .store import OFFICIAL_BEST, STEPPING_STONE, Store
from .util import append_jsonl, log

KNOWN_SOURCES = {'harness', 'sweep', 'meta'}


@dataclass
class Suggestion:
    kind: str
    target: str | None
    reason: str
    destructive: bool = False  # ALWAYS False; the curator never deletes.


class Curator:
    '''Deterministic, reversible archive hygiene + optional suggest-only LLM hook.'''

    def __init__(self, paths: Paths, min_idle_rounds: int = 8) -> None:
        self.paths = paths
        self.min_idle_rounds = min_idle_rounds

    def suggest(self, store: Store, round_idx: int) -> list[Suggestion]:
        out: list[Suggestion] = []
        for cand in store.all():
            usage = store.usage(cand.id)
            if cand.status == OFFICIAL_BEST and not usage.pinned:
                out.append(Suggestion('pin_lineage', cand.id, 'best lineage is unpinned'))
            if cand.status == STEPPING_STONE and not usage.pinned and usage.state == 'active':
                idle = round_idx - max(usage.last_selected, cand.round)
                if cand.n_children == 0 and idle >= self.min_idle_rounds:
                    out.append(Suggestion('archive_stale', cand.id, f'idle {idle} rounds, 0 children'))
        return out

    def apply_safe(self, store: Store, suggestions: list[Suggestion], round_idx: int) -> int:
        '''Apply ONLY non-destructive, provenance-gated suggestions. Returns count applied.'''
        applied = 0
        for s in suggestions:
            if s.destructive:
                continue  # never delete
            cand = store.get(s.target) if s.target else None
            if cand is not None and cand.created_by not in KNOWN_SOURCES:
                continue  # provenance gate
            if s.kind == 'pin_lineage' and s.target:
                store.pin_lineage(s.target, round_idx)
                applied += 1
            elif s.kind == 'archive_stale' and s.target:
                usage = store.usage(s.target)
                if not usage.pinned:
                    usage.state = 'archived'  # reversible; record is kept forever
                    store._flush_usage()  # noqa: SLF001 - intentional internal flush
                    applied += 1
        if applied:
            append_jsonl(self.paths.run_dir / 'curator.jsonl',
                         {'round': round_idx, 'applied': applied,
                          'suggestions': [s.__dict__ for s in suggestions]})
        return applied

    def write_llm_review_prompt(self, store: Store, round_idx: int) -> str:
        '''Build a suggest-only review prompt (an LLM client would answer; we never auto-delete).'''
        lines = [
            'You are an archive curator. Suggest ONLY reversible hygiene actions',
            '(pin_lineage / archive_stale). You may NOT delete any record or official score.',
            '',
            f'Round {round_idx}. Records:',
        ]
        for cand in store.all()[-50:]:
            u = store.usage(cand.id)
            lines.append(f'  {cand.id} {cand.status} alpha={cand.selection_alpha} '
                         f'children={cand.n_children} state={u.state} pinned={u.pinned}')
        prompt = '\n'.join(lines)
        (self.paths.run_dir / f'curator_prompt_{round_idx:03d}.md').write_text(prompt, encoding='utf-8')
        return prompt
