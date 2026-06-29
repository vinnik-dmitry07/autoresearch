'''Configuration and workspace paths.

The runtime store (`run_dir`) lives OUTSIDE the repo working tree so that the
per-candidate `git reset --hard` / `git clean -fd` can never destroy candidates,
state, history, logs, or scores (plan mechanical contract 1). The tracked inputs
(`evolve/manifest.yaml`, `evolve/config.json`, `evolve/mechanism/`) stay in the repo.
'''
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .util import utc_stamp

DEFAULT_ALLOWLIST = ('durak/src/strategy_heuristic.cpp',)


def find_repo_root(start: Path | None = None) -> Path:
    '''Walk upwards from start (or cwd) until a .git directory is found.'''
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / '.git').exists():
            return candidate
    return here


@dataclass
class SessionConfig:
    '''Bounds for a single inner agent session.'''

    max_turns: int = 12
    token_cap: int = 60_000
    wall_timeout_s: float = 900.0
    thinking_level: str = 'medium'
    model: str = 'auto'
    cost_per_session_usd: float = 0.0


@dataclass
class Paths:
    '''Resolved filesystem locations for one run.'''

    repo_root: Path
    run_dir: Path

    @property
    def candidates_dir(self) -> Path:
        return self.run_dir / 'candidates'

    @property
    def archive_json(self) -> Path:
        return self.run_dir / 'archive.json'

    @property
    def state_json(self) -> Path:
        return self.run_dir / 'state.json'

    @property
    def history_jsonl(self) -> Path:
        return self.run_dir / 'history.jsonl'

    @property
    def usage_json(self) -> Path:
        return self.run_dir / 'usage.json'

    @property
    def cost_jsonl(self) -> Path:
        return self.run_dir / 'cost.jsonl'

    @property
    def observations_dir(self) -> Path:
        return self.run_dir / 'observations'

    @property
    def backups_dir(self) -> Path:
        return self.run_dir / 'backups'

    @property
    def evolve_log(self) -> Path:
        return self.run_dir / 'evolve.log'

    @property
    def results_tsv(self) -> Path:
        '''Canonical results view, safe in run_dir (git cannot touch it).'''
        return self.run_dir / 'results.tsv'

    @property
    def repo_results_tsv(self) -> Path:
        '''Convenience copy inside the repo for analysis.ipynb (regenerated).'''
        return self.repo_root / 'results.tsv'

    @property
    def mechanism_dir(self) -> Path:
        return self.repo_root / 'evolve' / 'mechanism'

    def ensure(self) -> None:
        '''Create the run_dir tree.'''
        for directory in (self.run_dir, self.candidates_dir, self.observations_dir, self.backups_dir):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    '''Top-level harness configuration for one run.'''

    repo_root: Path
    paths: Paths
    run_id: str
    schema_version: int = 1
    max_rounds: int = 20
    k: int = 2
    cost_cap_usd: float = 5.0
    allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST
    gate_search: str = 'quick'
    gate_holdout: str = 'dual'
    gate_full: str = 'full'
    search_delta: float = 0.005
    holdout_trigger_delta: float = 0.0
    best_search: float = 0.0
    best_b4: float = 0.0
    best_lower_ci: float = 0.0
    engine: str = 'default'
    selector: str = 'random'
    selector_scale: float = 10.0
    selector_topk: int = 3
    nonconfirm_penalty: float = 0.98
    min_rounds: int = 0
    convergence_enabled: bool = False
    convergence_patience: int = 6
    meta_every: int = 0
    meta_target: str = 'evolve/mechanism/evolve_skill.md'
    use_worktrees: bool = False
    hygiene_enabled: bool = True
    stale_min_idle_rounds: int = 8
    backup_keep: int = 10
    session: SessionConfig = field(default_factory=SessionConfig)
    skip_build: bool = False
    agent_kind: str = 'cursor_cli'
    cmake_exe: str = ''
    # Behavioral descriptor b(x). Dormant by default: 'static' uses StaticDescriptor;
    # 'feature' reads the stored shadow descriptor. shadow_descriptors gates the extra
    # `--mode features` pass that records b_descriptor without touching selection/keep.
    descriptor_kind: str = 'static'
    shadow_descriptors: bool = False
    descriptor_seeds: int = 1500
    descriptor_columns: tuple[str, ...] = ()
    select_policy_path: str = ''
    # A2 gridless novelty multiplier for score_child_prop: p(parent) proportional to
    # base_weight * (1 + novelty_lambda * normalized_novelty(b(x))). Dormant at 0.0,
    # where the selector is byte-identical to plain score_child_prop. Reads stored b(x).
    novelty_lambda: float = 0.0
    novelty_k: int = 3
    # A3 LLM-free parameter sweep. Dormant unless engine='sweep' AND a template+axes
    # are given: the harness templates `sweep_template` by the cartesian product of
    # `sweep_axes` (token -> value list) and scores each variant through the keep gate.
    sweep_template: str = ''
    sweep_axes: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def allowlist_paths(self) -> tuple[Path, ...]:
        return tuple(self.repo_root / rel for rel in self.allowlist)


