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
import time
from typing import Any, Callable

from .agents import COMPLETED, Agent, AgentContext
from .config import Config
from .engine import EvolutionEngine, make_engine
from .evaluate import Evaluator, RealEvaluator, Scores, Verdict, keep_rule
from .hygiene import Hygiene
from .meta import Attribution, ConvergencePolicy, MetaController
from .observe import Observer
from .protect import VersionControl
from .select import Selector, make_selector
from .store import INVALID, OFFICIAL_BEST, STEPPING_STONE, Candidate, Store
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
        )
        self.engine = engine or make_engine(config.engine, self.selector)
        self.hygiene = Hygiene(self.paths, keep=config.backup_keep)
        self.convergence = ConvergencePolicy(
            config.convergence_enabled, config.min_rounds, config.convergence_patience,
        )
        self.attribution = Attribution(self.paths.run_dir / 'attribution.jsonl')
        self.rng = rng or random.Random(20260627)
        self._agent = agent
        self._agent_factory = agent_factory
        self._meta_agent = meta_agent
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
        if (self.paths.run_dir / 'stop.flag').exists():
            return 'operator stop flag'
        if self.state['round'] >= self.config.max_rounds:
            return 'max_rounds reached'
        if self.state['cost_usd'] >= self.config.cost_cap_usd:
            return 'cost_cap reached'
        return self.convergence.reason(self.state)

    # --- main loop -----------------------------------------------------------------

    def run(self, resume: bool = False) -> int:
        self._init_state(resume)
        if self.config.meta_every > 0:
            self.meta = MetaController(
                self.config, self._meta_agent or self._agent_instance(), self.attribution,
            )
        if self.config.hygiene_enabled:
            self.hygiene.backup('run_start')
        log(f'run {self.config.run_id} | run_dir={self.paths.run_dir}')
        log(f'base_commit={self.best_commit[:10]} best_search={self.state["best_search"]:.5f} '
            f'max_rounds={self.config.max_rounds} K={self.config.k} '
            f'engine={self.engine.name} selector={self.selector.name}')
        while True:
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
        phi = self.observer.summarize(self.store, self.state)
        new_commit = self.meta.run(round_idx, phi, self.best_commit, self.state['best_search'])
        if new_commit != self.best_commit:
            self.best_commit = new_commit
            self.state['best_commit'] = new_commit
            self.skill = self._load_skill()  # mechanism may have changed the inner contract
            log(f'  META advanced mechanism -> {new_commit[:10]}')
            self._save_state()

    def _run_candidate(
        self, parent: Candidate, round_idx: int, agent: Agent, phi: str,
    ) -> tuple[Candidate, bool]:
        cid = self.store.next_id()
        base = self.best_commit
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
        parent_snap = self.store.snapshot_text(parent.id)
        try:
            if self.config.use_worktrees:
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
                )
                result = agent.run(ctx)
                if result.status == COMPLETED:
                    self.vc.reset_all_but_allowlist(base)
                    patch = self.vc.diff_allowlist(base)
                    snapshot_text = self.vc.read_repo_file(self.allow_rel)
            tokens = result.tokens
            cost = result.cost_usd
            if result.status != COMPLETED:
                reason = f'agent {result.status}: {result.error}'.strip()
            else:
                if not patch.strip():
                    reason = 'empty diff'
                else:
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
                            if search.search_score >= self.state['best_search'] + self.config.holdout_trigger_delta:
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
                                        status = OFFICIAL_BEST
                                        reason = verdict.reason
                                        accepted = self._promote(full)
                                    else:
                                        reason = verdict.reason
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
            search, holdout, full, snapshot_text, tokens, eval_seconds,
        )
        self.store.add(cand, patch=patch, snapshot=snapshot_text)
        if status == OFFICIAL_BEST:
            self.store.pin_lineage(cand.id, round_idx)
        self.state['cost_usd'] += cost + self.config.session.cost_per_session_usd
        self.observer.append_cost({
            'round': round_idx, 'candidate_id': cid, 'tokens': tokens,
            'cost_usd': cost, 'eval_seconds': eval_seconds, 'status': status,
        })
        return cand, accepted

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
            created_by='harness',
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
            )
            result = agent.run(ctx)
            patch = ''
            if result.status == COMPLETED:
                patch = VersionControl(wt, self.config.allowlist).diff_allowlist(base)
            allow_path = wt / self.allow_rel
            snapshot = allow_path.read_text(encoding='utf-8') if allow_path.exists() else ''
        return result, patch, snapshot
