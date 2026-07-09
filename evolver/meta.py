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

import re
import time
from typing import Any

from .agents import COMPLETED, ERROR, TURN_LIMIT, Agent, AgentContext, AgentResult
from .config import Config
from .leak_gate import gate_scan
from .meta_delivery import (
    collect_post_agent_diagnostics,
    empty_patch_detail,
    file_sha256,
    log_post_agent_diagnostics,
    record_meta_round,
    scan_meta_tools_audit,
)
from .observe import load_family_map
from .protect import VersionControl
from .util import log
from .usage_limit import (
    session_limit_message,
    wait_for_usage_reset,
)

META_ALLOWLIST = ('evolve/mechanism',)

_DIFF_PATH_RE = re.compile(r'^diff --git a/(\S+)', re.MULTILINE)


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
        from .util import append_jsonl
        append_jsonl(self.path, rec)

    def record_round(self, round_idx: int, best_search: float) -> None:
        '''Close out the most recent meta edit with the realized best-score delta.'''
        from .util import append_jsonl
        for rec in self._pending:
            if 'best_after' not in rec:
                rec['best_after'] = best_search
                rec['delta'] = best_search - float(rec.get('best_before') or 0.0)
                append_jsonl(self.path, {**rec, 'event': 'meta_outcome', 'round': round_idx})
                break


def _meta_diff_in_scope(full_diff: str) -> bool:
    '''True when every changed path in full_diff stays under META_ALLOWLIST.'''
    if not full_diff.strip():
        return True
    for match in _DIFF_PATH_RE.finditer(full_diff):
        path = match.group(1).strip()
        if not any(path == prefix or path.startswith(prefix + '/') for prefix in META_ALLOWLIST):
            return False
    return True


