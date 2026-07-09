'''Shared helpers for parallel Phase-2 ladder (worktrees, scratch init, seed eval).'''
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

from leak_scan import (
    forbidden_paths_in_tree,
    git_ls_tree_paths,
    purge_forbidden_paths,
    scan_worktree_files,
    walk_worktree_files,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = 'f5c7c26'
STRATEGY_COMMIT = '2c11101'
MECHANISM_COMMIT = '77d3c66'
PROGRAM_COMMIT = '2c11101'
WORKTREE_ROOT = Path(r'D:\Projects\.evolver_ladder\worktrees')
RUN_ROOT = Path(r'D:\Projects\.evolver_runs\ladder_parallel')
CONFIG_DIR = Path(__file__).resolve().parent / 'ladder_configs'
MANIFEST_PATH = RUN_ROOT / 'manifest.json'
MANIFEST_VERIFY_PATH = RUN_ROOT / 'manifest_verify.json'
ALLOWLIST_PATH = Path(__file__).resolve().parent / 'ladder_allowed_paths.txt'

RESULTS_HEADER = (
    'commit\topponent\tpoint_rate\tsearch_score\tlower_ci\tgames\tcomplexity\tstatus\tdescription\n'
)

PHASE1_ARMS = ('A0', 'A1', 'A2', 'A4', 'A5', 'A6', 'A7', 'A8', 'A8s')
EXPERIMENTAL_ARMS = ('A9',)
DEFAULT_RNG_SEED = 20260627
MIN_ABLATION_REPLICATES = 3
CONTAMINATED_BATCH = '150224'
QUARANTINE_ROOT = RUN_ROOT / '_quarantine'

SEARCH_BAND = (0.681, 0.687)
B4_BAND = (0.489, 0.495)

# Strings that must not appear in agent-visible repo files or git history.
LEAK_GIT_MARKERS = ('71069a0', '6657f53', '0.77560', '0.776', '0.826')
LEAK_TEXT_MARKERS = (
    '0.77648', '71069a0', 'near-winner', 'archive family',
    'results_full.tsv', 'Superseded', 'Archived',
)
LEAK_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r'0\.77648\s+near-winner\s+family', 'phase-1 best snapshot family'),
    (r'the\s+0\.77648\s+near-winner\s+family', 'the phase-1 best snapshot family'),
    (r'candidate_0019\s+\(the\s+0\.77648[^)]+\)', 'phase-1 best snapshot'),
    (r'0\.77648', 'best_snapshot'),
    (r'near-winner', 'best_snapshot'),
    (r'archive family', 'prior family'),
)

STAGE_EXTRA_PREFIXES: dict[str, tuple[str, ...]] = {
    'post_materialize': ('.git',),
    'post_scratch': ('.git',),
    'post_commit_init': ('.git', 'durak/build', 'durak/triage_parts', 'durak/triage.log'),
    'a3_sweep': ('.git', 'durak/build', 'durak/triage_parts', 'durak/triage.log', 'evolve/sweep'),
}


def load_allowed_paths() -> tuple[str, ...]:
    lines = ALLOWLIST_PATH.read_text(encoding='utf-8').splitlines()
    return tuple(line.strip() for line in lines if line.strip() and not line.startswith('#'))


def _path_allowed(rel: str, allowed_files: frozenset[str], extra_prefixes: tuple[str, ...]) -> bool:
    if rel in allowed_files:
        return True
    for prefix in extra_prefixes:
        p = prefix.rstrip('/')
        if rel == p or rel.startswith(p + '/'):
            return True
    return False


def unexpected_paths(
    wt: Path,
    *,
    stage: str = 'post_scratch',
    allowed_files: tuple[str, ...] | None = None,
) -> list[str]:
    '''Return relative paths in wt that are not in the allowlist union for this stage.'''
    allowed = frozenset(allowed_files or load_allowed_paths())
    extras = STAGE_EXTRA_PREFIXES.get(stage, ('.git',))
    bad: list[str] = []
    for path in walk_worktree_files(wt):
        rel = path.relative_to(wt).as_posix()
        if not _path_allowed(rel, allowed, extras):
            bad.append(rel)
    return bad


def _run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f'  $ {" ".join(cmd)}', flush=True)
    return subprocess.run(
        cmd, cwd=str(cwd), check=check, text=True,
        capture_output=not sys.stdout.isatty(),
    )


def git_show(repo: Path, commit: str, rel_path: str) -> str:
    out = subprocess.run(
        ['git', '-C', str(repo), 'show', f'{commit}:{rel_path}'],
        check=True, text=True, capture_output=True,
    )
    return out.stdout


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def assert_git_isolation(wt: Path, *, fail_on_linked: bool = True) -> dict[str, str]:
    '''Verify standalone git repo inside wt; return reachability label for manifest.'''
    git_path = wt / '.git'
    if not git_path.is_dir():
        raise RuntimeError(f'{wt.name}: .git is not a directory (linked worktree?)')

    def _resolve(flag: str) -> Path:
        out = subprocess.run(
            ['git', '-C', str(wt), 'rev-parse', flag],
            check=True, text=True, capture_output=True,
        ).stdout.strip()
        p = Path(out)
        if not p.is_absolute():
            p = (wt / p).resolve()
        else:
            p = p.resolve()
        return p

    git_dir = _resolve('--git-dir')
    common_dir = _resolve('--git-common-dir')
    if not str(git_dir).startswith(str(wt.resolve())):
        msg = f'git-dir {git_dir} outside worktree'
        if fail_on_linked:
            raise RuntimeError(msg)
        return {'reachability': 'linked', 'git_dir': str(git_dir)}
    if common_dir != git_dir and not str(common_dir).startswith(str(wt.resolve())):
        msg = f'git-common-dir {common_dir} outside worktree'
        if fail_on_linked:
            raise RuntimeError(msg)
        return {'reachability': 'linked', 'git_common_dir': str(common_dir)}

    top = subprocess.run(
        ['git', '-C', str(wt), 'rev-parse', '--show-toplevel'],
        check=True, text=True, capture_output=True,
    ).stdout.strip()
    if Path(top).resolve() != wt.resolve():
        raise RuntimeError(f'git toplevel {top} != {wt}')

    return {'reachability': 'isolated_standalone', 'git_dir': str(git_dir)}


