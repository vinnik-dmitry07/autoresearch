'''Observation + durable memory.

Produces a compact, BOUNDED Phi per round (the only cross-round context the agent
sees - never the full archive). Memory is append-only; key state is flushed before
any summarization could discard it (flush-before-loss).
'''
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .store import OFFICIAL_BEST, Store
from .util import append_jsonl, atomic_write_text

PHI_MAX_CHARS = 4000
REJECTED_MAX = 12


def load_rejected_directions(repo_root: Path, limit: int = REJECTED_MAX) -> list[str]:
    '''Extract bullet lines from program.md's `## Rejected directions` section.

    Read-only: program.md is locked. Surfacing dead-ends in Phi stops the agent from
    re-proposing closed families (closes "stale ideas resurfacing").
    '''
    program = repo_root / 'program.md'
    if not program.exists():
        return []
    lines = program.read_text(encoding='utf-8').splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith('## ') and 'rejected directions' in stripped.lower():
            capturing = True
            continue
        if capturing:
            if stripped.startswith('## '):
                break
            if stripped[:1] in {'-', '*'} or stripped[:2].rstrip().isdigit():
                out.append(stripped.lstrip('-*0123456789. ').strip())
            if len(out) >= limit:
                break
    return [item for item in out if item]


class Observer:
    '''Builds Phi and maintains durable memory under run_dir.'''

    def __init__(self, config: Config) -> None:
        self.config = config
        self.paths = config.paths
        self._rejected: list[str] | None = None

    def _rejected_directions(self) -> list[str]:
        if self._rejected is None:
            self._rejected = load_rejected_directions(self.config.repo_root)
        return self._rejected

    def summarize(self, store: Store, state: dict[str, Any]) -> str:
        '''Return a compact, BOUNDED Phi and persist it to observations/round_NNN.md.'''
        cands = store.all()
        valid = [c for c in cands if c.is_valid]
        bests = [c for c in cands if c.status == OFFICIAL_BEST]
        best_search = state.get('best_search', self.config.best_search)
        best_b4 = state.get('best_b4', self.config.best_b4)
        plateau = state.get('plateau', 0)
        round_idx = state.get('round', 0)

        curve = [f'{c.search_score:.5f}' for c in bests if c.search_score is not None][-6:]
        recent = cands[-2 * self.config.k:] if cands else []
        recent_lines = [
            f'  - {c.id} {c.status} search_alpha={c.search_alpha} parent={c.parent_id} :: {c.reason[:80]}'
            for c in recent
        ]
        rejected = self._rejected_directions()
        rejected_lines = [f'  - {item[:110]}' for item in rejected]
        lines = [
            f'# Phi round {round_idx + 1}/{self.config.max_rounds}',
            '',
            f'best_search={best_search:.5f}  best_b4={best_b4:.5f}  best_id={state.get("best_id")}  plateau_rounds={plateau}',
            f'best curve (official_best search): {" -> ".join(curve) if curve else "(baseline only)"}',
            f'archive: total={len(cands)} valid={len(valid)} official_best={len(bests)}',
            f'budget: round={round_idx}/{self.config.max_rounds} cost={state.get("cost_usd", 0.0):.4f}/{self.config.cost_cap_usd}',
            f'keep rule (locked): search_full >= best+{self.config.search_delta} AND lower_ci >= best_lower_ci',
            '',
            'recent candidates:',
            *recent_lines,
        ]
        if rejected_lines:
            lines += ['', 'KNOWN DEAD-ENDS (do not re-propose; from program.md):', *rejected_lines]
        lines += [
            '',
            'CONTRACT: while budget remains you do not exit. If stuck, name the structural',
            'reason and submit from a different family. You cannot stop the run or score it.',
        ]
        if plateau >= 3:
            lines += [
                '',
                'DE-ANCHOR (plateau): drop the stale scalar; steer by behavioral difference;',
                'submit from a DIFFERENT heuristic family than the last attempts.',
            ]
        phi = '\n'.join(lines)
        if len(phi) > PHI_MAX_CHARS:
            phi = phi[:PHI_MAX_CHARS] + '\n... [truncated]'

        out = self.paths.observations_dir / f'round_{round_idx + 1:03d}.md'
        atomic_write_text(out, phi + '\n')
        return phi

    def flush_memory(self, state: dict[str, Any], note: str) -> None:
        '''Append a durable, never-rewritten memory line (flush-before-loss).

        Lives in run_dir (OUTSIDE the repo) so git reset/clean cannot delete it; the
        tracked evolve/mechanism/ holds only the skill input, not this growing log.
        '''
        path = self.paths.run_dir / 'memory.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        line = (
            f'- round {state.get("round", 0)}: best_search={state.get("best_search", 0.0):.5f} '
            f'best_id={state.get("best_id")} plateau={state.get("plateau", 0)} :: {note}\n'
        )
        with path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(line)

    def append_cost(self, record: dict[str, Any]) -> None:
        append_jsonl(self.paths.cost_jsonl, record)
