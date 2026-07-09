'''The external driver. It - not the agent - owns rounds, budget, scoring, the
keep/rollback gate, and termination.

Per-candidate flow (resets ALWAYS in finally; runtime store is outside the repo):
  restore parent snapshot -> run bounded agent session -> reset_all_but_allowlist
  (discard illegal edits) -> capture diff/snapshot in memory -> precheck+search eval
  -> [promotion track] holdout+full -> keep rule -> official_best (commit 'exp:' +
  tag evo-N + advance best_commit) | else valid_stepping_stone -> store.add ->
  regenerate results.tsv -> account budget/cost -> finally reset_to_base(best_commit).

Terminates ONLY on max_rounds, cost_cap, or an external operator stop flag. The
agent's DONE/PLATEAU never ends the outer run.
'''
from __future__ import annotations

import re
import shutil
import time
from typing import Any, Callable

from .agents import COMPLETED, Agent, AgentContext, AgentResult
from .config import Config
from .engine import EvolutionEngine, make_engine
from .evaluate import Evaluator, RealEvaluator, Scores, Verdict, keep_rule
from .hygiene import Hygiene
from .meta import Attribution, ConvergencePolicy, MetaController
from .observe import Observer
from .population import DEFAULT_DESCRIPTOR_COLUMNS, parse_feature_descriptor
from .protect import VersionControl
from .select import Selector, make_selector
from .leak_gate import gate_scan, snapshot_digest
from .store import INVALID, OFFICIAL_BEST, STEPPING_STONE, Candidate, Store
from .usage_limit import (
    is_cursor_auto_stop_flag,
    pause_for_cursor_auto_stop_flag,
    session_limit_message,
    wait_for_usage_reset,
)
from .util import atomic_write_json, log, read_json
import random

_RE_H = re.compile(r'kHeuristicCount\s*=\s*(\d+)')
_RE_P = re.compile(r'kParameterCount\s*=\s*(\d+)')


def parse_complexity(source: str) -> int | None:
    '''Derive complexity = 100*H + 10*P from the strategy manifest constants.'''
    h = _RE_H.search(source)
    p = _RE_P.search(source)
    if h is None or p is None:
        return None
    return 100 * int(h.group(1)) + 10 * int(p.group(1))