KDELTA_RE = re.compile(r'constexpr int kDelta = (\d+);')
MAX_SWEEP_AXES = 3
THRESHOLD_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r'L\.deck_count >= (\d+)'), 'deck_ge'),
    (re.compile(r'L\.deck_count <= (\d+)'), 'deck_le'),
    (re.compile(r'L\.deck_count < (\d+)'), 'deck_lt'),
    (re.compile(r'L\.opponent_hand_count <= (\d+)'), 'opp_le'),
    (re.compile(r'rank_of\([^)]+\) >= (\d+)'), 'rank_ge'),
)


def _axis_triple(value: int, *, lo: int = 1, hi: int = 9) -> list[str]:
    vals = sorted({max(lo, value - 1), value, min(hi, value + 1)})
    return [str(v) for v in vals]


def sweep_variant_count(axes: dict[str, list[str]]) -> int:
    if not axes:
        return 1
    total = 1
    for values in axes.values():
        total *= max(1, len(values))
    return total


def prepare_per_arm_sweep_template(snapshot: str) -> tuple[str, dict[str, list[str]]]:
    '''Tokenize tunables in a phase-1 snapshot for per-arm LLM-free sweep.

    Prefer ``constexpr int kDelta`` when present; otherwise up to three threshold
    literals in deck/rank/opponent comparisons.
    '''
    axes: dict[str, list[str]] = {}
    text = snapshot

    km = KDELTA_RE.search(text)
    if km:
        val = int(km.group(1))
        token = '__SWEEP_KDELTA__'
        text = KDELTA_RE.sub(f'constexpr int kDelta = {token};', text, count=1)
        axes[token] = _axis_triple(val, lo=1, hi=6)
        return text, axes

    token_map: dict[tuple[str, int], str] = {}

    def _token(kind: str, value: int) -> str | None:
        key = (kind, value)
        if key in token_map:
            return token_map[key]
        if len(token_map) >= MAX_SWEEP_AXES:
            return None
        tok = f'__SWEEP_{len(token_map)}__'
        token_map[key] = tok
        axes[tok] = _axis_triple(value)
        return tok

    for pat, kind in THRESHOLD_RES:
        def _repl(m: re.Match[str], *, _kind: str = kind) -> str:
            val = int(m.group(1))
            tok = _token(_kind, val)
            if tok is None:
                return m.group(0)
            return m.group(0).replace(m.group(1), tok, 1)

        text = pat.sub(_repl, text)

    return text, axes


def discover_latest_phase1_run(arm: str) -> Path | None:
    '''Newest non-A3 run_dir for an arm that has an archive.'''
    best: Path | None = None
    best_mtime = 0.0
    for p in RUN_ROOT.glob(f'{arm}_*'):
        if '_A3_' in p.name or not (p / 'archive.json').exists():
            continue
        if CONTAMINATED_BATCH in p.name:
            continue
        mt = p.stat().st_mtime
        if mt > best_mtime:
            best_mtime = mt
            best = p
    return best


def load_arm_config(arm: str) -> dict[str, Any]:
    path = CONFIG_DIR / f'{arm}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def arm_rng_seed(arm: str, replicate: int = 0) -> int:
    '''Harness RNG seed for one replicate (shared base across arms; +replicate offset).'''
    base = int(load_arm_config(arm).get('rng_seed', DEFAULT_RNG_SEED))
    return base + replicate


def manifest_spawn_id(arm: str, replicate: int, *, replicates: int) -> str:
    if replicates <= 1:
        return arm
    return f'{arm}@r{replicate}'


def parse_manifest_arm(spawn_id: str) -> str:
    '''Base arm label from manifest key (``A6@r1`` -> ``A6``).'''
    return spawn_id.split('@r', 1)[0]


def manifest_spawn_ids(manifest_arms: dict[str, Any], requested: list[str]) -> list[str]:
    '''Resolve manifest keys to spawn for requested base arms (incl. replicates).'''
    ids: list[str] = []
    for arm in requested:
        rep_keys = sorted(
            k for k in manifest_arms
            if k == arm or k.startswith(f'{arm}@r')
        )
        if rep_keys:
            ids.extend(rep_keys)
        else:
            ids.append(arm)
    return ids


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def scrub_leaky_text(text: str) -> str:
    '''Remove jun22 ladder anchors from text copied into isolated worktrees.'''
    out = text
    for pattern, repl in LEAK_TEXT_REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def git_history_leaks(wt: Path) -> list[str]:
    '''Return issues if git log exposes main-repo ladder history.'''
    issues: list[str] = []
    for extra in ([], ['--all']):
        cmd = ['git', '-C', str(wt), 'log', '--oneline', *extra, '-50']
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        for marker in LEAK_GIT_MARKERS:
            if marker in out:
                issues.append(f'git log {" ".join(extra)} contains {marker!r}')
    return issues


def tree_text_leaks(wt: Path) -> list[str]:
    '''Scan agent-readable repo files for forbidden substrings (legacy wrapper).'''
    hits = scan_worktree_files(wt)
    return [str(h) for h in hits]


