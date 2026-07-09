#!/usr/bin/env python
'''Overlay jun22 reference + parallel ladder arms on progress.png.

Fairness rules (plan v2):
  - jun22 frontier: status == keep, cummax on B4 rows
  - arm frontier: status == official_best AND score_kind in (baseline, full)
  - scatter: jun22 discard (grey); arms valid_stepping_stone (arm-tinted)
  - manual: jun22 keep/discard mapped to round axis in cols 2–3 (≤200)
  - dispersion (col 3): dashed below-frontier deviation, vertically joined at promotions

Layout: 2×3 — jun22 | arms (frontier+scatter) | arms (neg deviation only);
jun22 and arm panels in each row share y-axis scale.

Usage:
  python scripts/overlay_ladder_progress.py
'''
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ladder_lib import (  # noqa: E402
    REPO_ROOT,
    RUN_ROOT,
    SEARCH_BAND,
    discover_legacy_arm_run,
    discover_overlay_runs,
)

DEFAULT_REF = 'git:bccde74:results.tsv'
DEFAULT_OUT = REPO_ROOT / 'progress.png'
FRONTIER_KINDS = {'baseline', 'full'}
ARM_X_MAX = 200.0  # cap all phase-1 arm curves and scatter at this round
A3_PLOT_X = 20.0  # unused when A3 sweep runs are excluded from overlay
# Column-2 overrides: A6/A7 use legacy/quarantine runs (not clean batch 162509).
COL2_LEGACY_ARMS = ('A6', 'A7')
MANUAL_LABEL = 'manual'
MANUAL_X_MAX = ARM_X_MAX

_TAB10 = [mcolors.to_hex(plt.cm.tab10(i)) for i in range(10)]
_ARM_ORDER = ('A0', 'A1', 'A2', 'A4', 'A5', 'A6', 'A7', 'A8', 'A8s', 'A9')
COLORS = {arm: _TAB10[i] for i, arm in enumerate(_ARM_ORDER)}
COLORS['manual'] = '#000000'
COLORS['jun22'] = '#000000'