class Loop:
    '''Owns the evolution run for one config. Dependencies are injectable for tests.'''

    def __init__(
        self,
        config: Config,
        *,
        agent: Agent | None = None,
        agent_factory: Callable[[Config], Agent] | None = None,
        vc: VersionControl | None = None,
        evaluator: Evaluator | None = None,
        store: Store | None = None,
        selector: Selector | None = None,
        observer: Observer | None = None,
        engine: EvolutionEngine | None = None,
        meta_agent: Agent | None = None,
        meta_agent_factory: Callable[[Config], Agent] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.paths = config.paths
        self.allow_rel = config.allowlist[0]
        self.paths.ensure()
        self.vc = vc or VersionControl(config.repo_root, config.allowlist)
        self.evaluator = evaluator or RealEvaluator(config)
        self.store = store or Store(self.paths, schema_version=config.schema_version)
        self.observer = observer or Observer(config)
        self.selector = selector or make_selector(
            config.selector, config.selector_scale, config.selector_topk,
            novelty_lambda=config.novelty_lambda, novelty_k=config.novelty_k,
        )
        self.engine = engine or make_engine(config.engine, self.selector, config)
        self.hygiene = Hygiene(self.paths, keep=config.backup_keep)
        self.convergence = ConvergencePolicy(
            config.convergence_enabled, config.min_rounds, config.convergence_patience,
        )
        self.attribution = Attribution(self.paths.run_dir / 'attribution.jsonl')
        self.rng = rng or random.Random(config.rng_seed)
        self._agent = agent
        self._agent_factory = agent_factory
        self._meta_agent = meta_agent
        self._meta_agent_factory = meta_agent_factory
        self.meta: MetaController | None = None
        self.state: dict[str, Any] = {}
        self.skill = self._load_skill()

    def _load_skill(self) -> str:
        skill_path = self.paths.mechanism_dir / 'evolve_skill.md'
        return skill_path.read_text(encoding='utf-8') if skill_path.exists() else ''

    # --- agent resolution ----------------------------------------------------------

    def _agent_instance(self) -> Agent:
        if self._agent is not None:
            return self._agent
        if self._agent_factory is not None:
            self._agent = self._agent_factory(self.config)
            return self._agent
        raise RuntimeError(
            'no agent provided. Phase 0 runs via tests with a StubAgent; '
            'Phase 1 wires CursorAgent through agent_factory.'
        )

    def _meta_instance(self) -> Agent:
        if self._meta_agent is not None:
            return self._meta_agent
        if self._meta_agent_factory is not None:
            self._meta_agent = self._meta_agent_factory(self.config)
            return self._meta_agent
        return self._agent_instance()

    # --- state ---------------------------------------------------------------------

    def _save_state(self) -> None:
        atomic_write_json(self.paths.state_json, self.state)

    def _init_state(self, resume: bool) -> None:
        existing = read_json(self.paths.state_json, default=None) if resume else None
        if resume and existing is None and self.paths.state_json.exists():
            # state.json present but unreadable -> recover from the latest backup.
            if self.hygiene.restore_latest():
                existing = read_json(self.paths.state_json, default=None)
        if existing:
            self.state = existing
            if self.config.max_rounds > int(self.state.get('max_rounds', 0)):
                self.state['max_rounds'] = self.config.max_rounds
            if self.state.get('finished') and self.state['round'] < self.config.max_rounds:
                self.state['finished'] = False
            self.best_commit = self.state.get('best_commit') or self.vc.current_commit()
            log(f'resuming run {self.state.get("run_id")} at round {self.state.get("round")}')
            self.vc.reset_to_base(self.best_commit)
            return
        base = self.vc.current_commit()
        self.best_commit = base
        self.state = {
            'run_id': self.config.run_id,
            'base_commit': base,
            'best_commit': base,
            'best_id': None,
            'best_search': self.config.best_search,
            'best_b4': self.config.best_b4,
            'best_lower_ci': self.config.best_lower_ci,
            'round': 0,
            'max_rounds': self.config.max_rounds,
            'cost_usd': 0.0,
            'cost_cap_usd': self.config.cost_cap_usd,
            'plateau': 0,
            'finished': False,
            'selector': self.selector.name,
            'started_at': time.time(),
            'evo_count': 0,
            'last_official_round': 0,
            'rng_seed': self.config.rng_seed,
            'meta_slots_attempted': 0,
            'meta_slots_completed': 0,
            'meta_slots_committed': 0,
            'meta_slots_skipped_quota': 0,
            'meta_cost_usd': 0.0,
        }
        self._seed_root(base)
        self._save_state()

    def _seed_root(self, base: str) -> None:
        '''Seed candidate_0000 = the current best baseline, so the pool is non-empty.'''
        if self.store.all():
            return
        snapshot = self.vc.read_repo_file(self.allow_rel)
        root = Candidate(
            id=self.store.next_id(),
            parent_id=None,
            base_commit=base,
            round=0,
            status=OFFICIAL_BEST,
            created_by='harness',
            search_alpha=self.config.best_search,
            holdout_alpha=self.config.best_search,
            selection_alpha=self.config.best_search,
            search_score=self.config.best_search,
            point_rate_b4=self.config.best_b4,
            lower_ci=self.config.best_lower_ci,
            complexity=parse_complexity(snapshot),
            eval_bank='baseline',
            score_kind='baseline',
            reason='seed baseline',
        )
        self.store.add(root, patch='', snapshot=snapshot)
        self.store.pin_lineage(root.id, 0)
        self.state['best_id'] = root.id

    # --- termination ---------------------------------------------------------------

    def _terminate_reason(self) -> str | None:
        stop = self.paths.run_dir / 'stop.flag'
        if stop.exists():
            text = stop.read_text(encoding='utf-8')
            if not is_cursor_auto_stop_flag(text):
                return 'operator stop flag'
        if self.engine.exhausted():
            return 'sweep complete'
        if self.state['round'] >= self.config.max_rounds:
            return 'max_rounds reached'
        if self.state['cost_usd'] >= self.config.cost_cap_usd:
            return 'cost_cap reached'
        return self.convergence.reason(self.state)

    def _pause_for_cursor_auto_stop_if_needed(self) -> None:
        stop = self.paths.run_dir / 'stop.flag'
        if not stop.exists():
            return
        text = stop.read_text(encoding='utf-8')
        if not is_cursor_auto_stop_flag(text):
            return
        log('USAGE LIMIT: cursor auto threshold — pausing until reset')
        pause_for_cursor_auto_stop_flag(text)
        stop.unlink(missing_ok=True)
        log('USAGE LIMIT: cursor auto reset — resuming run')

    def _run_agent_with_usage_wait(self, agent: Agent, ctx: AgentContext) -> AgentResult:
        while True:
            result = agent.run(ctx)
            limit_msg = session_limit_message(
                result.error, result.summary, result.agent_stdout,
            )
            if result.status == COMPLETED or not limit_msg:
                return result
            log(f'  USAGE LIMIT: agent session blocked — {limit_msg}')
            wait_for_usage_reset(error=limit_msg, usage_reset_at=result.usage_reset_at)

    # --- main loop -----------------------------------------------------------------

    def run(self, resume: bool = False) -> int:
        self._init_state(resume)
        if self.config.meta_every > 0:
            self.meta = MetaController(
                self.config, self._meta_instance(), self.attribution,
            )
        if self.config.hygiene_enabled:
            self.hygiene.backup('run_start')
        log(f'run {self.config.run_id} | run_dir={self.paths.run_dir}')
        log(f'base_commit={self.best_commit[:10]} best_search={self.state["best_search"]:.5f} '
            f'max_rounds={self.config.max_rounds} K={self.config.k} rng_seed={self.config.rng_seed} '
            f'engine={self.engine.name} selector={self.selector.name}')
        while True:
            self._pause_for_cursor_auto_stop_if_needed()
            reason = self._terminate_reason()
            if reason is not None:
                log(f'TERMINATE: {reason}')
                break
            self._round()
            self._maybe_meta()
        self.state['finished'] = True
        self._save_state()
        self.store.regenerate_results()
        log(f'done. best_id={self.state["best_id"]} best_search={self.state["best_search"]:.5f} '
            f'rounds={self.state["round"]} cost={self.state["cost_usd"]:.4f} evo={self.state["evo_count"]}')
        if self.config.meta_every > 0:
            log(f'meta: attempted={self.state.get("meta_slots_attempted", 0)} '
                f'completed={self.state.get("meta_slots_completed", 0)} '
                f'committed={self.state.get("meta_slots_committed", 0)} '
                f'skipped_quota={self.state.get("meta_slots_skipped_quota", 0)} '
                f'cost={self.state.get("meta_cost_usd", 0.0):.4f}')
        return 0

    def _round(self) -> None:
        round_idx = self.state['round']
        phi = self.observer.summarize(self.store, self.state)
        pool = self.store.parents_pool()
        parents = self.engine.select_parents(self.store, self.config.k, self.rng, self.state)
        log(f'--- round {round_idx + 1}/{self.config.max_rounds} | engine={self.engine.name} '
            f'pool={len(pool)} parents={[p.id for p in parents]} ---')
        agent = self._agent_instance()
        improved = False
        for parent in parents:
            if self.state['cost_usd'] >= self.config.cost_cap_usd:
                log('cost cap hit mid-round; stopping remaining K')
                break
            if self.engine.exhausted():
                break  # LLM-free sweep ran out of variants mid-round
            self.store.mark_selected(parent.id, round_idx)
            cand, accepted = self._run_candidate(parent, round_idx, agent, phi)
            improved = improved or accepted
            self.engine.on_cycle_end(accepted, cand.search_alpha)
            log(f'  {cand.id}: status={cand.status} search_alpha={cand.search_alpha} '
                f'sel_alpha={cand.selection_alpha} :: {cand.reason}')
        self.state['round'] = round_idx + 1
        self.state['plateau'] = 0 if improved else self.state['plateau'] + 1
        self._save_state()
        self.store.regenerate_results()
        if self.config.shadow_descriptors:
            self.observer.record_descriptor_coverage(self.store, self.state)
        self.observer.flush_memory(self.state, 'improved' if improved else 'no improvement')
        if self.config.hygiene_enabled:
            moved = self.store.archive_stale(self.state['round'], self.config.stale_min_idle_rounds)
            if moved:
                log(f'  hygiene: archived {moved} stale record(s) (restorable)')
            self.hygiene.backup(f'round_{self.state["round"]:03d}')

    def _maybe_meta(self) -> None:
        '''Run a bounded meta self-modification round when due (default OFF).'''
        if self.meta is None:
            return
        round_idx = self.state['round']
        self.attribution.record_round(round_idx, self.state['best_search'])
        if not self.meta.due(round_idx):
            return
        self.state['meta_slots_attempted'] = int(self.state.get('meta_slots_attempted', 0)) + 1
        phi = self.observer.summarize(self.store, self.state)
        new_commit, meta_result = self.meta.run(
            round_idx, phi, self.best_commit, self.state['best_search'],
        )
        if meta_result is None and self.meta.quota_exhausted:
            self.state['meta_slots_skipped_quota'] = (
                int(self.state.get('meta_slots_skipped_quota', 0)) + 1
            )
            self._save_state()
            return
        if meta_result is not None:
            meta_cost = meta_result.cost_usd
            if (
                meta_result.status == COMPLETED
                and meta_cost <= 0
                and self.config.meta_session.max_budget_usd > 0
            ):
                meta_cost = self.config.meta_session.max_budget_usd
            if meta_result.status == COMPLETED:
                meta_cost += self.config.meta_session.cost_per_session_usd
                self.state['meta_slots_completed'] = (
                    int(self.state.get('meta_slots_completed', 0)) + 1
                )
            if meta_cost > 0:
                self.state['cost_usd'] += meta_cost
                self.state['meta_cost_usd'] = (
                    float(self.state.get('meta_cost_usd', 0.0)) + meta_cost
                )
                self.observer.append_cost({
                    'round': round_idx,
                    'candidate_id': 'meta',
                    'tokens': meta_result.tokens,
                    'cost_usd': meta_cost,
                    'eval_seconds': 0.0,
                    'status': meta_result.status,
                })
        if new_commit != self.best_commit:
            self.best_commit = new_commit
            self.state['best_commit'] = new_commit
            self.state['meta_slots_committed'] = (
                int(self.state.get('meta_slots_committed', 0)) + 1
            )
            self.skill = self._load_skill()  # mechanism may have changed the inner contract
            log(f'  META advanced mechanism -> {new_commit[:10]}')
            self._save_state()

    def _run_candidate(
        self, parent: Candidate, round_idx: int, agent: Agent, phi: str,
    ) -> tuple[Candidate, bool]:
        cid = self.store.next_id()
        base = self.best_commit
        created_by = 'harness'
        patch = ''
        snapshot_text = ''
        status = INVALID
        reason = ''
        tokens = 0
        cost = 0.0
        eval_seconds = 0.0
        search: Scores | None = None
        holdout: Scores | None = None
        full: Scores | None = None
        verdict: Verdict | None = None
        accepted = False
        b_descriptor: list[float] | None = None
        parent_snap = self.store.snapshot_text(parent.id)
        leak_skipped = False
        snapshot_hash_at_gate = ''
        try:
            proposal = self.engine.propose_snapshot(self.store, self.state, self.rng)
            if proposal is not None:
                # LLM-free sweep variant: write the templated snapshot directly and
                # score it through the SAME precheck/keep gate (no agent session).
                created_by = 'sweep'
                self.vc.write_repo_file(self.allow_rel, proposal)
                self.vc.reset_all_but_allowlist(base)
                patch = self.vc.diff_allowlist(base)
                snapshot_text = self.vc.read_repo_file(self.allow_rel)
                result = AgentResult(status=COMPLETED, summary='sweep variant')
                if self.config.leak_policy.enabled:
                    gate_hits = gate_scan('', snapshot_text)
                    if gate_hits:
                        leak_skipped = True
                        reason = f'leak gate: {gate_hits[0]}'
                        log(f'  LEAK GATE {cid} (sweep): {gate_hits[0]}')
                        self._record_leak_hit(round_idx, gate_hits)
                    else:
                        snapshot_hash_at_gate = snapshot_digest(snapshot_text)
            elif self.config.use_worktrees:
                result, patch, snapshot_text = self._propose_in_worktree(
                    parent_snap, base, phi, round_idx, parent, agent,
                )
                if result.status == COMPLETED and patch.strip():
                    self.vc.write_repo_file(self.allow_rel, snapshot_text)  # apply for eval
            else:
                if parent_snap:
                    self.vc.write_repo_file(self.allow_rel, parent_snap)
                ctx = AgentContext(
                    repo_root=self.config.repo_root,
                    strategy_rel=self.allow_rel,
                    prompt=self._build_prompt(phi),
                    phi=phi,
                    round_idx=round_idx,
                    parent_id=parent.id,
                    run_dir=self.paths.run_dir,
                )
                result = self._run_agent_with_usage_wait(agent, ctx)
                if result.status == COMPLETED:
                    self.vc.reset_all_but_allowlist(base)
                    patch = self.vc.diff_allowlist(base)
                    snapshot_text = self.vc.read_repo_file(self.allow_rel)
            tokens = result.tokens
            cost = result.cost_usd
            if result.status != COMPLETED:
                reason = f'agent {result.status}: {result.error}'.strip()
            elif self.config.leak_policy.enabled:
                stdout = getattr(result, 'agent_stdout', '') or ''
                gate_hits = gate_scan(stdout, snapshot_text)
                if gate_hits:
                    leak_skipped = True
                    reason = f'leak gate: {gate_hits[0]}'
                    log(f'  LEAK GATE {cid}: {gate_hits[0]}')
                    self._record_leak_hit(round_idx, gate_hits)
                elif patch.strip():
                    snapshot_hash_at_gate = snapshot_digest(snapshot_text)
            if not leak_skipped and result.status == COMPLETED and not reason:
                if not patch.strip():
                    reason = 'empty diff'
                else:
                    self._clean_eval_scratch(cid)
                    ok, pre_reason = self.evaluator.precheck()
                    if not ok:
                        reason = pre_reason
                    else:
                        search = self.evaluator.run_search()
                        if search is None:
                            reason = 'search eval failed'
                        else:
                            status = STEPPING_STONE
                            eval_seconds += search.eval_seconds
                            reason = f'search_alpha={search.search_score:.5f}'
                            if self._should_run_promotion_track(search):
                                holdout = self.evaluator.run_holdout()
                                full = self.evaluator.run_full()
                                if holdout is not None and full is not None:
                                    eval_seconds += holdout.eval_seconds + full.eval_seconds
                                    verdict = keep_rule(
                                        full.search_score, full.lower_ci,
                                        self.state['best_search'], self.state['best_lower_ci'],
                                        self.config.search_delta,
                                    )
                                    if verdict.accept:
                                        on_disk = self.vc.read_repo_file(self.allow_rel)
                                        if snapshot_hash_at_gate and snapshot_digest(on_disk) != snapshot_hash_at_gate:
                                            status = INVALID
                                            reason = 'promote blocked: snapshot changed after leak gate'
                                            log(f'  PROMOTE BLOCKED {cid}: snapshot hash mismatch')
                                        else:
                                            status = OFFICIAL_BEST
                                            reason = verdict.reason
                                            accepted = self._promote(full)
                                    else:
                                        reason = verdict.reason
                            # Shadow descriptor: record b(x) for every valid candidate.
                            # Never read by selection or the keep rule (telemetry only).
                            if self.config.shadow_descriptors:
                                b_descriptor = self._shadow_descriptor(cid)
        except Exception as exc:  # noqa: BLE001 - a candidate crash must never be fatal
            status = INVALID
            reason = f'crash: {exc!r}'
        finally:
            try:
                self.vc.reset_to_base(self.best_commit)
            except Exception as exc:  # noqa: BLE001
                log(f'WARN reset_to_base failed: {exc!r}')

        cand = self._build_candidate(
            cid, parent, base, round_idx, status, reason,
            search, holdout, full, snapshot_text, tokens, eval_seconds, created_by,
        )
        if b_descriptor is not None:
            cand.b_descriptor = b_descriptor
        if not leak_skipped:
            self.store.add(cand, patch=patch, snapshot=snapshot_text)
            if status == OFFICIAL_BEST:
                self.store.pin_lineage(cand.id, round_idx)
        else:
            log(f'  {cid}: leak invalid — no archive/results row')
        self.state['cost_usd'] += cost + self.config.session.cost_per_session_usd
        self.observer.append_cost({
            'round': round_idx, 'candidate_id': cid, 'tokens': tokens,
            'cost_usd': cost, 'eval_seconds': eval_seconds, 'status': status,
        })
        return cand, accepted

    def _shadow_descriptor(self, cid: str) -> list[float] | None:
        '''Shadow b(x): a cheap `--mode features` pass parsed into a mean vector.

        Pure telemetry - the result is stored in meta.json but never consulted by
        parent selection or the keep rule. Any failure is swallowed (non-fatal).
        '''
        run_features = getattr(self.evaluator, 'run_features', None)
        if run_features is None:
            return None
        out = self.paths.run_dir / 'descriptors' / f'{cid}.tsv'
        columns = list(self.config.descriptor_columns) or list(DEFAULT_DESCRIPTOR_COLUMNS)
        try:
            if not run_features(out, self.config.descriptor_seeds):
                return None
            vec = parse_feature_descriptor(out, columns)
        except Exception as exc:  # noqa: BLE001 - shadow telemetry must never be fatal
            log(f'WARN shadow descriptor failed for {cid}: {exc!r}')
            return None
        return list(vec) if vec else None

    def _promote(self, full: Scores) -> bool:
        '''Commit the accepted candidate as the new official best and advance pointers.'''
        message = f'exp: evo candidate search={full.search_score:.5f} b4={full.point_rate_b4:.5f}'
        new_commit = self.vc.commit_inline(message)
        self.best_commit = new_commit
        self.state['best_commit'] = new_commit
        self.state['best_search'] = full.search_score
        self.state['best_b4'] = full.point_rate_b4
        self.state['best_lower_ci'] = full.lower_ci
        self.state['evo_count'] += 1
        self.state['last_official_round'] = self.state['round']
        tag = self.vc.tag_evo(self.state['evo_count'])
        log(f'  PROMOTE official_best -> {new_commit[:10]} tag={tag} search={full.search_score:.5f}')
        return True

    def _should_run_promotion_track(self, search: Scores) -> bool:
        '''Mirror triage.bat full gate: Δsearch≥trigger OR ΔB4≥b4_trigger (jun22 B4-first).'''
        if search.search_score >= self.state['best_search'] + self.config.holdout_trigger_delta:
            return True
        return search.point_rate_b4 >= self.state['best_b4'] + self.config.holdout_trigger_b4_delta

    def _build_candidate(
        self,
        cid: str,
        parent: Candidate,
        base: str,
        round_idx: int,
        status: str,
        reason: str,
        search: Scores | None,
        holdout: Scores | None,
        full: Scores | None,
        snapshot_text: str,
        tokens: int,
        eval_seconds: float,
        created_by: str = 'harness',
    ) -> Candidate:
        search_alpha = search.search_score if search else None
        holdout_alpha = holdout.search_score if holdout else None
        if holdout_alpha is not None:
            selection_alpha: float | None = holdout_alpha
        elif search_alpha is not None:
            selection_alpha = search_alpha * self.config.nonconfirm_penalty
        else:
            selection_alpha = None
        best = full or holdout or search
        eval_bank = best.eval_bank if best else None
        score_kind = best.score_kind if best else None
        if status == OFFICIAL_BEST and full is not None:
            self.state['best_id'] = cid
        return Candidate(
            id=cid,
            parent_id=parent.id,
            base_commit=base,
            round=round_idx,
            status=status,
            created_by=created_by,
            search_alpha=search_alpha,
            holdout_alpha=holdout_alpha,
            selection_alpha=selection_alpha,
            search_score=(best.search_score if best else None),
            point_rate_b4=(best.point_rate_b4 if best else None),
            lower_ci=(best.lower_ci if best else None),
            complexity=parse_complexity(snapshot_text) if snapshot_text else None,
            eval_bank=eval_bank,
            score_kind=score_kind,
            tokens=tokens,
            eval_seconds=eval_seconds,
            reason=reason,
        )

    def _build_prompt(self, phi: str) -> str:
        '''Prepend the stateless skill contract (if present) to the bounded Phi.'''
        if self.skill:
            return f'{self.skill}\n\n---\n# Current state (Phi)\n\n{phi}\n'
        return phi

    def _propose_in_worktree(
        self, parent_snap: str, base: str, phi: str, round_idx: int, parent: Candidate, agent: Agent,
    ) -> tuple[Any, str, str]:
        '''Run the agent in a throwaway worktree so it cannot touch the main sandbox.

        Returns (agent_result, allowlist_patch, snapshot). The harness copies only the
        allowlist snapshot/diff back; locked edits inside the worktree are destroyed.
        '''
        from .worktree import worktree

        with worktree(self.config.repo_root, base, f'cand_r{round_idx}') as wt:
            if parent_snap:
                (wt / self.allow_rel).write_text(parent_snap, encoding='utf-8')
            ctx = AgentContext(
                repo_root=wt,
                strategy_rel=self.allow_rel,
                prompt=self._build_prompt(phi),
                phi=phi,
                round_idx=round_idx,
                parent_id=parent.id,
                run_dir=self.paths.run_dir,
            )
            result = self._run_agent_with_usage_wait(agent, ctx)
            patch = ''
            if result.status == COMPLETED:
                patch = VersionControl(wt, self.config.allowlist).diff_allowlist(base)
            allow_path = wt / self.allow_rel
            snapshot = allow_path.read_text(encoding='utf-8') if allow_path.exists() else ''
        return result, patch, snapshot

    def _clean_eval_scratch(self, cid: str) -> None:
        '''Drop stale triage artifacts before scorer runs (S6 side-effect isolation).'''
        triage = self.config.repo_root / 'durak' / 'triage_parts'
        if triage.exists():
            shutil.rmtree(triage, ignore_errors=True)
        scratch = self.paths.run_dir / '_eval_scratch' / cid
        scratch.mkdir(parents=True, exist_ok=True)

    def _record_leak_hit(self, round_idx: int, hits: list[str]) -> None:
        count = int(self.state.get('leak_hits', 0)) + 1
        self.state['leak_hits'] = count
        cap = self.config.leak_policy.stop_after_hits
        if cap > 0 and count >= cap:
            stop = self.paths.run_dir / 'stop.flag'
            stop.write_text(f'leak gate: {hits[0]}\n', encoding='utf-8')
            log(f'LEAK STOP: wrote {stop} after {count} hit(s)')