def verify_leak_free(
    wt: Path,
    *,
    stage: str = 'post_commit_init',
    allow_sweep: bool = False,
    pre_agent: bool = True,
) -> list[str]:
    '''Full pre_agent verification: paths, git ls-tree, marker scan.'''
    issues: list[str] = []

    extra = unexpected_paths(wt, stage=stage)
    if extra:
        issues.append(f'unexpected paths ({stage}): {extra[:5]}' + (f' +{len(extra)-5} more' if len(extra) > 5 else ''))

    try:
        tree_paths = git_ls_tree_paths(wt)
    except subprocess.CalledProcessError as exc:
        issues.append(f'git ls-tree failed: {exc}')
        tree_paths = []

    for rel in forbidden_paths_in_tree(tree_paths, allow_sweep=allow_sweep):
        issues.append(f'forbidden in git tree: {rel}')

    if pre_agent:
        for hit in scan_worktree_files(wt):
            issues.append(str(hit))

    issues.extend(git_history_leaks(wt))
    return issues


def _paths_in_commit(main_repo: Path, commit: str, paths: list[str]) -> tuple[list[str], list[str]]:
    '''Split allowlist into paths present at *commit* vs copy-from-working-tree.'''
    in_commit: list[str] = []
    from_worktree: list[str] = []
    for rel in paths:
        ok = subprocess.run(
            ['git', '-C', str(main_repo), 'cat-file', '-e', f'{commit}:{rel}'],
            capture_output=True,
            check=False,
        ).returncode == 0
        if ok:
            in_commit.append(rel)
        else:
            from_worktree.append(rel)
    return in_commit, from_worktree


def _copy_paths_from_repo(wt: Path, main_repo: Path, paths: list[str]) -> None:
    for rel in paths:
        src = main_repo / rel
        if not src.exists():
            raise RuntimeError(f'allowlist path missing in repo working tree: {rel}')
        dest = wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)


def materialize_base_tree(wt: Path, main_repo: Path) -> None:
    '''Extract only audited allowlist paths at BASE_COMMIT (no shell interpolation).'''
    wt.mkdir(parents=True, exist_ok=True)
    paths = list(load_allowed_paths())
    if not paths:
        raise RuntimeError(f'empty allowlist: {ALLOWLIST_PATH}')
    in_commit, from_worktree = _paths_in_commit(main_repo, BASE_COMMIT, paths)
    if from_worktree:
        print(
            f'  copy from working tree (not in {BASE_COMMIT}): {from_worktree}',
            flush=True,
        )
    cmd = ['git', '-C', str(main_repo), 'archive', '--format=tar', BASE_COMMIT, '--', *in_commit]
    print(f'  $ git archive {BASE_COMMIT} -- [{len(in_commit)} paths]', flush=True)
    if in_commit:
        proc = subprocess.run(cmd, check=True, capture_output=True)
        with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode='r') as tf:
            tf.extractall(path=wt)
    if from_worktree:
        _copy_paths_from_repo(wt, main_repo, from_worktree)
    purge_forbidden_paths(wt)
    bad = unexpected_paths(wt, stage='post_materialize')
    if bad:
        raise RuntimeError(f'unexpected paths after materialize: {bad[:3]}')


def populate_base_tree(wt: Path, main_repo: Path) -> None:
    '''Legacy alias — use materialize_base_tree (exact allowlist only).'''
    materialize_base_tree(wt, main_repo)


def _rmtree_force(path: Path) -> None:
    '''Remove a directory tree on Windows (clears read-only git objects).'''
    import stat

    def _onerror(func, p, _exc_info):  # noqa: ANN001
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onerror=_onerror)


def run_dir_is_contaminated(path: Path, *, batch: str = CONTAMINATED_BATCH) -> bool:
    '''True if run_dir name or quarantine label marks a contaminated batch.'''
    if batch and batch in path.name:
        return True
    if (path / 'QUARANTINED.txt').exists():
        return True
    qcopy = QUARANTINE_ROOT / path.name
    return qcopy.is_dir() and (qcopy / 'QUARANTINED.txt').exists()


def run_dir_is_overlay_eligible(path: Path) -> bool:
    '''Exclude quarantine dirs, verify stubs, and known contaminated batches.'''
    name = path.name
    if name.startswith('_'):
        return False
    if '_verify' in name:
        return False
    if run_dir_is_contaminated(path):
        return False
    return True


def discover_overlay_runs(base: Path) -> dict[str, Path]:
    '''Map arm label -> latest overlay-eligible run_dir under base.'''
    import re

    found: dict[str, tuple[float, Path]] = {}
    if not base.exists():
        return {}
    for p in base.iterdir():
        if not p.is_dir():
            continue
        if p.name == '_quarantine':
            continue
        if not run_dir_is_overlay_eligible(p):
            continue
        m = re.match(r'^(A\d+s?)(?:_A3)?_', p.name)
        if not m:
            continue
        arm = m.group(1)
        is_a3 = '_A3_' in p.name
        label = f'{arm}_A3' if is_a3 else arm
        ts = p.stat().st_mtime
        prev = found.get(label)
        if prev is None or ts > prev[0]:
            found[label] = (ts, p)
    return {k: v[1] for k, v in found.items()}


def discover_legacy_arm_run(
    base: Path,
    arm: str,
    *,
    exclude_batch: str = '162509',
) -> Path | None:
    '''Best legacy/quarantine run for an arm (for overlay column-2 overrides).

    Prefers _quarantine/, then QUARANTINED.txt, then contaminated batch, then
    highest round count. Skips the clean batch (default 162509).
    '''
    import re

    candidates: list[Path] = []
    for root in (QUARANTINE_ROOT, base):
        if not root.is_dir():
            continue
        for p in root.iterdir():
            if not p.is_dir():
                continue
            if not re.match(rf'^{re.escape(arm)}_', p.name) or '_A3_' in p.name:
                continue
            if exclude_batch and exclude_batch in p.name:
                continue
            candidates.append(p)
    if not candidates:
        return None

    def _sort_key(p: Path) -> tuple[int, int, int]:
        in_q = int(p.parent.name == '_quarantine' or (p / 'QUARANTINED.txt').exists())
        rnd = 0
        state_path = p / 'state.json'
        if state_path.exists():
            rnd = int(json.loads(state_path.read_text(encoding='utf-8')).get('round') or 0)
        contaminated = int(CONTAMINATED_BATCH in p.name)
        return (in_q, rnd, contaminated)

    return max(candidates, key=_sort_key)


