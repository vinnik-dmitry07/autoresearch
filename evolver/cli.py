'''Command-line entry point: `python -m evolver.cli {run|status|continue|stop}`.

The driver owns termination; `stop` is an EXTERNAL operator control (a flag the loop
checks at round boundaries), never an agent-owned stop.
'''
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, find_repo_root, load_config, overlay_claude_meta_session
from .evaluate import read_best_from_results
from .util import log, read_json


def _latest_run_dir(repo_root: Path) -> Path | None:
    base = repo_root.parent / '.evolver_runs'
    if not base.exists():
        return None
    runs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def _apply_results_baseline(config: Config) -> None:
    '''Raise the run baseline to the best row in results.tsv (never lower it).'''
    best = read_best_from_results(config.repo_root)
    if best is not None and best[0] > config.best_search:
        config.best_search, config.best_b4, config.best_lower_ci = best
        log(f'baseline from results.tsv: search={best[0]:.5f} b4={best[1]:.5f} lower_ci={best[2]:.5f}')


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    if getattr(args, 'repo_root', None):
        return Path(args.repo_root).resolve()
    return find_repo_root()


def _cmd_run(args: argparse.Namespace) -> int:
    from .agents import make_agent, make_meta_agent
    from .loop import Loop

    repo_root = _resolve_repo_root(args)
    overrides: dict[str, object] = {}
    if args.max_rounds is not None:
        overrides['max_rounds'] = args.max_rounds
    if args.k is not None:
        overrides['K'] = args.k
    if args.rng_seed is not None:
        overrides['rng_seed'] = args.rng_seed
    if args.run_dir is not None:
        overrides['run_dir'] = args.run_dir
    config = load_config(repo_root=repo_root, run_id=args.run_id, overrides=overrides)
    arm_tpl = overlay_claude_meta_session(config)
    if arm_tpl:
        log(f'  meta session overlay: scripts/ladder_configs/{arm_tpl}.json (claude_cli)')
    if not getattr(args, 'no_results_baseline', False):
        _apply_results_baseline(config)
    return Loop(
        config, agent_factory=make_agent, meta_agent_factory=make_meta_agent,
    ).run()


def _cmd_continue(args: argparse.Namespace) -> int:
    from .agents import make_agent, make_meta_agent
    from .loop import Loop

    repo_root = _resolve_repo_root(args)
    run_dir = Path(args.run_dir).resolve() if args.run_dir else _latest_run_dir(repo_root)
    if run_dir is None or not run_dir.exists():
        log('no run to continue; start one with `run`')
        return 1
    overrides: dict[str, object] = {'run_dir': str(run_dir)}
    if args.max_rounds is not None:
        overrides['max_rounds'] = args.max_rounds
    config = load_config(repo_root=repo_root, overrides=overrides)
    arm_tpl = overlay_claude_meta_session(config)
    if arm_tpl:
        log(f'  meta session overlay: scripts/ladder_configs/{arm_tpl}.json (claude_cli)')
    return Loop(
        config, agent_factory=make_agent, meta_agent_factory=make_meta_agent,
    ).run(resume=True)


def _cmd_status(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args)
    run_dir = Path(args.run_dir).resolve() if args.run_dir else _latest_run_dir(repo_root)
    if run_dir is None or not run_dir.exists():
        log('no runs found')
        return 1
    state = read_json(run_dir / 'state.json', default={})
    log(f'run_dir: {run_dir}')
    for key in ('round', 'max_rounds', 'cost_usd', 'cost_cap_usd', 'best_id', 'best_search', 'finished'):
        if key in state:
            log(f'  {key}: {state[key]}')
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    repo_root = _resolve_repo_root(args)
    run_dir = Path(args.run_dir).resolve() if args.run_dir else _latest_run_dir(repo_root)
    if run_dir is None or not run_dir.exists():
        log('no run to stop')
        return 1
    (run_dir / 'stop.flag').write_text('stop requested by operator\n', encoding='utf-8')
    log(f'stop flag written; the loop will halt at the next round boundary ({run_dir})')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='evolver', description='Durak evolution harness')
    sub = parser.add_subparsers(dest='command', required=True)

    run = sub.add_parser('run', help='start a new run')
    run.add_argument('--run-id', default=None)
    run.add_argument('--run-dir', default=None)
    run.add_argument('--repo-root', default=None, help='git worktree root (default: cwd repo)')
    run.add_argument('--no-results-baseline', action='store_true',
                     help='do not raise baseline from repo results.tsv')
    run.add_argument('--max-rounds', type=int, default=None)
    run.add_argument('--k', type=int, default=None)
    run.add_argument('--rng-seed', type=int, default=None, help='harness RNG seed (parent/sweep selection)')
    run.set_defaults(func=_cmd_run, no_results_baseline=False)

    cont = sub.add_parser('continue', help='resume the latest (or given) run')
    cont.add_argument('--run-dir', default=None)
    cont.add_argument('--repo-root', default=None)
    cont.add_argument('--max-rounds', type=int, default=None,
                      help='raise round budget when extending a finished run')
    cont.set_defaults(func=_cmd_continue)

    status = sub.add_parser('status', help='print run state')
    status.add_argument('--run-dir', default=None)
    status.add_argument('--repo-root', default=None)
    status.set_defaults(func=_cmd_status)

    stop = sub.add_parser('stop', help='request an external halt at the next round boundary')
    stop.add_argument('--run-dir', default=None)
    stop.add_argument('--repo-root', default=None)
    stop.set_defaults(func=_cmd_stop)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == '__main__':
    sys.exit(main())
