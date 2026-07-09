'''Lean leak backstop: curated marker hashes + narrow regex (Tier A v5).

Gate surfaces: stdout + strategy snapshot (+ worktree files at pre_agent init).
Git diff / shell commands are audit-only (not scanned here).
'''
from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_SCAN_BYTES = 2 * 1024 * 1024

# SHA256 of normalized marker strings (lowercase, collapsed whitespace). Raw strings
# are never committed; tests use synthetic fixtures only.
LEAK_MARKER_HASHES: frozenset[str] = frozenset({
    '0f8e86b05af3ccb4fe3460a5edd8191480ccee0c075d0b2ec5a7eb163b66afab',
    'fb27107918e58e519a2e7d197754196a48d02d70994bd00ecbaff5758cab6beb',
    'c7e46492d197f96c67981c6f426d2461a18b8bccf8ee98cdd5fc15edfb526ec1',
    'd7788d1579b64595624a63023830678d92ff9ee15cefa92fa2c4999673f907c8',
    '1e2e26c0a0da67a0c45ec8cf710d7c915bd3d3c2d5e38215472ff9373b342213',
    '7294c74d708db1acf40c489d6fef495eac643080e417ca306889d6b6fb0778f2',
})

LEAK_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r'sweep template', re.I),
    re.compile(r'near-winner', re.I),
    re.compile(r'0\.77648', re.I),
    re.compile(r'template candidate_0019', re.I),
    re.compile(r'candidate_0019.*scored.*0\.776', re.I),
    re.compile(r'0\.776 family', re.I),
    re.compile(r'0\.776 lineage', re.I),
)

# Paths that must never appear in phase-1 init (git ls-tree / disk).
PHASE1_FORBIDDEN_PREFIXES = (
    'evolve/sweep/',
    'knowledge/',
    'results_full.tsv',
)

# Fallback purge targets (relative to worktree root).
PURGE_FORBIDDEN_RELS = (
    'evolve/sweep/template.cpp',
    'results_full.tsv',
    'knowledge',
    'progress.png',
    'progress_full.png',
)


@dataclass(frozen=True)
class LeakHit:
    surface: str
    detail: str

    def __str__(self) -> str:
        return f'{self.surface}: {self.detail}'


def normalize_text(text: str) -> str:
    return ' '.join(text.lower().split())


def marker_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode('utf-8')).hexdigest()


def read_text_safe(path: Path) -> tuple[str | None, str]:
    '''Try utf-8 → utf-8-sig → latin-1; skip binary / oversize files.'''
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f'stat failed: {exc}'
    if size > MAX_SCAN_BYTES:
        return None, 'skipped oversize'
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f'read failed: {exc}'
    if b'\x00' in raw[:8192]:
        return None, 'skipped binary'
    for enc in ('utf-8', 'utf-8-sig', 'latin-1'):
        try:
            return raw.decode(enc), ''
        except UnicodeDecodeError:
            continue
    return None, 'skipped decode'


def scan_text(text: str, *, surface: str = 'text') -> list[LeakHit]:
    hits: list[LeakHit] = []
    for line in text.splitlines():
        norm = normalize_text(line)
        if not norm:
            continue
        if hashlib.sha256(norm.encode('utf-8')).hexdigest() in LEAK_MARKER_HASHES:
            hits.append(LeakHit(surface, 'marker hash (line)'))
            return hits
        words = norm.split()
        for n in range(1, min(5, len(words) + 1)):
            for i in range(len(words) - n + 1):
                chunk = ' '.join(words[i:i + n])
                if hashlib.sha256(chunk.encode('utf-8')).hexdigest() in LEAK_MARKER_HASHES:
                    hits.append(LeakHit(surface, f'marker hash ({n}-gram)'))
                    return hits
    for pat in LEAK_REGEXES:
        m = pat.search(text)
        if m:
            hits.append(LeakHit(surface, f'regex {pat.pattern!r}: {m.group(0)!r}'))
            break
    return hits


def scan_file(path: Path, *, surface: str | None = None) -> list[LeakHit]:
    text, note = read_text_safe(path)
    if text is None:
        return []
    rel = surface or path.as_posix()
    return scan_text(text, surface=rel)


def scan_files(paths: list[Path], *, root: Path | None = None) -> list[LeakHit]:
    hits: list[LeakHit] = []
    for path in paths:
        surf = str(path.relative_to(root)) if root and path.is_relative_to(root) else str(path)
        hits.extend(scan_file(path, surface=surf))
    return hits


def walk_worktree_files(wt: Path) -> list[Path]:
    files: list[Path] = []
    for path in wt.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(wt).as_posix()
        if rel.startswith('.git/'):
            continue
        files.append(path)
    return files


def scan_worktree_files(wt: Path) -> list[LeakHit]:
    return scan_files(walk_worktree_files(wt), root=wt)


def git_ls_tree_paths(wt: Path, commit: str = 'HEAD') -> list[str]:
    out = subprocess.run(
        ['git', '-C', str(wt), 'ls-tree', '-r', '--name-only', commit],
        check=True, text=True, capture_output=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def forbidden_paths_in_tree(paths: Iterable[str], *, allow_sweep: bool = False) -> list[str]:
    issues: list[str] = []
    prefixes = PHASE1_FORBIDDEN_PREFIXES if not allow_sweep else tuple(
        p for p in PHASE1_FORBIDDEN_PREFIXES if not p.startswith('evolve/sweep')
    )
    for rel in paths:
        for prefix in prefixes:
            if rel == prefix.rstrip('/') or rel.startswith(prefix):
                issues.append(rel)
                break
    return issues


def purge_forbidden_paths(wt: Path) -> list[str]:
    '''Fallback removal of known leak vectors. Returns removed relative paths.'''
    removed: list[str] = []
    for rel in PURGE_FORBIDDEN_RELS:
        target = wt / rel
        if not target.exists():
            continue
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(rel)
    return removed