def quarantine_contaminated_runs(
    arms: tuple[str, ...] = ('A1', 'A2', 'A4', 'A5'),
    batch: str = CONTAMINATED_BATCH,
) -> list[Path]:
    '''Move contaminated run dirs to RUN_ROOT/_quarantine/ (read-only label).'''
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for arm in arms:
        for run_dir in sorted(RUN_ROOT.glob(f'{arm}_*{batch}*')):
            if '_A3_' in run_dir.name or not run_dir.is_dir():
                continue
            dest = QUARANTINE_ROOT / run_dir.name
            if dest.exists():
                if run_dir.exists():
                    print(
                        f'[quarantine] removing duplicate contaminated run from RUN_ROOT: '
                        f'{run_dir.name}',
                        flush=True,
                    )
                    _rmtree_force(run_dir)
                if dest not in moved:
                    moved.append(dest)
                continue
            print(f'[quarantine] {run_dir.name} -> {dest}', flush=True)
            shutil.move(str(run_dir), str(dest))
            label = dest / 'QUARANTINED.txt'
            label.write_text(
                f'contaminated batch={batch}; do not use for overlay or A3 parent\n',
                encoding='utf-8',
            )
            moved.append(dest)
    return moved


def unsafe_restore_quarantined_runs(
    arms: tuple[str, ...] = ('A1', 'A2', 'A4', 'A5'),
    batch: str = CONTAMINATED_BATCH,
    *,
    i_know_this_is_contaminated: bool = False,
) -> list[Path]:
    '''Move quarantined phase-1 run dirs back to RUN_ROOT (forensic use only).

    Requires ``i_know_this_is_contaminated=True`` — restored runs must not feed
    overlay or A3 parent selection.
    '''
    if not i_know_this_is_contaminated:
        raise RuntimeError(
            'refusing restore: pass i_know_this_is_contaminated=True '
            '(restored runs are contaminated and must not feed overlay/A3)'
        )
    restored: list[Path] = []
    if not QUARANTINE_ROOT.exists():
        return restored
    for arm in arms:
        for qdir in sorted(QUARANTINE_ROOT.glob(f'{arm}_*{batch}*')):
            if '_A3_' in qdir.name or not qdir.is_dir():
                continue
            dest = RUN_ROOT / qdir.name
            if dest.exists():
                print(f'[restore] skip {qdir.name}: already at {dest}', flush=True)
                continue
            print(f'[restore] {qdir.name} -> {dest}', flush=True)
            shutil.move(str(qdir), str(dest))
            restored.append(dest)
    return restored


def destroy_arm_repo(label: str, main_repo: Path) -> None:
    '''Remove an arm directory (legacy linked worktree or isolated git repo).'''
    wt = WORKTREE_ROOT / label
    if not wt.exists():
        return
    git_path = wt / '.git'
    if git_path.is_file():
        _run(['git', 'worktree', 'remove', '--force', str(wt)], cwd=main_repo, check=False)
        for branch in (f'ladder/{label}', f'scratch/{label}'):
            _run(['git', 'branch', '-D', branch], cwd=main_repo, check=False)
    else:
        _rmtree_force(wt)


def _git_init_isolated(wt: Path, branch: str) -> None:
    '''Fresh git repo with no shared refs to the main ladder history.'''
    wt.mkdir(parents=True, exist_ok=True)
    _run(['git', 'init', '-b', branch], cwd=wt)
    _run(['git', 'config', 'user.email', 'dimitry@bobyard.com'], cwd=wt)
    _run(['git', 'config', 'user.name', 'Dimitry'], cwd=wt)


def sweep_template_text(main_repo: Path) -> str:
    src = main_repo / 'evolve/sweep/template.cpp'
    if not src.exists():
        return ''
    return scrub_leaky_text(src.read_text(encoding='utf-8'))


def apply_scrubbed_sweep_template(wt: Path, main_repo: Path) -> None:
    text = sweep_template_text(main_repo)
    if not text:
        return
    dest = wt / 'evolve/sweep/template.cpp'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding='utf-8')


def apply_scratch_files(wt: Path, main_repo: Path) -> None:
    '''Overlay jun22-clean files onto an isolated scratch repo.'''
    pairs = [
        ('durak/src/strategy_heuristic.cpp', STRATEGY_COMMIT),
        ('program.md', PROGRAM_COMMIT),
        ('evolve/mechanism/evolve_skill.md', MECHANISM_COMMIT),
        ('evolve/mechanism/family_map.md', MECHANISM_COMMIT),
    ]
    for rel, commit in pairs:
        dest = wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(git_show(main_repo, commit, rel), encoding='utf-8')

    (wt / 'results.tsv').write_text(RESULTS_HEADER, encoding='utf-8')
    full = wt / 'results_full.tsv'
    if full.exists():
        full.unlink()

    scores = wt / 'scores.json'
    if scores.exists():
        scores.unlink()

    sweep_tpl = wt / 'evolve/sweep/template.cpp'
    if sweep_tpl.exists():
        sweep_tpl.unlink()


def git_commit_all(wt: Path, message: str) -> str:
    _run(['git', 'add', '-A'], cwd=wt)
    _run(['git', 'commit', '-m', message], cwd=wt)
    out = subprocess.run(
        ['git', '-C', str(wt), 'rev-parse', 'HEAD'],
        check=True, text=True, capture_output=True,
    )
    return out.stdout.strip()


