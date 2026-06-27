'''Meta-layer (Phase 2, default OFF): self-modification, evidence convergence, attribution.

Three independent, opt-in pieces, all still harness-governed:
  - ConvergencePolicy: harness-owned early stop GATED behind a min_rounds floor. The
    agent still cannot stop; this only lets the *harness* end a run early once it has
    cleared the floor AND seen no holdout-confirmed gain for `patience` rounds.
  - MetaController: every M rounds a bounded meta-session may edit the mechanism layer
    (evolve/mechanism/**) only; the strategy and everything else is reset. Mirrors the
    inner allowlist contract one level up.
  - Attribution: ties each meta edit to the best-score delta that followed it.
'''
from __future__ import annotations

from typing import Any

from .agents import COMPLETED, Agent, AgentContext
from .config import Config
from .protect import VersionControl
from .util import append_jsonl, log

META_ALLOWLIST = ('evolve/mechanism',)


class ConvergencePolicy:
    '''Evidence-based early stop, never firing before the min_rounds floor.'''

    def __init__(self, enabled: bool, min_rounds: int, patience: int) -> None:
        self.enabled = enabled
        self.min_rounds = min_rounds
        self.patience = patience

    def reason(self, state: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        round_idx = int(state.get('round', 0))
        if round_idx < self.min_rounds:
            return None  # floor: cannot converge early
        last_official = int(state.get('last_official_round', 0))
        if round_idx - last_official >= self.patience:
            return (f'evidence convergence: no holdout-confirmed gain in {self.patience} '
                    f'rounds (min_rounds={self.min_rounds} floor cleared)')
        return None


class Attribution:
    '''Append-only ledger tying meta edits to the best-score delta that follows them.'''

    def __init__(self, path) -> None:
        self.path = path
        self._pending: list[dict[str, Any]] = []

    def record_edit(self, round_idx: int, summary: str, best_before: float) -> None:
        rec = {'event': 'meta_edit', 'round': round_idx, 'summary': summary,
               'best_before': best_before}
        self._pending.append(rec)
        append_jsonl(self.path, rec)

    def record_round(self, round_idx: int, best_search: float) -> None:
        '''Close out the most recent meta edit with the realized best-score delta.'''
        for rec in self._pending:
            if 'best_after' not in rec:
                rec['best_after'] = best_search
                rec['delta'] = best_search - float(rec.get('best_before') or 0.0)
                append_jsonl(self.path, {**rec, 'event': 'meta_outcome', 'round': round_idx})
                break


class MetaController:
    '''Runs bounded meta-sessions that may edit only the mechanism layer.'''

    def __init__(self, config: Config, agent: Agent, attribution: Attribution) -> None:
        self.config = config
        self.agent = agent
        self.attribution = attribution
        self.every = config.meta_every
        self.target_rel = config.meta_target

    def due(self, round_idx: int) -> bool:
        return self.every > 0 and round_idx > 0 and round_idx % self.every == 0

    def run(self, round_idx: int, phi: str, best_commit: str, best_before: float) -> str:
        '''Attempt one mechanism self-modification; return the (possibly new) best commit.'''
        vc = VersionControl(self.config.repo_root, META_ALLOWLIST)
        final_commit = best_commit
        try:
            ctx = AgentContext(
                repo_root=self.config.repo_root,
                strategy_rel=self.target_rel,
                prompt=self._prompt(phi),
                phi=phi,
                round_idx=round_idx,
                parent_id=None,
            )
            result = self.agent.run(ctx)
            if result.status == COMPLETED:
                vc.reset_all_but_allowlist(best_commit)  # discard any strategy edits
                patch = vc.diff_allowlist(best_commit)
                if patch.strip():
                    final_commit = vc.commit_inline(f'meta: round {round_idx} self-modification')
                    self.attribution.record_edit(round_idx, result.summary or 'meta edit', best_before)
                    log(f'  META edited mechanism -> {final_commit[:10]}')
        except Exception as exc:  # noqa: BLE001 - a meta failure must never end the run
            log(f'WARN meta round failed: {exc!r}')
        finally:
            try:
                vc.reset_to_base(final_commit)
            except Exception as exc:  # noqa: BLE001
                log(f'WARN meta reset failed: {exc!r}')
        return final_commit

    def _prompt(self, phi: str) -> str:
        meta_skill = self.config.paths.mechanism_dir / 'meta_skill.md'
        contract = meta_skill.read_text(encoding='utf-8') if meta_skill.exists() else (
            'You may edit ONLY the mechanism layer to improve how the inner agent searches. '
            'You cannot change the evaluator, metric, or thresholds.'
        )
        return f'{contract}\n\n---\n# Current state (Phi)\n\n{phi}\n'
