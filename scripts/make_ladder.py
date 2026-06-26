'''Regenerate the curated hero ladder chart (progress_ladder.png).

This is the zoomed view of the early ladder climb -- the first `LADDER_N`
B2-vs-B4 experiments from results.tsv (the run that took B2 from parity up the
baseline ladder). It is kept as a separate curated chart from the live
analysis.ipynb outputs (progress.png / occam.png / score_alignment.png).

Kept-experiment labels are rotated vertical so they do not overlap.

Run from the repo root:
    python scripts/make_ladder.py
'''
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LADDER_N = 24  # first N B4 experiments form the curated ladder climb
RESULTS_PATH = Path('results.tsv')
OUT_PATH = Path('progress_ladder.png')


def load_b4(path):
    df = pd.read_csv(path, sep='\t', dtype=str)
    for col in ('point_rate', 'search_score', 'lower_ci', 'games', 'complexity'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['status'] = df['status'].str.strip().str.lower()
    df['opponent'] = df['opponent'].str.strip()
    df['commit'] = df['commit'].str.strip()
    b4 = df[df['opponent'] == 'B4'].copy().reset_index(drop=True)
    b4['exp_id'] = np.arange(len(b4))
    return b4


def main():
    if not RESULTS_PATH.exists():
        raise FileNotFoundError(
            'results.tsv not found. Run the autoresearch loop first (see program.md).'
        )
    ladder = load_b4(RESULTS_PATH)
    ladder = ladder[ladder['exp_id'] < LADDER_N].copy()

    fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    disc = ladder[ladder['status'] == 'discard']
    kept = ladder[ladder['status'] == 'keep']

    # --- Top: point_rate vs B4 ---
    ax = axes[0]
    ax.scatter(disc['exp_id'], disc['point_rate'], c='#cccccc', s=20, alpha=0.6,
               label='Discarded')
    ax.scatter(kept['exp_id'], kept['point_rate'], c='#2ecc71', s=60, zorder=4,
               label='Kept', edgecolors='black', linewidths=0.5)
    if len(kept):
        ax.step(kept['exp_id'], kept['point_rate'].cummax(), where='post',
                color='#27ae60', linewidth=2, alpha=0.7, label='Running best')
        for _, row in kept.iterrows():
            desc = str(row['description']).strip()
            if len(desc) > 40:
                desc = desc[:37] + '...'
            ax.annotate(desc, (row['exp_id'], row['point_rate']),
                        textcoords='offset points', xytext=(0, 8), fontsize=7,
                        color='#1a7a3a', alpha=0.9, rotation=90, ha='center', va='bottom')
    ax.axhline(0.50, color='#888', linestyle='--', linewidth=1, alpha=0.5,
               label='Parity (0.50)')
    ax.axhline(0.52, color='#e74c3c', linestyle='--', linewidth=1, alpha=0.5,
               label='Dominates (>0.52 CI)')
    ax.set_ylabel('Point rate vs B4 (higher is better)')
    ax.legend(loc='lower right', fontsize=8)
    ax.grid(True, alpha=0.2)
    ax.set_title(f'B2 vs B4: {len(ladder)} experiments, {len(kept)} kept')

    # --- Bottom: search_score ---
    ax2 = axes[1]
    ax2.scatter(disc['exp_id'], disc['search_score'], c='#cccccc', s=20, alpha=0.6)
    ax2.scatter(kept['exp_id'], kept['search_score'], c='#3498db', s=60,
                edgecolors='black', linewidths=0.5, label='Kept search_score')
    if len(kept):
        ax2.step(kept['exp_id'], kept['search_score'].cummax(), where='post',
                 color='#2980b9', linewidth=2, alpha=0.7, label='Running best')
    ax2.set_xlabel('Experiment # (B4 headline rows)')
    ax2.set_ylabel('Search score (composite ladder \u2212 complexity)')
    ax2.legend(loc='lower right', fontsize=8)
    ax2.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=150, bbox_inches='tight')
    print(f'Saved {OUT_PATH} ({len(ladder)} experiments, {len(kept)} kept)')


if __name__ == '__main__':
    main()