def prebuild(wt: Path) -> None:
    print(f'[prebuild] {wt.name}', flush=True)
    _run(['cmd', '/c', 'durak\\build.bat', 'fast', 'test'], cwd=wt)


def fresh_seed_eval(wt: Path) -> tuple[float, float, float]:
    '''Gate-3 full eval on the scratch seed (NOT quick).'''
    sys.path.insert(0, str(REPO_ROOT))
    from evolver.config import load_config
    from evolver.evaluate import RealEvaluator

    config = load_config(repo_root=wt)
    ev = RealEvaluator(config)
    ok, reason = ev.precheck()
    if not ok:
        raise RuntimeError(f'seed precheck failed: {reason}')
    print('[seed] run_full (Gate 3)...', flush=True)
    full = ev.run_full()
    if full is None:
        raise RuntimeError('seed run_full failed')
    print(
        f'[seed] search={full.search_score:.5f} b4={full.point_rate_b4:.5f} '
        f'lower_ci={full.lower_ci:.5f}',
        flush=True,
    )
    return full.search_score, full.point_rate_b4, full.lower_ci


def write_baseline_config(wt: Path, arm: str, baseline: tuple[float, float, float]) -> None:
    cfg = load_arm_config(arm)
    cfg['baseline'] = {
        'best_search': baseline[0],
        'best_b4': baseline[1],
        'best_lower_ci': baseline[2],
    }
    write_json(wt / 'evolve' / 'config.json', cfg)


def init_worktree(
    arm: str,
    main_repo: Path,
    *,
    force: bool = False,
) -> Path:
    wt = WORKTREE_ROOT / arm
    if wt.exists() and not force:
        return wt
    destroy_arm_repo(arm, main_repo)
    wt = WORKTREE_ROOT / arm
    materialize_base_tree(wt, main_repo)
    bad = unexpected_paths(wt, stage='post_materialize')
    if bad:
        raise RuntimeError(f'{arm} unexpected after materialize: {bad[0]}')
    _git_init_isolated(wt, f'scratch/{arm}')
    apply_scratch_files(wt, main_repo)
    if arm_uses_claude_meta(arm):
        arm_cfg = load_arm_config(arm)
        materialize_claude_meta_mechanism(
            wt, main_repo, strict=_is_strict_claude_meta(arm_cfg),
        )
    _purge_family_map_for_arm(arm, wt)
    bad = unexpected_paths(wt, stage='post_scratch')
    if bad:
        raise RuntimeError(f'{arm} unexpected after scratch: {bad[0]}')
    write_json(wt / 'evolve' / 'config.json', load_arm_config(arm))
    git_commit_all(wt, f'scratch: {arm} from-scratch init')
    prebuild(wt)
    baseline = fresh_seed_eval(wt)
    write_baseline_config(wt, arm, baseline)
    git_commit_all(wt, f'scratch: {arm} jun22 seed baseline eval')
    iso = assert_git_isolation(wt)
    leaks = verify_leak_free(wt, stage='post_commit_init', allow_sweep=False)
    if leaks:
        raise RuntimeError(f'{arm} leak check failed after init: {leaks[0]}')
    print(f'[init] {arm} reachability={iso.get("reachability")}', flush=True)
    return wt


def arm_uses_claude_meta(arm: str) -> bool:
    cfg = load_arm_config(arm)
    meta = cfg.get('meta') or {}
    return str(meta.get('agent', '')).strip() == 'claude_cli'


def _is_strict_claude_meta(cfg: dict[str, Any]) -> bool:
    meta = cfg.get('meta') or {}
    return (
        str(meta.get('agent', '')).strip() == 'claude_cli'
        and bool(meta.get('strict_self_contained', False))
    )


def read_worktree_config(wt: Path) -> dict[str, Any]:
    cfg_path = wt / 'evolve' / 'config.json'
    if not cfg_path.is_file():
        return {}
    return json.loads(cfg_path.read_text(encoding='utf-8'))


def resolve_template_arm(cfg: dict[str, Any], *, wt_name: str = '') -> str:
    '''Resolve ladder template arm from materialized config (not directory name).'''
    meta = cfg.get('meta') or {}
    ladder_template = str(meta.get('ladder_template', '')).strip()
    if ladder_template:
        return ladder_template
    arm_field = str(cfg.get('arm', '')).strip()
    if arm_field:
        return arm_field
    if str(meta.get('agent', '')).strip() == 'claude_cli':
        return 'A8s' if bool(meta.get('strict_self_contained', False)) else 'A8'
    return wt_name.strip()


def _purge_family_map_for_arm(arm: str, wt: Path) -> None:
    '''A9 v1: remove family_map.md from strict pilot worktree only.'''
    if arm != 'A9':
        return
    fm = wt / 'evolve' / 'mechanism' / 'family_map.md'
    if fm.is_file():
        fm.unlink()


def materialize_claude_meta_mechanism(
    wt: Path,
    main_repo: Path,
    *,
    strict: bool,
) -> None:
    mech = wt / 'evolve' / 'mechanism'
    mech.mkdir(parents=True, exist_ok=True)
    if strict:
        for name in (
            'a8s_meta_constitution.md',
            'a8s_meta_skill.md',
            'a8_meta_claude_settings.json',
        ):
            src = main_repo / 'evolve' / 'mechanism' / name
            if src.is_file():
                (mech / name).write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
        seed = main_repo / 'evolve' / 'mechanism' / 'evolve_skill_a8s.md'
        if seed.is_file():
            (mech / 'evolve_skill.md').write_text(
                seed.read_text(encoding='utf-8'), encoding='utf-8',
            )
    else:
        for name in ('a8_meta_constitution.md', 'a8_meta_claude_settings.json'):
            src = main_repo / 'evolve' / 'mechanism' / name
            if src.is_file():
                (mech / name).write_text(src.read_text(encoding='utf-8'), encoding='utf-8')


