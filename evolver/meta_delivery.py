'''Meta-delivery invariant: diagnostics, root identity, structured audit records.

Invariant: COMPLETED meta session + changed mechanism file => meta commit exists.
Until that holds, A8 is a harness-integration test, not a research ablation.
'''
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .protect import VersionControl
from .util import append_jsonl, log, run_command

META_ROUNDS_JSONL = 'meta_rounds.jsonl'
META_TARGET_SUFFIX = 'evolve/mechanism/evolve_skill.md'

_FORBIDDEN_META_TOOLS = frozenset({
    'Write', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Glob', 'Grep', 'ToolSearch',
})

_META_DENY_EXTRA = (
    'Read(*family_map.md)',
    'Read(**/family_map.md)',
    'Read(**\\family_map.md)',
    'Read(*meta_skill.md)',
    'Read(**/meta_skill.md)',
    'Read(**\\meta_skill.md)',
    'Read(*strategy_heuristic.cpp)',
    'Read(**/strategy_heuristic.cpp)',
    'Read(**\\strategy_heuristic.cpp)',
    'Read(*durak*)',
    'Read(**/durak/**)',
    'Read(**\\durak\\**)',
    'ToolSearch(*)',
)

_MEMORY_MARKERS = (
    '/.claude/', '\\.claude\\', '/memory/', '\\memory\\',
    'memory.md', 'memory\\',
)

_OUT_OF_SCOPE_MARKERS = (
    '.evolver_runs', '/evolver/', 'evolver/', 'archive.json', 'results.tsv',
)


@dataclass(frozen=True)
class ScopeViolation:
    message: str
    after_edit: bool
    ts: float = 0.0


@dataclass(frozen=True)
class ScopeScanResult:
    violations: tuple[ScopeViolation, ...]

    @property
    def messages(self) -> tuple[str, ...]:
        return tuple(v.message for v in self.violations)

    def outcome(self) -> str | None:
        if not self.violations:
            return None
        before = any(not v.after_edit for v in self.violations)
        after = any(v.after_edit for v in self.violations)
        if before and after:
            return 'scope_violation_before_and_after_edit'
        if after:
            return 'scope_violation_after_edit'
        return 'scope_violation_before_edit'


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ''
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_toplevel(repo_root: Path) -> str:
    result = run_command(['git', 'rev-parse', '--show-toplevel'], cwd=repo_root)
    if not result.ok:
        return ''
    return Path(result.stdout.strip()).resolve().as_posix()


def git_porcelain(repo_root: Path) -> str:
    result = run_command(['git', 'status', '--porcelain=v1'], cwd=repo_root)
    return (result.stdout or '').strip()


def mechanism_diff_text(vc: VersionControl, base: str, target_rel: str) -> str:
    return vc.diff_paths(base, target_rel)


def root_identity_ok(expected: Path, observed_toplevel: str) -> bool:
    if not observed_toplevel:
        return False
    return Path(observed_toplevel).resolve() == expected.resolve()


def _norm_path(raw: str) -> str:
    return raw.replace('\\', '/').lower()


def _is_evolve_skill_path(raw: str, target_rel: str = META_TARGET_SUFFIX) -> bool:
    norm = _norm_path(raw)
    target = _norm_path(target_rel)
    return target in norm or norm.endswith('evolve_skill.md')


def _memory_path(raw: str) -> bool:
    if '*' in raw:
        return False
    low = _norm_path(raw)
    return any(m.replace('\\', '/').lower() in low for m in _MEMORY_MARKERS)


def _strict_bash_allowed(raw: str, target_rel: str = META_TARGET_SUFFIX) -> bool:
    low = raw.lower()
    if 'git commit' in low:
        return False
    norm = _norm_path(raw)
    if 'git diff' in low and _norm_path(target_rel) in norm:
        return True
    if 'git status' in low and 'porcelain' in low:
        return True
    return False


def tool_access_violation(
    tool_name: str,
    raw: str,
    repo_root: Path,
    *,
    strict_meta: bool = False,
    target_rel: str = META_TARGET_SUFFIX,
) -> str | None:
    '''Return violation description, or None when the tool use is in scope.'''
    low = _norm_path(raw)
    if tool_name in _FORBIDDEN_META_TOOLS:
        return f'forbidden tool {tool_name}'
    if _memory_path(raw):
        return f'memory path blocked: {raw[:120]}'
    if '../' in low or '/..' in low or low.startswith('..'):
        return f'parent traversal in {tool_name}: {raw[:120]}'
    for marker in _OUT_OF_SCOPE_MARKERS:
        if marker in low:
            return f'out-of-scope path ({marker}): {raw[:120]}'
    if raw.startswith('/') or (len(raw) > 2 and raw[1] == ':'):
        try:
            resolved = Path(raw).resolve()
            resolved.relative_to(repo_root.resolve())
        except (OSError, ValueError):
            return f'path outside worktree: {raw[:120]}'
    if strict_meta:
        if tool_name == 'Read':
            if not _is_evolve_skill_path(raw, target_rel):
                return f'meta read outside contract: {raw[:120]}'
        elif tool_name == 'Edit':
            if not _is_evolve_skill_path(raw, target_rel):
                return f'meta edit outside contract: {raw[:120]}'
        elif tool_name == 'Bash':
            if not _strict_bash_allowed(raw, target_rel):
                return f'forbidden bash: {raw[:120]}'
    return None


