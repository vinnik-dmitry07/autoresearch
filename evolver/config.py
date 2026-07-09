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
    '''Bounds for a single agent session (inner or meta).'''

    max_turns: int = 12
    token_cap: int = 60_000
    wall_timeout_s: float = 900.0
    thinking_level: str = 'medium'
    model: str = 'auto'
    cost_per_session_usd: float = 0.0
    effort: str = ''
    max_budget_usd: float = 0.0
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    settings_file: str = ''
    append_system_prompt_file: str = ''


@dataclass
class LeakPolicy:
    '''Tier-A leak backstop (honest-but-contaminated agent threat model).'''

    enabled: bool = True
    stop_after_hits: int = 0  # 0 = never auto-stop the outer run


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
    holdout_trigger_b4_delta: float = 0.005
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
    meta_agent_kind: str = ''
    meta_strict_self_contained: bool = False
    meta_ladder_template: str = ''
    ladder_arm: str = ''
    meta_session: SessionConfig = field(default_factory=SessionConfig)
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
    # A4 MAP-Elites coarse grid. Defaults reproduce the bare engine (bins=8, no
    # projection, raw-perf elites); the A4 treatment sets a low-D projection of b(x)
    # plus robust (holdout/lower_ci) elite replacement.
    map_elites_bins: int = 8
    map_elites_dims: tuple[int, ...] = ()
    map_elites_robust: bool = False
    leak_policy: LeakPolicy = field(default_factory=LeakPolicy)
    rng_seed: int = 20260627

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


def _parse_session(raw: dict[str, Any], fallback: SessionConfig | None = None) -> SessionConfig:
    '''Parse a session block; missing keys inherit from fallback when given.'''
    fb = fallback or SessionConfig()
    return SessionConfig(
        max_turns=int(raw.get('max_turns', fb.max_turns)),
        token_cap=int(raw.get('token_cap', fb.token_cap)),
        wall_timeout_s=float(raw.get('wall_timeout_s', fb.wall_timeout_s)),
        thinking_level=str(raw.get('thinking_level', fb.thinking_level)),
        model=str(raw.get('model', fb.model)),
        cost_per_session_usd=float(raw.get('cost_per_session_usd', fb.cost_per_session_usd)),
        effort=str(raw.get('effort', fb.effort)),
        max_budget_usd=float(raw.get('max_budget_usd', fb.max_budget_usd)),
        allowed_tools=tuple(str(t) for t in (raw.get('allowed_tools') or fb.allowed_tools)),
        disallowed_tools=tuple(str(t) for t in (raw.get('disallowed_tools') or fb.disallowed_tools)),
        settings_file=str(raw.get('settings_file', fb.settings_file)),
        append_system_prompt_file=str(
            raw.get('append_system_prompt_file', fb.append_system_prompt_file),
        ),
    )


def _resolve_run_dir(repo_root: Path, raw: Any, run_id: str) -> Path:
    '''Resolve run_dir; default to a sibling of the repo so git cannot reach it.'''
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate
    return (repo_root.parent / '.evolver_runs' / run_id).resolve()


def _claude_meta_template_arm(config: Config) -> str:
    if config.meta_agent_kind != 'claude_cli':
        return ''
    if config.meta_ladder_template:
        return config.meta_ladder_template
    if config.ladder_arm:
        return config.ladder_arm
    return 'A8s' if config.meta_strict_self_contained else 'A8'


def overlay_claude_meta_session(config: Config, harness_root: Path | None = None) -> str | None:
    '''Force meta block from ladder template for claude_cli arms (A8 or A8s).

    Worktree evolve/config.json is git-reset each round and may carry a stale
    permissive meta block; the harness template is the source of truth at process start.
    Returns template arm name when applied, else None.
    '''
    arm = _claude_meta_template_arm(config)
    if not arm:
        return None
    hr = (harness_root or Path(__file__).resolve().parent.parent).resolve()
    tpl = hr / 'scripts' / 'ladder_configs' / f'{arm}.json'
    if not tpl.is_file():
        return None
    raw = json.loads(tpl.read_text(encoding='utf-8'))
    meta = raw.get('meta') or {}
    meta_raw = meta.get('session') or {}
    if not meta_raw:
        return None
    config.meta_strict_self_contained = bool(meta.get('strict_self_contained', False))
    config.meta_session = _parse_session(meta_raw, fallback=config.meta_session)
    return arm


def overlay_a8_meta_session(config: Config, harness_root: Path | None = None) -> bool:
    '''Backward-compatible wrapper; True when any claude_cli overlay applied.'''
    return overlay_claude_meta_session(config, harness_root=harness_root) is not None


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
    map_elites = raw.get('map_elites', {})
    leak_raw = raw.get('leak_policy', {})
    session = _parse_session(raw.get('session', {}))
    meta_session_raw = meta.get('session') or {}
    meta_session = _parse_session(meta_session_raw, fallback=session) if meta_session_raw else session
    meta_agent_kind = str(meta.get('agent', '') or '')

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
        holdout_trigger_b4_delta=float(promotion.get('holdout_trigger_b4_delta', 0.005)),
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
        meta_agent_kind=meta_agent_kind,
        meta_strict_self_contained=bool(meta.get('strict_self_contained', False)),
        meta_ladder_template=str(meta.get('ladder_template', '')),
        ladder_arm=str(raw.get('arm', '')),
        meta_session=meta_session,
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
        map_elites_bins=int(map_elites.get('bins', 8)),
        map_elites_dims=tuple(int(d) for d in (map_elites.get('dims') or ())),
        map_elites_robust=bool(map_elites.get('robust', False)),
        leak_policy=LeakPolicy(
            enabled=bool(leak_raw.get('enabled', True)),
            stop_after_hits=int(leak_raw.get('stop_after_hits', 0)),
        ),
        rng_seed=int(raw.get('rng_seed', 20260627)),
    )