def validate_replicate_concurrency(replicates: int, max_concurrent: int) -> str | None:
    '''Shared worktree replicates require serial spawn.'''
    if replicates > 1 and max_concurrent > 1:
        return (
            'shared worktree: replicates > 1 require max_concurrent == 1 '
            f'(got replicates={replicates}, max_concurrent={max_concurrent})'
        )
    return None


def resolve_cursor_agent_exe() -> str:
    '''Match ``CursorCliAgent._resolve_exe`` (local install, session auth).'''
    found = shutil.which('cursor-agent')
    if found:
        return found
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidate = Path(local) / 'cursor-agent' / 'cursor-agent.cmd'
        if candidate.exists():
            return str(candidate)
    return 'cursor-agent'


def preflight_cursor_cli(*, repo_root: Path | None = None) -> list[str]:
    '''Smoke check for local ``cursor-agent`` (bobyard JWT via ``cursor_cli_env``).

    Strips host ``CURSOR_API_KEY``, injects IDE ``CURSOR_AUTH_TOKEN``, model ``auto``.
    Returns failure messages (empty = OK).
    '''
    issues: list[str] = []
    repo_root = (repo_root or REPO_ROOT).resolve()
    sys.path.insert(0, str(REPO_ROOT))
    from evolver.util import cursor_cli_env
    exe = resolve_cursor_agent_exe()
    if exe == 'cursor-agent' and shutil.which('cursor-agent') is None:
        default = Path(os.environ.get('LOCALAPPDATA', '')) / 'cursor-agent' / 'cursor-agent.cmd'
        if not default.exists():
            issues.append('cursor-agent not on PATH and default install missing')
            return issues

    base = [
        exe, '-p', '--force', '--trust',
        '--output-format', 'stream-json',
        '--model', 'auto',
        '--workspace', str(repo_root),
    ]
    cmd = ['cmd', '/c', *base] if os.name == 'nt' else base
    prompt = 'respond with OK'

    print('[preflight] cursor-agent smoke (session auth)...', flush=True)
    print(f'[preflight] {" ".join(cmd)}', flush=True)

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            env=cursor_cli_env(),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        issues.append('cursor-agent preflight timed out after 120s')
        return issues

    combined = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode != 0:
        tail = combined.strip()[-800:]
        issues.append(f'cursor-agent preflight failed (exit={proc.returncode}): {tail}')
        return issues

    if not any('"type"' in line for line in combined.splitlines()):
        issues.append('cursor-agent preflight: no stream-json events (login required?)')

    return issues


def preflight_claude_cli(*, arm: str = 'A8', repo_root: Path | None = None) -> list[str]:
    '''Smoke check with the same ``claude -p`` flags as production meta sessions.

    Uses ``--max-turns 1`` and a harmless prompt on stdin (matching ``ClaudeCliAgent.run``).
    Returns a list of failure messages (empty = OK).
    '''
    issues: list[str] = []
    if shutil.which('claude') is None:
        issues.append('claude not on PATH')
        return issues

    repo_root = (repo_root or REPO_ROOT).resolve()
    sys.path.insert(0, str(REPO_ROOT))
    from dataclasses import replace

    from evolver.agents import AgentContext, ClaudeCliAgent
    from evolver.config import load_config

    cfg_file = repo_root / 'evolve' / 'config.json'
    if not cfg_file.exists():
        issues.append(f'missing {cfg_file}')
        return issues

    config = load_config(repo_root)
    if (config.meta_agent_kind or '').strip() != 'claude_cli':
        issues.append(f'{arm}: meta agent is not claude_cli')
        return issues

    append_rel = config.meta_session.append_system_prompt_file
    if append_rel and not (repo_root / append_rel).exists():
        issues.append(f'missing append_system_prompt_file: {append_rel}')

    smoke_session = replace(config.meta_session, max_turns=1)
    agent = ClaudeCliAgent(config, session=smoke_session)
    ctx = AgentContext(
        repo_root=repo_root,
        strategy_rel=config.meta_target,
        prompt='respond with OK',
        phi='',
        round_idx=0,
        parent_id=None,
    )
    cmd = agent._command(ctx)
    prompt = 'respond with OK'

    print(f'[preflight] claude meta smoke ({arm})...', flush=True)
    print(f'[preflight] {" ".join(cmd)}', flush=True)

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(repo_root),
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        issues.append('claude preflight timed out after 180s')
        return issues

    combined = (proc.stdout or '') + (proc.stderr or '')
    if proc.returncode != 0:
        tail = combined.strip()[-800:]
        issues.append(f'claude preflight failed (exit={proc.returncode}): {tail}')
        return issues

    for line in reversed(combined.splitlines()):
        stripped = line.strip()
        if not stripped.startswith('{'):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if event.get('type') == 'result':
            if event.get('is_error'):
                msg = str(event.get('result') or event.get('subtype') or 'unknown error')
                issues.append(f'claude preflight result error: {msg[:300]}')
            break

    return issues