def load_reference(path_spec: str) -> pd.DataFrame:
    if path_spec.startswith('git:'):
        spec = path_spec[4:]
        text = subprocess.run(
            ['git', '-C', str(REPO_ROOT), 'show', spec],
            check=True, text=True, capture_output=True,
        ).stdout
        from io import StringIO
        df = pd.read_csv(StringIO(text), sep='\t', dtype=str)
    else:
        df = pd.read_csv(path_spec, sep='\t', dtype=str)
    for col in ('point_rate', 'search_score', 'lower_ci', 'games', 'complexity'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['status'] = df['status'].str.strip().str.lower()
    return df


def load_arm_b4(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, float]:
    '''Return (all_b4, frontier, scatter, x_end_round) for one arm run_dir.'''
    tsv = run_dir / 'results.tsv'
    archive = run_dir / 'archive.json'
    if not tsv.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 0.0

    df = pd.read_csv(tsv, sep='\t', dtype=str)
    for col in ('point_rate', 'search_score', 'lower_ci', 'games', 'complexity'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['status'] = df['status'].str.strip().str.lower()
    df['commit'] = df['commit'].str.strip()
    b4 = df[df['opponent'].str.strip() == 'B4'].copy().reset_index(drop=True)

    kind_map: dict[str, str] = {}
    round_map: dict[str, int] = {}
    if archive.exists():
        import json
        for row in json.loads(archive.read_text(encoding='utf-8')):
            kind_map[row['id']] = row.get('score_kind') or ''
            round_map[row['id']] = int(row.get('round') or 0)

    b4['score_kind'] = b4['commit'].map(kind_map).fillna('')
    b4['round'] = b4['commit'].map(round_map).fillna(0).astype(int)
    b4 = _assign_exp_ids(b4)
    frontier = b4[
        (b4['status'] == 'official_best')
        & (b4['score_kind'].isin(FRONTIER_KINDS))
    ].copy()
    scatter = b4[
        (b4['status'] == 'valid_stepping_stone')
    ].copy()
    x_end = _run_x_end(run_dir, b4)
    return b4, frontier, scatter, x_end


def _run_x_end(run_dir: Path, b4: pd.DataFrame) -> float:
    '''Last round index for step-line extension (state.round when available).'''
    state_path = run_dir / 'state.json'
    if state_path.exists():
        import json
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('round') is not None:
            return float(state['round'])
    if not b4.empty:
        return float(b4['round'].max()) + 1.0
    return 0.0


def _assign_exp_ids(b4: pd.DataFrame) -> pd.DataFrame:
    '''Single experiment index for all rows (frontier + scatter share x).'''
    if b4.empty:
        return b4
    out = b4.copy()
    out['_ord'] = out['commit'].str.extract(r'(\d+)$').astype(float)
    out = out.sort_values('_ord').reset_index(drop=True)
    out['exp_id'] = np.arange(len(out))
    return out.drop(columns=['_ord'])


def discover_runs(base: Path) -> dict[str, Path]:
    '''Map arm label -> latest eligible run_dir (skips quarantine/contaminated batches).'''
    return discover_overlay_runs(base)


def jun22_as_arm(
    ref_b4: pd.DataFrame,
    x_max: float = MANUAL_X_MAX,
) -> tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]:
    '''Map jun22 manual-loop B4 rows onto the arms round axis (round := exp_id).'''
    b4 = ref_b4[ref_b4['exp_id'] <= x_max].copy()
    b4['round'] = b4['exp_id'].astype(int)
    keep = b4[b4['status'] == 'keep'].copy()
    disc = b4[b4['status'] == 'discard'].copy()
    frontier = keep.copy()
    frontier['status'] = 'official_best'
    frontier['score_kind'] = 'full'
    scatter = disc.copy()
    scatter['status'] = 'valid_stepping_stone'
    scatter['score_kind'] = 'search'
    x_end = min(float(b4['exp_id'].max()) + 1.0 if len(b4) else 0.0, x_max)
    return frontier, scatter, x_end, b4


def _arm_color(label: str) -> str:
    if label == MANUAL_LABEL:
        return COLORS['manual']
    return COLORS.get(label.split('_')[0], '#333333')


def _clip_arm_round(df: pd.DataFrame, x_max: float = ARM_X_MAX) -> pd.DataFrame:
    if df.empty or 'round' not in df.columns:
        return df
    return df[df['round'] <= x_max].copy()


def _cap_x_end(x_end: float, x_max: float = ARM_X_MAX) -> float:
    return min(x_end, x_max)


def _is_a3(label: str) -> bool:
    return '_A3' in label


def _frontier_step(
    frontier: pd.DataFrame,
    y_col: str,
    x_end: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    '''Cummax frontier on round axis; last plateau extends flat to x_end when given.'''
    if frontier.empty:
        return np.array([]), np.array([])
    fr = frontier.sort_values(['round', 'commit'])
    xs: list[float] = []
    ys: list[float] = []
    running = fr[y_col].cummax()
    for rnd, y in zip(fr['round'], running):
        rnd_f = float(rnd)
        if xs and rnd_f == xs[-1]:
            ys[-1] = float(y)
        else:
            xs.append(rnd_f)
            ys.append(float(y))
    if x_end is not None and xs and float(x_end) > xs[-1]:
        xs.append(float(x_end))
        ys.append(ys[-1])
    return np.array(xs), np.array(ys)


def _frontier_plateau_deviation(
    frontier: pd.DataFrame,
    scatter: pd.DataFrame,
    y_col: str,
    x_end: float,
    x_max: float = ARM_X_MAX,
) -> list[tuple[float, float, float, float, float]]:
    '''Per horizontal plateau: (x_start, x_end, frontier_y, mean_above, mean_below).'''
    plot_end = min(float(x_end), x_max)
    xs, ys = _frontier_step(frontier, y_col, plot_end)
    if len(xs) < 2 or scatter.empty or y_col not in scatter.columns:
        return []
    sc = scatter[(scatter['round'] <= x_max) & scatter[y_col].notna()].copy()
    if sc.empty:
        return []

    bands: list[tuple[float, float, float, float, float]] = []
    for i in range(len(xs) - 1):
        x_start = float(xs[i])
        x_stop = float(xs[i + 1])
        y_level = float(ys[i])
        is_last = i == len(xs) - 2
        if is_last:
            mask = (sc['round'] >= x_start) & (sc['round'] <= x_max)
        else:
            mask = (sc['round'] >= x_start) & (sc['round'] < x_stop)
        pts = sc.loc[mask, y_col].to_numpy(dtype=float)
        if pts.size == 0:
            bands.append((x_start, x_stop, y_level, 0.0, 0.0))
            continue
        above = pts[pts > y_level] - y_level
        below = y_level - pts[pts < y_level]
        pos_dev = float(np.mean(above)) if above.size else 0.0
        neg_dev = float(np.mean(below)) if below.size else 0.0
        bands.append((x_start, x_stop, y_level, pos_dev, neg_dev))
    return bands


def self_check(arm: str, frontier: pd.DataFrame) -> list[str]:
    warns: list[str] = []
    if _is_a3(arm) or arm == MANUAL_LABEL:
        return warns
    if frontier.empty:
        warns.append(f'{arm}: no official_best frontier rows')
        return warns
    first = frontier.sort_values('commit')['search_score'].iloc[0]
    if not (SEARCH_BAND[0] <= first <= SEARCH_BAND[1]):
        warns.append(
            f'{arm}: first frontier search {first:.5f} outside {SEARCH_BAND} (engine drift?)'
        )
    return warns


def _jun22_frontier_step(
    ref_keep: pd.DataFrame,
    y_col: str,
    x_end: float,
) -> tuple[np.ndarray, np.ndarray]:
    '''Keep cummax extended horizontally to last experiment index.'''
    if ref_keep.empty:
        return np.array([]), np.array([])
    ks = ref_keep.sort_values('exp_id')
    xs = ks['exp_id'].to_numpy(dtype=float)
    ys = ks[y_col].cummax().to_numpy(dtype=float)
    if xs[-1] < x_end:
        xs = np.append(xs, x_end)
        ys = np.append(ys, ys[-1])
    return xs, ys


def _plot_jun22_point_rate(ax: plt.Axes, ref_b4: pd.DataFrame, ref_keep: pd.DataFrame) -> None:
    ref_disc = ref_b4[ref_b4['status'] == 'discard']
    ax.scatter(ref_disc['exp_id'], ref_disc['point_rate'], c='#cccccc', s=15, alpha=0.5,
               label='discard')
    ax.scatter(ref_keep['exp_id'], ref_keep['point_rate'], c='#2ecc71', s=40, zorder=3,
               label='keep', edgecolors='black', linewidths=0.3)
    if len(ref_keep):
        x_end = float(ref_b4['exp_id'].max()) if len(ref_b4) else 0.0
        xs, ys = _jun22_frontier_step(ref_keep, 'point_rate', x_end)
        ax.step(xs, ys, where='post',
                color=COLORS['jun22'], linewidth=2, alpha=0.8, label='frontier')
    ax.axhline(0.50, color='#888', linestyle='--', linewidth=0.8, alpha=0.5)
    ax.set_ylabel('B4 point_rate')
    ax.set_title('jun22 manual loop')
    ax.legend(loc='lower right', fontsize=7)
    ax.grid(True, alpha=0.2)


def _plot_jun22_search(ax: plt.Axes, ref_b4: pd.DataFrame, ref_keep: pd.DataFrame) -> None:
    ref_disc = ref_b4[ref_b4['status'] == 'discard']
    ax.scatter(ref_disc['exp_id'], ref_disc['search_score'], c='#cccccc', s=15, alpha=0.5)
    ax.scatter(ref_keep['exp_id'], ref_keep['search_score'], c='#3498db', s=40, zorder=3,
               label='keep', edgecolors='black', linewidths=0.3)
    if len(ref_keep):
        x_end = float(ref_b4['exp_id'].max()) if len(ref_b4) else 0.0
        xs, ys = _jun22_frontier_step(ref_keep, 'search_score', x_end)
        ax.step(xs, ys, where='post',
                color=COLORS['jun22'], linewidth=2, alpha=0.8, label='frontier')
    ax.axhline(0.52, color='#888', linestyle='--', linewidth=0.8, alpha=0.5)
    ax.set_xlabel('experiment # (jun22)')
    ax.set_ylabel('search_score (composite − complexity)')
    ax.legend(loc='lower right', fontsize=7)
    ax.grid(True, alpha=0.2)


def _a3_sweep_step(
    b4: pd.DataFrame,
    y_col: str,
    x_base: float = A3_PLOT_X,
) -> tuple[np.ndarray, np.ndarray]:
    '''Cummax of best score per round over A3 sweep, x offset after phase-1.'''
    if b4.empty or y_col not in b4.columns:
        return np.array([]), np.array([])
    valid = b4[b4['status'].str.strip().str.lower() != 'invalid'].copy()
    if valid.empty:
        return np.array([]), np.array([])
    by_round = (
        valid.groupby('round', as_index=False)[y_col]
        .max()
        .sort_values('round')
    )
    ys = by_round[y_col].cummax().to_numpy(dtype=float)
    xs = x_base + by_round['round'].astype(float).to_numpy()
    return xs, ys


def _a3_best_y(b4: pd.DataFrame, frontier: pd.DataFrame, y_col: str) -> float | None:
    '''Best B4 score seen in A3 sweep (any non-invalid row), else official frontier.'''
    xs, ys = _a3_sweep_step(b4, y_col)
    if len(ys):
        return float(ys[-1])
    if frontier.empty or y_col not in frontier.columns:
        return None
    fr = frontier.sort_values(['round', 'commit'])
    return float(fr[y_col].cummax().iloc[-1])


def _a3_legend_label(label: str) -> str:
    return f'{label.split("_")[0]}-sweep'


def _set_arms_xlim(
    ax: plt.Axes,
    arm_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]],
) -> None:
    ax.set_xlim(0, ARM_X_MAX)