def _load_manifest_allowlist(repo_root: Path) -> tuple[str, ...] | None:
    '''Read evolve/manifest.yaml and return its inner evolvable layer paths.'''
    manifest_path = repo_root / 'evolve' / 'manifest.yaml'
    if not manifest_path.exists():
        return None
    data = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
    layers = (data.get('evolvable_layers') or {}).get('inner') or []
    paths = tuple(str(p) for p in layers)
    return paths or None


def _resolve_run_dir(repo_root: Path, raw: Any, run_id: str) -> Path:
    '''Resolve run_dir; default to a sibling of the repo so git cannot reach it.'''
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate
    return (repo_root.parent / '.evolver_runs' / run_id).resolve()


def load_config(
    repo_root: Path | None = None,
    run_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> Config:
    '''Load defaults, overlay evolve/config.json, then overlay explicit overrides.'''
    repo_root = (repo_root or find_repo_root()).resolve()
    raw: dict[str, Any] = {}
    config_path = repo_root / 'evolve' / 'config.json'
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding='utf-8'))
    if overrides:
        raw = {**raw, **overrides}

    run_id = run_id or raw.get('run_id') or utc_stamp()
    run_dir = _resolve_run_dir(repo_root, raw.get('run_dir'), run_id)
    paths = Paths(repo_root=repo_root, run_dir=run_dir)

    allowlist = _load_manifest_allowlist(repo_root)
    if allowlist is None:
        allowlist = tuple(raw.get('allowlist', DEFAULT_ALLOWLIST))

    gates = raw.get('gates', {})
    keep_rule = raw.get('keep_rule', {})
    baseline = raw.get('baseline', {})
    promotion = raw.get('promotion', {})
    convergence = raw.get('convergence', {})
    meta = raw.get('meta', {})
    descriptor = raw.get('descriptor', {})
    novelty = raw.get('novelty', {})
    sweep = raw.get('sweep', {})
    sweep_axes = {
        str(token): tuple(str(v) for v in values)
        for token, values in (sweep.get('axes') or {}).items()
    }
    session_raw = raw.get('session', {})
    session = SessionConfig(
        max_turns=int(session_raw.get('max_turns', 12)),
        token_cap=int(session_raw.get('token_cap', 60_000)),
        wall_timeout_s=float(session_raw.get('wall_timeout_s', 900.0)),
        thinking_level=str(session_raw.get('thinking_level', 'medium')),
        model=str(session_raw.get('model', 'auto')),
        cost_per_session_usd=float(session_raw.get('cost_per_session_usd', 0.0)),
    )

    return Config(
        repo_root=repo_root,
        paths=paths,
        run_id=run_id,
        schema_version=int(raw.get('schema_version', 1)),
        max_rounds=int(raw.get('max_rounds', 20)),
        k=int(raw.get('K', raw.get('k', 2))),
        cost_cap_usd=float(raw.get('cost_cap_usd', 5.0)),
        allowlist=tuple(allowlist),
        gate_search=str(gates.get('search', 'quick')),
        gate_holdout=str(gates.get('holdout', 'dual')),
        gate_full=str(gates.get('full', 'full')),
        search_delta=float(keep_rule.get('search_delta', 0.005)),
        holdout_trigger_delta=float(promotion.get('holdout_trigger_delta', 0.0)),
        best_search=float(baseline.get('best_search', 0.0)),
        best_b4=float(baseline.get('best_b4', 0.0)),
        best_lower_ci=float(baseline.get('best_lower_ci', 0.0)),
        engine=str(raw.get('engine', 'default')),
        selector=str(raw.get('selector', 'random')),
        selector_scale=float(raw.get('selector_scale', 10.0)),
        selector_topk=int(raw.get('selector_topk', 3)),
        nonconfirm_penalty=float(raw.get('nonconfirm_penalty', 0.98)),
        min_rounds=int(convergence.get('min_rounds', raw.get('min_rounds', 0))),
        convergence_enabled=bool(convergence.get('enabled', False)),
        convergence_patience=int(convergence.get('patience', 6)),
        meta_every=int(meta.get('every', 0)),
        meta_target=str(meta.get('target', 'evolve/mechanism/evolve_skill.md')),
        use_worktrees=bool(raw.get('use_worktrees', False)),
        hygiene_enabled=bool(raw.get('hygiene_enabled', True)),
        stale_min_idle_rounds=int(raw.get('stale_min_idle_rounds', 8)),
        backup_keep=int(raw.get('backup_keep', 10)),
        session=session,
        skip_build=bool(raw.get('skip_build', False)),
        agent_kind=str(raw.get('agent', 'cursor_cli')),
        cmake_exe=str(raw.get('cmake', '')),
        descriptor_kind=str(descriptor.get('kind', 'static')),
        shadow_descriptors=bool(descriptor.get('shadow', False)),
        descriptor_seeds=int(descriptor.get('seeds', 1500)),
        descriptor_columns=tuple(str(c) for c in (descriptor.get('columns') or ())),
        select_policy_path=str(raw.get('select_policy', '')),
        novelty_lambda=float(novelty.get('lambda', 0.0)),
        novelty_k=int(novelty.get('k', 3)),
        sweep_template=str(sweep.get('template', '')),
        sweep_axes=sweep_axes,
    )