def verify_worktree(arm: str, wt: Path, run_dir: Path | None = None) -> list[str]:
    '''Return list of verification failures (empty = OK).'''
    sys.path.insert(0, str(REPO_ROOT))
    from evolver.observe import load_rejected_directions

    fails: list[str] = []
    try:
        iso = assert_git_isolation(wt)
        if iso.get('reachability') != 'isolated_standalone':
            fails.append(f'{arm}: reachability={iso.get("reachability")}')
    except RuntimeError as exc:
        fails.append(f'{arm}: {exc}')

    top = subprocess.run(
        ['git', '-C', str(wt), 'rev-parse', '--show-toplevel'],
        check=True, text=True, capture_output=True,
    ).stdout.strip()
    if Path(top).resolve() != wt.resolve():
        fails.append(f'{arm}: worktree toplevel mismatch')

    if run_dir is not None:
        try:
            run_dir.resolve().relative_to(wt.resolve())
            fails.append(f'{arm}: run_dir inside worktree')
        except ValueError:
            pass

    if MANIFEST_PATH.resolve().is_relative_to(wt.resolve()):
        fails.append(f'{arm}: manifest inside worktree')

    tree_paths = git_ls_tree_paths(wt)
    if any(p.startswith('evolve/sweep/') for p in tree_paths):
        fails.append(f'{arm}: evolve/sweep/ in init commit')

    fails.extend(verify_leak_free(wt, stage='post_commit_init', allow_sweep=False))

    if (wt / 'CLAUDE.md').exists():
        fails.append(f'{arm}: CLAUDE.md present in worktree')

    strat = (wt / 'durak/src/strategy_heuristic.cpp').read_text(encoding='utf-8')
    ref = git_show(REPO_ROOT, STRATEGY_COMMIT, 'durak/src/strategy_heuristic.cpp')
    if file_hash(strat) != file_hash(ref):
        fails.append(f'{arm}: strategy hash != 2c11101')

    cfg = json.loads((wt / 'evolve/config.json').read_text(encoding='utf-8'))
    promo = cfg.get('promotion', {})
    if float(promo.get('holdout_trigger_delta', -1)) != 0.006:
        fails.append(f'{arm}: holdout_trigger_delta != 0.006')
    bl = cfg.get('baseline', {})
    bs = float(bl.get('best_search', 0))
    bb = float(bl.get('best_b4', 0))
    if not (SEARCH_BAND[0] <= bs <= SEARCH_BAND[1]):
        fails.append(f'{arm}: baseline search {bs:.5f} outside {SEARCH_BAND}')
    if not (B4_BAND[0] <= bb <= B4_BAND[1]):
        fails.append(f'{arm}: baseline b4 {bb:.5f} outside {B4_BAND}')

    if load_rejected_directions(wt):
        fails.append(f'{arm}: rejected directions non-empty')

    return fails


def save_manifest(entries: dict[str, Any]) -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(MANIFEST_PATH, entries)


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def best_official_from_run(run_dir: Path) -> dict[str, Any] | None:
    '''Return the archive row with highest search_score among official_best.'''
    path = run_dir / 'archive.json'
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding='utf-8'))
    bests = [r for r in rows if r.get('status') == 'official_best']
    if not bests:
        return None
    return max(bests, key=lambda r: float(r.get('search_score') or 0))


def snapshot_for_candidate(run_dir: Path, cid: str) -> str:
    snap = run_dir / 'candidates' / cid / 'snapshot.cpp'
    return snap.read_text(encoding='utf-8') if snap.exists() else ''


def init_a3_worktree(
    arm: str,
    phase1_run_dir: Path,
    main_repo: Path,
    *,
    force: bool = False,
) -> Path | None:
    '''Fresh A3 worktree from phase-1 best official_best snapshot.'''
    if CONTAMINATED_BATCH in phase1_run_dir.name:
        print(f'[A3] {arm}: refusing contaminated parent run {phase1_run_dir.name}', flush=True)
        return None

    best = best_official_from_run(phase1_run_dir)
    if best is None:
        print(f'[A3] {arm}: no official_best in {phase1_run_dir.name}, skip', flush=True)
        return None

    wt = WORKTREE_ROOT / f'{arm}_A3'
    if wt.exists() and not force:
        return wt
    destroy_arm_repo(f'{arm}_A3', main_repo)

    wt = WORKTREE_ROOT / f'{arm}_A3'
    materialize_base_tree(wt, main_repo)
    _git_init_isolated(wt, f'scratch/{arm}_A3')
    apply_scratch_files(wt, main_repo)

    snap = snapshot_for_candidate(phase1_run_dir, best['id'])
    if not snap:
        print(f'[A3] {arm}: missing snapshot for {best["id"]}, skip', flush=True)
        return None

    strat_path = wt / 'durak/src/strategy_heuristic.cpp'
    strat_path.write_text(snap, encoding='utf-8')

    sweep_tpl, sweep_axes = prepare_per_arm_sweep_template(snap)
    sweep_path = wt / 'evolve/sweep/template.cpp'
    sweep_path.parent.mkdir(parents=True, exist_ok=True)
    sweep_path.write_text(scrub_leaky_text(sweep_tpl), encoding='utf-8')

    cfg = json.loads((CONFIG_DIR / 'A3_sweep.json').read_text(encoding='utf-8'))
    bl_search = float(best.get('search_score') or 0)
    bl_b4 = float(best.get('point_rate_b4') or 0)
    bl_ci = float(best.get('lower_ci') or 0)
    cfg['baseline'] = {
        'best_search': bl_search,
        'best_b4': bl_b4,
        'best_lower_ci': bl_ci,
    }
    n_variants = sweep_variant_count(sweep_axes)
    cfg['max_rounds'] = max(n_variants + 2, 5)
    cfg.setdefault('sweep', {})['template'] = 'evolve/sweep/template.cpp'
    cfg['sweep']['axes'] = sweep_axes
    write_json(wt / 'evolve/config.json', cfg)
    git_commit_all(wt, f'scratch: {arm}_A3 best={best["id"]} search={bl_search:.5f}')
    print(
        f'[A3] {arm}: sweep from {best["id"]} variants={n_variants} axes={list(sweep_axes)}',
        flush=True,
    )
    prebuild(wt)
    assert_git_isolation(wt)
    leaks = verify_leak_free(wt, stage='a3_sweep', allow_sweep=True)
    if leaks:
        raise RuntimeError(f'{arm}_A3 leak check failed after init: {leaks[0]}')
    return wt