def _collect_row_ys(
    ref_keep: pd.DataFrame,
    arm_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]],
    y_col: str,
) -> list[float]:
    '''Y values for shared row ylim: keep/frontier lines only (not grey scatter).'''
    ys: list[float] = []
    if len(ref_keep) and y_col in ref_keep.columns:
        ys.extend(ref_keep[y_col].dropna().tolist())
        ys.append(float(ref_keep[y_col].cummax().max()))
    for label, (frontier, scatter, _x_end, b4) in arm_data.items():
        if _is_a3(label):
            y = _a3_best_y(b4, frontier, y_col)
            if y is not None:
                ys.append(y)
            continue
        if frontier.shape[0] and y_col in frontier.columns:
            fr = _clip_arm_round(frontier)
            if fr.shape[0]:
                ys.extend(fr[y_col].cummax().dropna().tolist())
        elif not _is_a3(label):
            sc = _clip_arm_round(scatter)
            if sc.shape[0] and y_col in sc.columns:
                ys.extend(sc[y_col].dropna().tolist())
    return [y for y in ys if y > 0]


def _shared_ylim(ys: list[float], pad_frac: float = 0.04) -> tuple[float, float] | None:
    if not ys:
        return None
    lo, hi = float(min(ys)), float(max(ys))
    span = hi - lo
    pad = span * pad_frac if span > 0 else 0.01
    return lo - pad, hi + pad


