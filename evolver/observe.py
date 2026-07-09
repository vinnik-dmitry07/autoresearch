'''Observation + durable memory.

Produces a compact, BOUNDED Phi per round (the only cross-round context the agent
sees - never the full archive). Memory is append-only; key state is flushed before
any summarization could discard it (flush-before-loss).
'''
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .population import coverage_stats
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


def load_family_map(config: Config, limit_chars: int = 2000) -> str:
    '''Read family_map.md (mechanism dir, then repo root); '' when absent.

    Meta-only knowledge: callers MUST gate this behind meta being enabled so the
    Phase-1 baseline prompt never depends on it (plan: dormant until meta is on).
    '''
    for path in (config.paths.mechanism_dir / 'family_map.md', config.repo_root / 'family_map.md'):
        if path.exists():
            return path.read_text(encoding='utf-8').strip()[:limit_chars]
    return ''


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
        if self.config.meta_every > 0 and not self.config.meta_strict_self_contained:
            # family_map.md is surfaced ONLY when the meta layer is active, so the
            # Phase-1 baseline Phi stays byte-identical regardless of the file.
            # Strict self-contained meta (A8s) embeds taxonomy in evolve_skill.md instead.
            family_map = load_family_map(self.config)
            if family_map:
                head = family_map.splitlines()[:6]
                lines += ['', 'HEURISTIC FAMILIES (family_map.md; meta active):', *[f'  {ln}' for ln in head]]
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

    def record_descriptor_coverage(self, store: Store, state: dict[str, Any]) -> None:
        '''Shadow telemetry: descriptor-space coverage/entropy over valid candidates.

        Appends one line to descriptor_coverage.jsonl and writes a small markdown
        snapshot beside the round observation. Deliberately does NOT touch the
        agent-facing Phi, so selection and the prompt stay identical to the baseline.
        '''
        vectors = [tuple(c.b_descriptor) for c in store.all() if c.is_valid and c.b_descriptor]
        if len(vectors) < 2:
            return
        round_idx = state.get('round', 0)
        stats = coverage_stats(vectors)
        append_jsonl(self.paths.run_dir / 'descriptor_coverage.jsonl', {'round': round_idx, **stats})
        per_dim = ', '.join(f'{s:.3f}' for s in stats['per_dim_std'])
        snapshot = (
            f'# Descriptor coverage round {round_idx}\n\n'
            f'valid_with_b={stats["n"]}  dims={stats["dims"]}  '
            f'cells_occupied={stats["cells_occupied"]}/{stats["grid_cells"]}\n'
            f'entropy={stats["entropy_bits"]:.3f} bits (norm={stats["entropy_norm"]:.3f})\n'
            f'per_dim_std=[{per_dim}]\n'
        )
        atomic_write_text(self.paths.observations_dir / f'round_{round_idx:03d}_descriptor.md', snapshot)

    def append_cost(self, record: dict[str, Any]) -> None:
        append_jsonl(self.paths.cost_jsonl, record)