class MetaController:
    '''Runs bounded meta-sessions that may edit only the mechanism layer.'''

    def __init__(self, config: Config, agent: Agent, attribution: Attribution) -> None:
        self.config = config
        self.agent = agent
        self.attribution = attribution
        self.every = config.meta_every
        self.target_rel = config.meta_target
        self._quota_exhausted = False

    @property
    def quota_exhausted(self) -> bool:
        return self._quota_exhausted

    def due(self, round_idx: int) -> bool:
        return self.every > 0 and round_idx > 0 and round_idx % self.every == 0

    def run(
        self, round_idx: int, phi: str, best_commit: str, best_before: float,
    ) -> tuple[str, AgentResult | None]:
        '''Attempt one mechanism self-modification; return (commit, result).'''
        if self._quota_exhausted:
            log(f'  META unavailable at round {round_idx}: session quota exhausted')
            self._record(round_idx, best_commit, best_before, None, 'skipped_quota', {})
            return best_commit, None

        vc = VersionControl(self.config.repo_root, META_ALLOWLIST)
        final_commit = best_commit
        result: AgentResult | None = None
        target = self.config.repo_root / self.target_rel
        hash_before = file_sha256(target)
        outcome = 'error'

        try:
            ctx = AgentContext(
                repo_root=self.config.repo_root,
                strategy_rel=self.target_rel,
                prompt=self._prompt(phi),
                phi=phi,
                round_idx=round_idx,
                parent_id=None,
                run_dir=self.config.paths.run_dir,
            )
            session_ts = time.time()
            while True:
                result = self.agent.run(ctx)
                if result.status == TURN_LIMIT:
                    log(f'  META turn limit at round {round_idx}: {result.error}')
                    self._record(round_idx, best_commit, best_before, result, 'turn_limit', {})
                    return final_commit, result
                if result.status != COMPLETED:
                    limit_msg = session_limit_message(
                        result.error, result.summary, result.agent_stdout,
                    )
                    if limit_msg:
                        log(f'  META session limit at round {round_idx}: {limit_msg}')
                        wait_for_usage_reset(
                            error=limit_msg, usage_reset_at=result.usage_reset_at,
                        )
                        continue
                    log(f'  META session {result.status} at round {round_idx}: {result.error}')
                    self._record(
                        round_idx, best_commit, best_before, result, result.status,
                        {'meta_invocation': result.meta_invocation} if result.meta_invocation else {},
                    )
                    return final_commit, result
                break

            diag = collect_post_agent_diagnostics(
                vc, self.config.repo_root, best_commit, self.target_rel,
                hash_before=hash_before, status=result.status,
            )
            log_post_agent_diagnostics(round_idx, diag)

            tool_violations = list(result.scope_violations)
            audit_path = (
                (self.config.paths.run_dir / 'meta_tools.jsonl')
                if self.config.paths.run_dir else None
            )
            scope_scan = None
            if audit_path is not None:
                scope_scan = scan_meta_tools_audit(
                    audit_path,
                    self.config.repo_root,
                    since_ts=session_ts,
                    target_rel=self.target_rel,
                    strict_meta=True,
                )
                for hit in scope_scan.messages:
                    if hit not in tool_violations:
                        tool_violations.append(hit)
            if tool_violations:
                scope_outcome = 'scope_violation'
                if scope_scan is not None and scope_scan.violations:
                    scanned = scope_scan.outcome()
                    if scanned:
                        scope_outcome = scanned
                timing = 'unknown'
                if scope_scan is not None and scope_scan.violations:
                    before = any(not v.after_edit for v in scope_scan.violations)
                    after = any(v.after_edit for v in scope_scan.violations)
                    if before and after:
                        timing = 'before_and_after_edit'
                    elif after:
                        timing = 'after_edit'
                    else:
                        timing = 'before_edit'
                log(f'  META scope violation at round {round_idx} ({timing}): '
                    f'{tool_violations[0]}')
                self._record(
                    round_idx, best_commit, best_before, result, scope_outcome,
                    {
                        **diag,
                        'scope_violations': tool_violations,
                        'scope_violation_timing': timing,
                    },
                )
                vc.reset_all_but_allowlist(best_commit)
                return final_commit, result

            if not diag['root_identity_ok']:
                log(f'  META root mismatch at round {round_idx}: '
                    f'expected={diag["cwd_expected"]} toplevel={diag["git_toplevel"]}')
                self._record(
                    round_idx, best_commit, best_before, result, 'root_mismatch', diag,
                )
                vc.reset_all_but_allowlist(best_commit)
                return final_commit, result

            full_diff = vc.diff_versus_commit(best_commit)
            if not _meta_diff_in_scope(full_diff):
                log(f'  META scope violation at round {round_idx}: diff outside mechanism')
                self._record(
                    round_idx, best_commit, best_before, result, 'diff_scope_violation', diag,
                )
                vc.reset_all_but_allowlist(best_commit)
                return final_commit, result

            vc.reset_all_but_allowlist(best_commit)
            mechanism_text = vc.read_repo_file(self.target_rel) if target.exists() else ''
            stdout = result.agent_stdout or ''
            leak_hits = list(result.leak_hits) or gate_scan(stdout, mechanism_text)
            if leak_hits:
                log(f'  META leak gate round {round_idx}: {leak_hits[0]}')
                self._record(
                    round_idx, best_commit, best_before, result, 'leak_gate',
                    {**diag, 'leak_hits': leak_hits},
                )
                return final_commit, result

            patch = vc.diff_allowlist(best_commit)
            diag['allowlist_diff_len'] = len(patch.strip())
            if patch.strip():
                final_commit = vc.commit_inline(f'meta: round {round_idx} self-modification')
                self.attribution.record_edit(round_idx, result.summary or 'meta edit', best_before)
                outcome = 'committed'
                log(f'  META edited mechanism -> {final_commit[:10]}')
            else:
                outcome = 'empty_patch'
                detail = empty_patch_detail(diag)
                log(f'  META skip round {round_idx}: empty mechanism diff after COMPLETED '
                    f'({detail})')
            self._record(round_idx, best_commit, best_before, result, outcome, diag,
                         commit=final_commit)
        except Exception as exc:  # noqa: BLE001 - a meta failure must never end the run
            log(f'WARN meta round failed: {exc!r}')
            self._record(round_idx, best_commit, best_before, result, 'exception', {})
        finally:
            try:
                vc.reset_to_base(final_commit)
            except Exception as exc:  # noqa: BLE001
                log(f'WARN meta reset failed: {exc!r}')
        return final_commit, result

    def _record(
        self,
        round_idx: int,
        best_commit: str,
        best_before: float,
        result: AgentResult | None,
        outcome: str,
        diag: dict[str, Any],
        *,
        commit: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            'round': round_idx,
            'outcome': outcome,
            'best_commit': best_commit[:10],
            'best_before': best_before,
            'status': result.status if result else '',
            'error': (result.error or '')[:200] if result else '',
            'tokens': result.tokens if result else 0,
            'cost_usd': result.cost_usd if result else 0.0,
            'committed': outcome == 'committed',
            'commit': (commit or best_commit)[:10],
        }
        record.update({k: v for k, v in diag.items() if k != 'mechanism_diff_preview'})
        if result and result.meta_invocation:
            record['meta_invocation'] = result.meta_invocation
        if 'mechanism_diff_preview' in diag:
            record['mechanism_diff_preview'] = diag['mechanism_diff_preview'][:200]
        record_meta_round(self.config.paths.run_dir, record)

    def _prompt(self, phi: str) -> str:
        mech = self.config.paths.mechanism_dir
        if self.config.meta_strict_self_contained:
            skill_path = mech / 'a8s_meta_skill.md'
            constitution_path = mech / 'a8s_meta_constitution.md'
        else:
            skill_path = mech / 'meta_skill.md'
            constitution_path = (
                mech / 'a8_meta_constitution.md'
                if self.config.meta_agent_kind == 'claude_cli' else None
            )
        contract = skill_path.read_text(encoding='utf-8') if skill_path.is_file() else (
            'You may edit ONLY the mechanism layer to improve how the inner agent searches. '
            'You cannot change the evaluator, metric, or thresholds.'
        )
        if constitution_path is not None and constitution_path.is_file():
            contract += (
                '\n\n---\n# Meta constitution\n\n'
                + constitution_path.read_text(encoding='utf-8')
            )
        family_block = ''
        if (
            not self.config.meta_strict_self_contained
            and self.config.meta_agent_kind != 'claude_cli'
        ):
            family_map = load_family_map(self.config)
            family_block = (
                f'\n\n---\n# Known heuristic families (family_map.md)\n\n{family_map}\n'
                if family_map else ''
            )
        return f'{contract}{family_block}\n\n---\n# Current state (Phi)\n\n{phi}\n'