def _apply_row_ylim(
    axes_row: tuple[plt.Axes, ...],
    ylim: tuple[float, float] | None,
) -> None:
    if ylim is None:
        return
    for ax in axes_row:
        ax.set_ylim(ylim)


def _neg_deviation_polyline(
    frontier: pd.DataFrame,
    scatter: pd.DataFrame,
    y_col: str,
    x_end: float,
) -> tuple[np.ndarray, np.ndarray]:
    '''Connected dashed path: horizontal at frontier−mean(below), vertical at promotions.'''
    bands = _frontier_plateau_deviation(frontier, scatter, y_col, x_end)
    if not bands:
        return np.array([]), np.array([])

    xs_line: list[float] = []
    ys_line: list[float] = []
    for i, (x0, x1, y_lvl, _pos, neg_dev) in enumerate(bands):
        y_dash = float(y_lvl) - float(neg_dev)
        if i == 0:
            xs_line.extend([x0, x1])
            ys_line.extend([y_dash, y_dash])
            continue
        xs_line.extend([x0, x0, x1])
        ys_line.extend([ys_line[-1], y_dash, y_dash])
    return np.array(xs_line), np.array(ys_line)


def _plot_arm_neg_deviation(
    ax: plt.Axes,
    label: str,
    frontier: pd.DataFrame,
    scatter: pd.DataFrame,
    y_col: str,
    x_end: float,
) -> None:
    '''Dashed polyline at frontier − mean(below), vertical joins at promotions.'''
    if _is_a3(label):
        return
    c = _arm_color(label)
    frontier = _clip_arm_round(frontier)
    scatter = _clip_arm_round(scatter)
    x_plot_end = _cap_x_end(x_end)
    xs, ys = _neg_deviation_polyline(frontier, scatter, y_col, x_plot_end)
    if len(xs) == 0:
        return
    ax.plot(
        xs, ys, linestyle='--', color=c, linewidth=1.0, alpha=0.85,
        label=label, zorder=3,
    )