def scan_meta_tools_audit(
    audit_path: Path,
    repo_root: Path,
    *,
    since_ts: float = 0.0,
    target_rel: str = META_TARGET_SUFFIX,
    strict_meta: bool = True,
) -> ScopeScanResult:
    if not audit_path.is_file():
        return ScopeScanResult(())
    violations: list[ScopeViolation] = []
    first_edit_ts: float | None = None
    for line in audit_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = float(rec.get('ts') or 0.0)
        if ts < since_ts:
            continue
        tool = str(rec.get('tool') or '')
        raw = str(rec.get('raw') or '')
        if tool == 'Edit' and _is_evolve_skill_path(raw, target_rel):
            if first_edit_ts is None:
                first_edit_ts = ts
        if rec.get('parent_traversal'):
            after = first_edit_ts is not None and ts >= first_edit_ts
            violations.append(ScopeViolation(
                f'meta_tools parent_traversal: {tool} {raw[:120]}',
                after_edit=after,
                ts=ts,
            ))
            continue
        violation = tool_access_violation(
            tool, raw, repo_root, strict_meta=strict_meta, target_rel=target_rel,
        )
        if violation:
            after = first_edit_ts is not None and ts >= first_edit_ts
            violations.append(ScopeViolation(violation, after_edit=after, ts=ts))
    return ScopeScanResult(tuple(violations))


def collect_post_agent_diagnostics(
    vc: VersionControl,
    repo_root: Path,
    best_commit: str,
    target_rel: str,
    *,
    hash_before: str,
    status: str,
) -> dict[str, Any]:
    target = repo_root / target_rel
    hash_after = file_sha256(target)
    toplevel = git_toplevel(repo_root)
    allowlist_diff = vc.diff_allowlist(best_commit)
    mech_diff = mechanism_diff_text(vc, best_commit, target_rel)
    return {
        'status': status,
        'cwd_expected': str(repo_root.resolve()),
        'git_toplevel': toplevel,
        'root_identity_ok': root_identity_ok(repo_root, toplevel),
        'git_status_porcelain': git_porcelain(repo_root),
        'file_hash_before': hash_before,
        'file_hash_after': hash_after,
        'file_changed': hash_before != hash_after,
        'mechanism_diff_len': len(mech_diff),
        'allowlist_diff_len': len(allowlist_diff.strip()),
        'mechanism_diff_preview': mech_diff[:500],
    }


def log_post_agent_diagnostics(round_idx: int, diag: dict[str, Any]) -> None:
    log(f'  META post-agent round {round_idx}: '
        f'status={diag["status"]} root_ok={diag["root_identity_ok"]} '
        f'hash_before={diag["file_hash_before"][:12]} '
        f'hash_after={diag["file_hash_after"][:12]} '
        f'allowlist_diff_len={diag["allowlist_diff_len"]}')
    if diag.get('git_status_porcelain'):
        log(f'  META git_status: {diag["git_status_porcelain"][:200]}')


def record_meta_round(run_dir: Path | None, record: dict[str, Any]) -> None:
    if run_dir is None:
        return
    append_jsonl(run_dir / META_ROUNDS_JSONL, record)


def empty_patch_detail(diag: dict[str, Any]) -> str:
    return (
        f'file_hash_before={diag["file_hash_before"][:12]} '
        f'file_hash_after={diag["file_hash_after"][:12]} '
        f'file_changed={diag["file_changed"]} '
        f'allowlist_diff_len={diag["allowlist_diff_len"]} '
        f'root_ok={diag["root_identity_ok"]}'
    )


def materialize_meta_settings(
    repo_root: Path,
    settings_rel: str,
    harness_root: Path,
) -> Path | None:
    '''Ensure settings JSON exists in the worktree (git reset may drop untracked copies).'''
    if not settings_rel:
        return None
    dest = Path(settings_rel)
    if not dest.is_absolute():
        dest = repo_root / dest
    if dest.is_file():
        return dest.resolve()
    template = harness_root / 'evolve' / 'mechanism' / 'a8_meta_claude_settings.json'
    if not template.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')
    return dest.resolve()


def expand_meta_allowed_tools(
    base: tuple[str, ...],
    repo_root: Path,
    target_rel: str,
) -> tuple[str, ...]:
    '''Add resolved absolute paths so Windows live reads match allow rules.'''
    skill = (repo_root / target_rel).resolve()
    extras = (
        f'Read({skill.as_posix()})',
        f'Edit({skill.as_posix()})',
        f'Read({skill})',
        f'Edit({skill})',
    )
    seen: set[str] = set()
    out: list[str] = []
    for rule in (*base, *extras):
        if rule and rule not in seen:
            seen.add(rule)
            out.append(rule)
    return tuple(out)


def expand_meta_disallowed_tools(base: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for rule in (*base, *_META_DENY_EXTRA):
        if rule and rule not in seen:
            seen.add(rule)
            out.append(rule)
    return tuple(out)


def meta_command_fingerprint(cmd: list[str]) -> dict[str, str]:
    display = cmd[3:] if len(cmd) >= 3 and cmd[0] == 'cmd' and cmd[1] == '/c' else cmd
    joined = ' '.join(display)
    allowed = ''
    disallowed = ''
    settings = ''
    for i, token in enumerate(display):
        if token == '--allowedTools' and i + 1 < len(display):
            allowed = display[i + 1]
        elif token == '--disallowedTools' and i + 1 < len(display):
            disallowed = display[i + 1]
        elif token == '--settings' and i + 1 < len(display):
            settings = display[i + 1]
    return {
        'argv_sha256': hashlib.sha256(joined.encode('utf-8')).hexdigest()[:16],
        'allowed_tools': allowed[:500],
        'disallowed_tools': disallowed[:800],
        'settings_path': settings,
        'has_settings': str(bool(settings)),
    }