def refresh_a3_config(wt: Path) -> None:
    '''Rewrite evolve/config.json from template, preserving measured baseline + sweep axes.'''
    cfg_path = wt / 'evolve/config.json'
    existing = json.loads(cfg_path.read_text(encoding='utf-8'))
    baseline = existing.get('baseline', {})
    sweep_block = existing.get('sweep', {})
    cfg = json.loads((CONFIG_DIR / 'A3_sweep.json').read_text(encoding='utf-8'))
    if baseline:
        cfg['baseline'] = baseline
    if sweep_block.get('axes'):
        cfg.setdefault('sweep', {})['axes'] = sweep_block['axes']
        if sweep_block.get('template'):
            cfg['sweep']['template'] = sweep_block['template']
    if existing.get('max_rounds'):
        cfg['max_rounds'] = existing['max_rounds']
    write_json(cfg_path, cfg)


def refresh_claude_meta_config(wt: Path) -> None:
    '''Rewrite claude_cli meta session from ladder template; preserve baseline/max_rounds.'''
    cfg_path = wt / 'evolve' / 'config.json'
    if not cfg_path.exists():
        return
    existing = read_worktree_config(wt)
    meta = existing.get('meta') or {}
    if str(meta.get('agent', '')).strip() != 'claude_cli':
        return
    tpl_arm = resolve_template_arm(existing, wt_name=wt.name)
    tpl = load_arm_config(tpl_arm)
    cfg = existing
    cfg['meta'] = tpl['meta']
    if existing.get('baseline'):
        cfg['baseline'] = existing['baseline']
    if existing.get('max_rounds'):
        cfg['max_rounds'] = existing['max_rounds']
    write_json(cfg_path, cfg)
    materialize_claude_meta_mechanism(
        wt, REPO_ROOT, strict=_is_strict_claude_meta(cfg),
    )


def refresh_a8_meta_config(wt: Path) -> None:
    '''Backward-compatible alias for refresh_claude_meta_config.'''
    refresh_claude_meta_config(wt)


def scrub_phase1_worktree(wt: Path) -> None:
    '''Remove agent-visible leak vectors before an overnight phase-1 continue.'''
    purge_forbidden_paths(wt)
    if (wt / '.git').exists():
        _run(['git', 'add', '-A'], cwd=wt, check=False)
        dirty = subprocess.run(
            ['git', '-C', str(wt), 'status', '--porcelain'],
            capture_output=True, text=True,
        ).stdout.strip()
        if dirty:
            _run(['git', 'commit', '-m', 'ladder: scrub leak vectors (no sweep template)'], cwd=wt)


def prepare_phase1_continue(
    wt: Path,
    run_dir: Path,
    *,
    max_rounds: int = 200,
    disable_convergence: bool = True,
) -> list[str]:
    '''Scrub leaks, extend budget, clear stop flag; return remaining leak issues.'''
    refresh_a8_meta_config(wt)
    scrub_phase1_worktree(wt)

    cfg_path = wt / 'evolve/config.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    cfg['max_rounds'] = max(max_rounds, int(cfg.get('max_rounds') or 0) + 1)
    if disable_convergence:
        cfg.setdefault('convergence', {})['enabled'] = False
    write_json(cfg_path, cfg)

    state_path = run_dir / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        state['finished'] = False
        state['max_rounds'] = cfg['max_rounds']
        write_json(state_path, state)

    stop_flag = run_dir / 'stop.flag'
    if stop_flag.exists():
        stop_flag.unlink()

    return verify_leak_free(wt, stage='post_commit_init', allow_sweep=False)


def _ladder_subprocess_env() -> dict[str, str]:
    sys.path.insert(0, str(REPO_ROOT))
    from evolver.util import cursor_cli_env

    env = cursor_cli_env(os.environ.copy())
    env['PYTHONUNBUFFERED'] = '1'
    return env


def spawn_continue_arm(
    arm: str,
    wt: Path,
    run_dir: Path,
    *,
    python: str | None = None,
) -> subprocess.Popen[Any]:
    py = python or sys.executable
    env = _ladder_subprocess_env()
    log_path = run_dir / 'launcher.stdout.log'
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        py, '-m', 'evolver.cli', 'continue',
        '--repo-root', str(wt),
        '--run-dir', str(run_dir),
    ]
    print(f'[continue] {arm} -> {run_dir}', flush=True)
    log_f = open(log_path, 'a', encoding='utf-8')  # noqa: SIM115
    log_f.write(f'\n=== continue {time.strftime("%Y-%m-%d %H:%M:%S")} ===\n')
    log_f.flush()
    return subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=log_f, stderr=subprocess.STDOUT)


def spawn_arm(
    arm: str,
    wt: Path,
    run_dir: Path,
    *,
    python: str | None = None,
    rng_seed: int | None = None,
    max_rounds: int | None = None,
) -> subprocess.Popen[Any]:
    py = python or sys.executable
    env = _ladder_subprocess_env()
    log_path = run_dir / 'launcher.stdout.log'
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        py, '-m', 'evolver.cli', 'run',
        '--repo-root', str(wt),
        '--no-results-baseline',
        '--run-dir', str(run_dir),
        '--run-id', run_dir.name,
    ]
    if rng_seed is not None:
        cmd.extend(['--rng-seed', str(rng_seed)])
    if max_rounds is not None:
        cmd.extend(['--max-rounds', str(max_rounds)])
    print(f'[spawn] {arm} rng_seed={rng_seed} max_rounds={max_rounds} -> {run_dir}', flush=True)
    log_f = open(log_path, 'w', encoding='utf-8')  # noqa: SIM115
    return subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=log_f, stderr=subprocess.STDOUT)