def _plot_arm_series(
    ax: plt.Axes,
    label: str,
    frontier: pd.DataFrame,
    scatter: pd.DataFrame,
    y_col: str,
    x_end: float,
    b4: pd.DataFrame,
) -> None:
    c = _arm_color(label)
    if _is_a3(label):
        y_best = _a3_best_y(b4, frontier, y_col)
        if y_best is None:
            return
        ax.scatter(
            [A3_PLOT_X], [y_best], marker='x', c=c, s=28,
            linewidths=1.2, label=_a3_legend_label(label), zorder=6,
        )
        return

    x_col = 'round'
    scatter = _clip_arm_round(scatter)
    frontier = _clip_arm_round(frontier)
    x_plot_end = _cap_x_end(x_end)
    if scatter.shape[0]:
        ax.scatter(
            scatter[x_col], scatter[y_col], c=c, s=6, alpha=0.3,
            marker='o', linewidths=0, zorder=3,
        )
    if frontier.shape[0]:
        xs, ys = _frontier_step(frontier, y_col, x_plot_end)
        ax.step(xs, ys, where='post', color=c, linewidth=1.5, alpha=0.9, label=label, zorder=4)


def _plot_arms_neg_deviation(
    ax: plt.Axes,
    arm_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]],
    y_col: str,
    *,
    xlabel: str = '',
) -> None:
    for label, (frontier, scatter, x_end, b4) in arm_data.items():
        _plot_arm_neg_deviation(ax, label, frontier, scatter, y_col, x_end)
    ax.axhline(0.50 if y_col == 'point_rate' else 0.52,
               color='#888', linestyle='--', linewidth=0.8, alpha=0.5)
    _set_arms_xlim(ax, arm_data)
    ax.set_title('evolver arms — dashed below-frontier (joined)')
    ax.legend(loc='lower right', fontsize=6, ncol=2)
    ax.grid(True, alpha=0.2)
    if xlabel:
        ax.set_xlabel(xlabel)


def _plot_arms_point_rate(
    ax: plt.Axes,
    arm_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]],
) -> None:
    for label, (frontier, scatter, x_end, b4) in arm_data.items():
        _plot_arm_series(ax, label, frontier, scatter, 'point_rate', x_end, b4)
    ax.axhline(0.50, color='#888', linestyle='--', linewidth=0.8, alpha=0.5)
    _set_arms_xlim(ax, arm_data)
    ax.set_ylabel('B4 point_rate')
    ax.set_title('evolver arms — phase-1 frontier + scatter')
    ax.legend(loc='lower right', fontsize=6, ncol=2)
    ax.grid(True, alpha=0.2)


