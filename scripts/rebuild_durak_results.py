'''Rebuild full Durak results.tsv from git keeps + transcript probes, then refresh charts.'''
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results.tsv'
SLIM = ROOT / 'results_batch25_30.tsv'

HEADER = (
    'commit\topponent\tpoint_rate\tsearch_score\tlower_ci\tgames\tcomplexity\tstatus\tdescription\n'
)

# (commit, point_rate, search_score, lower_ci, games, complexity, status, description)
# Chronological B4 headline rows for Durak jun22 + early ladder.
ROWS: list[tuple] = [
    # Early ladder (master / pre-jun22)
    ('228791f', 0.49211, 0.68404, 0.49200, 10000000, 310, 'keep',
     'baseline B2 H1-H3'),
    ('2415f53', 0.50461, 0.70002, 0.50447, 10000000, 210, 'keep',
     'exp A: drop H3 same-rank trump defense'),
    ('35330ec', 0.52434, 0.72562, 0.52409, 10000000, 100, 'keep',
     'exp B: drop H2 group-attack H1-only'),
    ('c263a3a', 0.53748, 0.73239, 0.53723, 10000000, 100, 'keep',
     'exp G: endgame open low pair singleton'),
    ('84c9321', 0.54507, 0.73650, 0.54485, 10000000, 100, 'keep',
     'exp H: midgame pair-open + endgame trump-strip'),
    ('069959b', 0.54516, 0.73654, 0.54493, 10000000, 100, 'discard',
     'exp J: void-suit pile pressure (below keep bar)'),
    ('probe', 0.53397, 0.73094, 0.53241, 200000, 100, 'discard',
     'exp K: defense voluntary take (quick regression)'),
    ('probe', 0.54409, 0.73727, 0.54246, 200000, 100, 'discard',
     'exp L: relaxed trump-strip opp<=4 (quick)'),
    ('probe', 0.54551, 0.73679, 0.54391, 200000, 100, 'discard',
     'exp M: late pair-open deck<=6 (quick neutral)'),
    # Finish-mode series (transcript3)
    ('f36cda7', 0.54714, 0.73689, 0.54691, 10000000, 100, 'keep',
     'exp P: void pile -8 + finish trump-strip open'),
    ('7bb300c', 0.55749, 0.74418, 0.55726, 10000000, 100, 'keep',
     'exp Q: finish pile low-trump dump endgame'),
    ('41b5857', 0.56543, 0.74988, 0.56520, 10000000, 100, 'keep',
     'exp R: finish mode opp<=3'),
    ('65e8104', 0.58063, 0.75452, 0.58040, 10000000, 100, 'keep',
     'exp S: finish trump dump >=1 trump'),
    ('f6b5d93', 0.58560, 0.75736, 0.58537, 10000000, 100, 'keep',
     'exp V: pile trump dump deck<=3'),
    ('d7ed0c0', 0.59161, 0.76111, 0.59138, 10000000, 100, 'keep',
     'exp Y: pile trump dump deck<=6'),
    ('bd8b6c5', 0.60708, 0.77075, 0.60685, 10000000, 100, 'keep',
     'exp AC: pile trump dump opp<=4'),
    ('f86282d', 0.61206, 0.77341, 0.61183, 10000000, 100, 'keep',
     'exp AD: pile trump dump opp<=5'),
    # jun22 batch 1-2 probes (transcript4)
    ('probe', 0.59800, 0.76000, 0.59600, 200000, 100, 'discard',
     'exp AK: open strip opp<=4 (regression)'),
    ('probe', 0.61300, 0.77200, 0.61100, 200000, 100, 'discard',
     'exp AL-AP: pile/open micro probes neutral'),
    ('d5bca3c', 0.61938, 0.77742, 0.61913, 10000000, 100, 'keep',
     'exp AQ: pile trump dump deck<=5'),
    ('probe', 0.62122, 0.77850, 0.61900, 200000, 100, 'discard',
     'exp BY: pair-open deck>=6 maybe (+0.002 quick)'),
    ('probe', 0.62165, 0.77887, 0.62139, 10000000, 100, 'discard',
     'exp CI: pair-open deck>=5 full (+0.0023 sub-gate)'),
    ('7912e0c', 0.62635, 0.78125, 0.62610, 10000000, 100, 'keep',
     'exp CQ: pair deck>=5 + pile trump dump deck<=3'),
    ('167b02d', 0.63676, 0.78941, 0.63652, 10000000, 100, 'keep',
     'exp CZ: CQ combo + endgame open strip opp<=2'),
]


def row(r: tuple) -> str:
    c, pr, ss, lo, games, cx, st, desc = r
    return f'{c}\tB4\t{pr:.6f}\t{ss:.6f}\t{lo:.6f}\t{games}\t{cx}\t{st}\t{desc}\n'


def append_slim_probes(lines: list[str]) -> None:
    if not SLIM.exists():
        return
    text = SLIM.read_text(encoding='utf-8')
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) >= 9 and parts[1] == 'B4' and parts[0] == 'probe':
            lines.append(line + '\n')


def main() -> None:
    # Preserve post-CZ batch probes.
    if OUT.exists():
        SLIM.write_text(OUT.read_text(encoding='utf-8'), encoding='utf-8')

    lines = [HEADER]
    for r in ROWS:
        lines.append(row(r))
    append_slim_probes(lines)

    OUT.write_text(''.join(lines), encoding='utf-8')
    b4 = sum(1 for ln in lines if '\tB4\t' in ln)
    keeps = sum(1 for ln in lines if '\tkeep\t' in ln and '\tB4\t' in ln)
    print(f'Wrote {len(lines) - 1} rows ({b4} B4, {keeps} keeps) to {OUT}')

    print('Regenerating progress.png via run_analysis.bat ...', flush=True)
    subprocess.run(['cmd', '/c', str(ROOT / 'scripts' / 'run_analysis.bat')], cwd=ROOT, check=True)
    print('Done: progress.png, occam.png, score_alignment.png')


if __name__ == '__main__':
    main()