def _plot_arms_search(
    ax: plt.Axes,
    arm_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]],
) -> None:
    for label, (frontier, scatter, x_end, b4) in arm_data.items():
        _plot_arm_series(ax, label, frontier, scatter, 'search_score', x_end, b4)
    ax.axhline(0.52, color='#888', linestyle='--', linewidth=0.8, alpha=0.5)
    _set_arms_xlim(ax, arm_data)
    ax.set_xlabel('round # (phase-1)')
    ax.set_ylabel('search_score (composite − complexity)')
    ax.legend(loc='lower right', fontsize=6, ncol=2)
    ax.grid(True, alpha=0.2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', default=DEFAULT_REF)
    parser.add_argument('--runs', type=Path, default=RUN_ROOT)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    ref = load_reference(args.reference)
    ref_b4 = ref[ref['opponent'].str.strip() == 'B4'].copy().reset_index(drop=True)
    ref_b4['exp_id'] = np.arange(len(ref_b4))
    ref_keep = ref_b4[ref_b4['status'] == 'keep'].copy()

    runs = discover_runs(args.runs)
    if not runs:
        print(f'no arm run dirs under {args.runs}', flush=True)

    for arm in COL2_LEGACY_ARMS:
        legacy = discover_legacy_arm_run(args.runs, arm)
        if legacy is not None:
            runs[arm] = legacy
            print(f'[col2 legacy] {arm} -> {legacy.name}', flush=True)

    arm_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame]] = {}
    all_warns: list[str] = []
    for label, run_dir in sorted(runs.items()):
        if '_A3' in label:
            continue
        b4, frontier, scatter, x_end = load_arm_b4(run_dir)
        arm_data[label] = (frontier, scatter, _cap_x_end(x_end), b4)
        all_warns.extend(self_check(label, frontier))
        print(
            f'{label}: frontier={len(frontier)} scatter={len(scatter)} '
            f'x_end={_cap_x_end(x_end):.0f} dir={run_dir.name}',
            flush=True,
        )

    mf, ms, mx, mb4 = jun22_as_arm(ref_b4, MANUAL_X_MAX)
    arm_data[MANUAL_LABEL] = (mf, ms, mx, mb4)
    print(
        f'{MANUAL_LABEL}: frontier={len(mf)} scatter={len(ms)} x_end={mx:.0f} '
        f'source=jun22_manual_loop (cols 2–3)',
        flush=True,
    )

    for w in all_warns:
        print(f'WARN: {w}', flush=True)

    if args.dry_run:
        return 0

    fig, axes = plt.subplots(2, 3, figsize=(26, 10))
    fig.suptitle(
        'Parallel ladder: jun22 | arms frontier | below-frontier deviation',
        fontsize=12,
    )

    _plot_jun22_point_rate(axes[0, 0], ref_b4, ref_keep)
    _plot_arms_point_rate(axes[0, 1], arm_data)
    _plot_arms_neg_deviation(axes[0, 2], arm_data, 'point_rate')
    axes[0, 2].set_ylabel('B4 point_rate')

    _plot_jun22_search(axes[1, 0], ref_b4, ref_keep)
    _plot_arms_search(axes[1, 1], arm_data)
    _plot_arms_neg_deviation(
        axes[1, 2], arm_data, 'search_score',
        xlabel='round # (phase-1)',
    )
    axes[1, 2].set_ylabel('search_score (composite − complexity)')

    pr_ylim = _shared_ylim(_collect_row_ys(ref_keep, arm_data, 'point_rate'))
    ss_ylim = _shared_ylim(_collect_row_ys(ref_keep, arm_data, 'search_score'))
    _apply_row_ylim((axes[0, 0], axes[0, 1], axes[0, 2]), pr_ylim)
    _apply_row_ylim((axes[1, 0], axes[1, 1], axes[1, 2]), ss_ylim)
    if pr_ylim:
        print(f'point_rate ylim={pr_ylim[0]:.4f}..{pr_ylim[1]:.4f}', flush=True)
    if ss_ylim:
        print(f'search_score ylim={ss_ylim[0]:.4f}..{ss_ylim[1]:.4f}', flush=True)

    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    plt.close(fig)
    print(f'wrote {args.out}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
