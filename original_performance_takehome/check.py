"""Fast hypothesis loop: correctness + simulated cycles.

Default: cheap smoke, then official 10/16/256.
Trace is opt-in and uses a small kernel so Perfetto stays interactive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from perf_takehome import BASELINE, get_kernel, quick_kernel_check
from problem import Input, N_CORES, PythonMachine, Tree, build_mem_image
from vliw_native import profile_program

HISTORY = ROOT / '_check_history.jsonl'
ABLATION = ROOT / '_ablation.jsonl'
LAST_PROF = ROOT / '_last_profile.json'
TEST_FILES = (
    'tests/submission_tests.py',
    'tests/frozen_problem.py',
    'tests/test_engine.py',
)
FULL = (10, 16, 256)
SMOKE = (3, 2, 8)
TRACE_SIZE = (5, 4, 16)


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def _load_last_full_cycles() -> int | None:
    if not HISTORY.is_file():
        return None
    last = None
    with HISTORY.open(encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cycles = ((row or {}).get('full') or {}).get('cycles')
            if cycles is not None:
                last = cycles
    return last


def _append_history(row: dict) -> None:
    with HISTORY.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + '\n')


def _run_one(label: str, height: int, rounds: int, batch: int) -> dict:
    print(f'  {label} {height}/{rounds}/{batch}', flush=True)
    t0 = time.perf_counter()
    try:
        cycles = quick_kernel_check(height, rounds, batch)
        ok = True
        err = ''
    except AssertionError as exc:
        cycles = None
        ok = False
        err = str(exc)
    took = _ms(t0)
    row = {
        'label': label,
        'shape': f'{height}/{rounds}/{batch}',
        'cycles': cycles,
        'ok': ok,
        'ms': round(took, 1),
        'err': err,
    }
    if ok and cycles is not None:
        extra = ''
        if (height, rounds, batch) == FULL:
            extra = f'  {BASELINE / cycles:.3f}x baseline'
        print(f'    cycles={cycles}{extra}  {took:.0f} ms  ok', flush=True)
    else:
        print(f'    FAIL  {took:.0f} ms  {err}', flush=True)
    return row


def write_small_trace(dest: Path) -> Path:
    height, rounds, batch = TRACE_SIZE
    print(f'  trace {height}/{rounds}/{batch} -> {dest.name}', flush=True)
    t0 = time.perf_counter()
    random.seed(123)
    forest = Tree.generate(height)
    inp = Input.generate(forest, batch, rounds)
    mem = build_mem_image(forest, inp)
    kb = get_kernel(
        forest.height, len(forest.values), len(inp.indices), rounds, emit_debug=False
    )
    prev = Path.cwd()
    os.chdir(ROOT)
    try:
        old = ROOT / 'trace.json'
        if old.is_file():
            old.unlink()
        machine = PythonMachine(
            list(mem),
            kb.instrs,
            kb.debug_info(),
            n_cores=N_CORES,
            value_trace={},
            trace=True,
        )
        machine.enable_pause = False
        machine.enable_debug = False
        machine.run()
        del machine
    finally:
        os.chdir(prev)
    src = ROOT / 'trace.json'
    if dest.resolve() != src.resolve():
        dest.write_bytes(src.read_bytes())
    size = dest.stat().st_size
    print(f'    wrote {size / 1e6:.2f} MB  {_ms(t0):.0f} ms', flush=True)
    return dest


def _print_profile(prof: dict) -> None:
    eng = prof.get('engines') or {}

    def occ(name: str) -> str:
        e = eng.get(name) or {}
        limit = int(e.get('limit') or 0)
        cycles = max(int(prof.get('cycles_est') or 0), 1)
        used = float(e.get('ops') or 0) / cycles
        return f'{name}={used:.2f}/{limit}'

    correct = prof.get('correct')
    extra = ''
    if correct is not None:
        extra = f'  correct={str(bool(correct)).lower()}'
        if prof.get('cycles_run') is not None:
            extra += f'  cycles_run={prof.get("cycles_run")}'
        if prof.get('error'):
            extra += f'  err={prof.get("error")}'
    print(
        f'  cycles_est={prof.get("cycles_est")}  ipc={float(prof.get("ipc") or 0):.2f}  '
        f'idle={prof.get("idle_cause")}  bottleneck={prof.get("bottleneck")}{extra}',
        flush=True,
    )
    oh = float(prof.get('overhead_frac') or 0)
    print(
        f'  floor={prof.get("floor")} {prof.get("floor_engine")}  '
        f'overhead={prof.get("overhead")} ({100.0 * oh:.1f}%)  '
        f'sat={prof.get("saturation_cycles")}  '
        f'cp={prof.get("critical_path")}  '
        f'cp_raw={prof.get("cp_raw")}  cp_waw={prof.get("cp_waw")}  '
        f'cp_mem={prof.get("cp_mem")}  '
        f'dep={float(prof.get("dep_pressure") or 0):.3f}  '
        f'ports={float(prof.get("resource_pressure") or 0):.3f}  '
        f'waste={float(prof.get("schedule_waste") or 0):.3f}',
        flush=True,
    )
    print(
        f'  {occ("alu")}  {occ("valu")}  {occ("load")}  {occ("store")}  {occ("flow")}  '
        f'ops={prof.get("alu_ops")}/{prof.get("valu_ops")}/{prof.get("load_ops")}/'
        f'{prof.get("store_ops")}/{prof.get("flow_ops")}',
        flush=True,
    )
    phases = prof.get('phases') or {}
    if phases:
        bits = [f'{k}={v}' for k, v in phases.items() if v]
        if bits:
            print('  phases  ' + '  '.join(bits), flush=True)
    bounds = prof.get('bounds') or {}
    if bounds:
        print(
            f'  bounds  valu={bounds.get("valu_floor")}  load={bounds.get("load_floor")}  '
            f'gather={bounds.get("gather_floor")}  all_scalar={bounds.get("gather_floor_all_scalar")}  '
            f'fused_hash={bounds.get("fused_hash_floor")}  useful={bounds.get("useful_op_floor")}  '
            f'ipc/23={float(bounds.get("ipc_vs_peak") or 0):.3f}',
            flush=True,
        )
    by_d = prof.get('gathers_by_depth') or {}
    if by_d:
        bits = [
            f'{k}:{row.get("gathers")}/{row.get("cycles")}'
            for k, row in by_d.items()
            if isinstance(row, dict) and (row.get('gathers') or row.get('cycles'))
        ]
        if bits:
            print('  depth  ' + '  '.join(bits) + '  (gathers/cycles)', flush=True)
    alu_c = prof.get('alu_class') or {}
    if alu_c:
        print(
            f'  alu_class  hash={alu_c.get("hash")}  idx={alu_c.get("idx")}  '
            f'addr={alu_c.get("addr")}  init={alu_c.get("init")}',
            flush=True,
        )
    vecs = prof.get('scratch_vectors') or {}
    pipe = prof.get('pipeline') or {}
    if vecs or pipe:
        print(
            f'  scratch  peak_vecs={vecs.get("peak_vecs")}/{vecs.get("capacity_vecs")}  '
            f'free={vecs.get("free_vecs")}  waw={vecs.get("waw_conflicts")}  '
            f'war={vecs.get("war_named_overlaps")}  same_cyc={vecs.get("war_same_cycle")}  '
            f'in_flight={float(pipe.get("tiles_in_flight") or 0):.1f}  '
            f'ii={float(pipe.get("ii_est") or 0):.2f}  '
            f'load_to_use={float(pipe.get("load_to_use_mean") or 0):.1f}  '
            f'p50={pipe.get("load_to_use_p50")}  p95={pipe.get("load_to_use_p95")}  '
            f'hist={pipe.get("load_to_use_hist")}',
            flush=True,
        )
    regions = prof.get('regions') or {}
    if regions:
        su = regions.get('startup') or {}
        st = regions.get('steady') or {}
        dr = regions.get('drain') or {}
        print(
            f'  regions  startup={su.get("cycles")}  steady={st.get("cycles")}  '
            f'drain={dr.get("cycles")}  zero_load={prof.get("zero_load_cycles")}  '
            f'load0_valu<6={prof.get("load0_valu_lt6")}',
            flush=True,
        )
        print(
            f'  unused  steady valu={st.get("valu_unused_slots")}  '
            f'load={st.get("load_unused_slots")}  store={st.get("store_unused_slots")}  '
            f'alu={st.get("alu_unused_slots")}  flow={st.get("flow_unused_slots")}',
            flush=True,
        )
        print(
            f'  unused  drain  valu={dr.get("valu_unused_slots")}  '
            f'load={dr.get("load_unused_slots")}  store={dr.get("store_unused_slots")}  '
            f'alu={dr.get("alu_unused_slots")}  flow={dr.get("flow_unused_slots")}  '
            f'wavefront={pipe.get("wavefront")}',
            flush=True,
        )
    occ_hist = prof.get('occupancy_hist') or {}
    if occ_hist:
        bits = []
        for name in ('alu', 'valu', 'load', 'store', 'flow'):
            row = occ_hist.get(name) or {}
            if isinstance(row, dict):
                bits.append(
                    f'{name}={float(row.get("mean_used") or 0):.2f}/'
                    f'{row.get("limit")} full={row.get("full")} hist={row.get("hist")}'
                )
        if bits:
            print('  occ_hist  ' + '  '.join(bits), flush=True)
    occ_series = prof.get('occupancy_series') or {}
    if int(occ_series.get('n') or 0) > 0:
        print(
            f'  occ_series  n={occ_series.get("n")}  stride={occ_series.get("stride")}',
            flush=True,
        )
    pres = prof.get('pressure') or {}
    if pres:
        extra = ''
        if int(pres.get('n') or 0) > 0:
            extra = f'  series_n={pres.get("n")}  stride={pres.get("stride")}'
        print(
            f'  pressure  peak={pres.get("peak")}  p50={pres.get("p50")}  '
            f'mean={float(pres.get("mean") or 0):.1f}{extra}',
            flush=True,
        )
    for row in (prof.get('live_overlaps') or [])[:6]:
        print(
            f'  overlap  {row.get("a")}~{row.get("b")}  cycles={row.get("cycles")}',
            flush=True,
        )
    integ = prof.get('integrity') or {}
    if integ:
        print(
            f'  integrity  hash={integ.get("hash_ops_present")}  '
            f'stores={integ.get("index_stores")}  mux={integ.get("mux_used")}  '
            f'skip_hash={integ.get("suspect_skip_hash")}  cheat={integ.get("suspect_cheat")}',
            flush=True,
        )
    rni = prof.get('ready_not_issued') or {}
    lim = prof.get('limit_engine') or {}
    mix = prof.get('mix') or {}
    print(
        f'  rni_mean={float(prof.get("ready_not_issued_mean") or 0):.2f}  '
        f'rni={rni}  limit={lim}',
        flush=True,
    )
    print(
        f'  mix  {prof.get("mix_imbalance")}  '
        f'valu/load={float(prof.get("valu_per_load") or 0):.2f} (target 3)  '
        f'load/flow={float(prof.get("load_per_flow") or 0):.2f} (target 2)  '
        f'hungry valu={mix.get("valu_hungry")} load={mix.get("load_hungry")} '
        f'flow={mix.get("flow_hungry")} bal={mix.get("balanced")} '
        f'empty={mix.get("empty")}',
        flush=True,
    )
    rle = mix.get('rle')
    if rle:
        shown = rle if len(rle) <= 96 else rle[:96] + '...'
        print(f'  mix_rle  {shown}', flush=True)
    print(
        f'  gather  load.load={prof.get("gather_scalar")}  vload={prof.get("vload_ops")}  '
        f'select={prof.get("select_ops")}  vselect={prof.get("vselect_ops")}  '
        f'madd={prof.get("madd_ops")}  L0-3 prefer select  L5+ prefer gather',
        flush=True,
    )
    print(
        f'  peak_live={prof.get("peak_live")}/{prof.get("scratch_capacity")}  '
        f'cells={prof.get("cells_touched")}  slack_mean={float(prof.get("slack_mean") or 0):.1f}  '
        f'slack_max={prof.get("slack_max")}  fp={prof.get("fingerprint")}',
        flush=True,
    )
    tops = prof.get('top_ops') or []
    if tops:
        bits = [f'{name}:{n}' for name, n in tops[:6]]
        print('  top_ops  ' + '  '.join(bits), flush=True)
    slackers = prof.get('top_slack') or []
    for row in slackers[:8]:
        pred = row.get('pred_op') or '-'
        print(
            f'  slack  {row.get("op")} issue={row.get("issue")} '
            f'ready={row.get("ready")} slack={row.get("slack")} '
            f'pred={pred}@{row.get("pred_issue")}',
            flush=True,
        )
    for row in (prof.get('named_live') or [])[:8]:
        carried = '  loop' if row.get('loop_carried') else ''
        print(
            f'  live  {row.get("name")} writes={row.get("writes")} '
            f'span={row.get("span")} cells={row.get("cells")}{carried}',
            flush=True,
        )
    for hyp in prof.get('hypotheses') or []:
        print(f'  hyp  {hyp.get("tag")}  {hyp.get("why")}', flush=True)
    for hint in prof.get('hints') or []:
        print(f'  hint  {hint}', flush=True)
    diff = prof.get('diff')
    if diff:
        print(
            f'  diff  cycles={diff.get("cycles_est")}  '
            f'cp_raw={diff.get("cp_raw")}  cp_waw={diff.get("cp_waw")}  '
            f'cp_mem={diff.get("cp_mem")}  '
            f'ops={diff.get("alu_ops")}/{diff.get("valu_ops")}/{diff.get("load_ops")}/'
            f'{diff.get("store_ops")}/{diff.get("flow_ops")}  '
            f'oh={diff.get("overhead")}  gather={diff.get("gather_scalar")}  '
            f'vsel={diff.get("vselect_ops")}  '
            f'floor_moved={diff.get("floor_engine_changed")}  '
            f'bn_moved={diff.get("bottleneck_moved")}  '
            f'same={diff.get("same_program")}',
            flush=True,
        )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _print_audit(prof: dict | None) -> None:
    print('  audit', flush=True)
    missing = False
    for rel in TEST_FILES:
        path = ROOT / rel
        if not path.is_file():
            missing = True
            print(f'    MISSING  {rel}', flush=True)
            continue
        print(f'    tests  {rel}  sha256={_file_digest(path)}', flush=True)
    frozen = ROOT / 'tests' / 'frozen_problem.py'
    problem = ROOT / 'problem.py'
    if frozen.is_file() and problem.is_file():
        same = frozen.read_bytes() == problem.read_bytes()
        print(f'    frozen_vs_problem  {"same" if same else "differ"}', flush=True)
    if prof is None:
        print('    no profile', flush=True)
        return
    integ = prof.get('integrity') or {}
    bounds = prof.get('bounds') or {}
    cycles = prof.get('cycles_run') or prof.get('cycles_est')
    gather_all = int(bounds.get('gather_floor_all_scalar') or 0)
    mux = bool(integ.get('mux_used'))
    print(
        f'    integrity  hash={integ.get("hash_ops_present")}  '
        f'stores={integ.get("index_stores")}  mux={mux}  '
        f'hash_like={integ.get("hash_like_ops")}  '
        f'skip_hash={integ.get("suspect_skip_hash")}  '
        f'cheat={integ.get("suspect_cheat")}',
        flush=True,
    )
    if missing:
        print('    WARN  frozen test files missing', flush=True)
    if cycles is not None and gather_all and int(cycles) < gather_all and not mux:
        print(
            f'    WARN  cycles={cycles} < gather_floor_all_scalar={gather_all} without mux',
            flush=True,
        )
    if integ.get('suspect_cheat') or integ.get('suspect_skip_hash'):
        print('    WARN  score integrity flags set', flush=True)


def run_profile(height: int, rounds: int, batch: int) -> dict:
    print(f'  profile {height}/{rounds}/{batch}', flush=True)
    t0 = time.perf_counter()
    n_nodes = 2 ** (height + 1) - 1
    kb = get_kernel(height, n_nodes, batch, rounds, emit_debug=False)
    prev = LAST_PROF.read_text(encoding='utf-8') if LAST_PROF.is_file() else None
    prof = profile_program(
        kb.instrs,
        omit_debug=True,
        prev_json=prev,
        phases=kb.phases,
        scratch_debug=kb.scratch_debug,
        forest_height=height,
        rounds=rounds,
        batch_size=batch,
    )
    try:
        prof['cycles_run'] = quick_kernel_check(height, rounds, batch)
        prof['correct'] = True
    except AssertionError as exc:
        prof['correct'] = False
        prof['error'] = str(exc)
    LAST_PROF.write_text(json.dumps(prof, indent=2) + '\n', encoding='utf-8')
    print(f'    {_ms(t0):.0f} ms', flush=True)
    _print_profile(prof)
    return prof


def open_trace(path: Path) -> int:
    cli = ROOT / 'tools' / 'perfetto_cli.py'
    return subprocess.call([sys.executable, '-u', str(cli), '--httpd', str(path)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Fast kernel hypothesis check')
    parser.add_argument('--smoke', action='store_true', help='only 3/2/8')
    parser.add_argument('--full', action='store_true', help='only official 10/16/256')
    parser.add_argument('--trace', action='store_true', help='small trace + native Perfetto')
    parser.add_argument('--prof', action='store_true', help='C++ scheduler-aware profile')
    parser.add_argument(
        '--prof-only',
        action='store_true',
        help='profile + correctness, skip extra smoke/full prints',
    )
    parser.add_argument('-m', '--note', default='', help='label stored in history')
    parser.add_argument('--hypothesis', default='', help='ablation hypothesis stored in history')
    parser.add_argument(
        '--keep',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='mark ablation keep/revert (default: keep if cycles dropped)',
    )
    parser.add_argument('--audit', action='store_true', help='print score-integrity audit')
    args = parser.parse_args(argv)

    last_cycles = _load_last_full_cycles()

    print('hypothesis check', flush=True)
    t0 = time.perf_counter()
    results: dict[str, dict] = {}
    ok = True
    prof = None
    if args.prof or args.prof_only:
        shape = SMOKE if args.smoke else FULL
        prof = run_profile(*shape)
        ok = ok and bool(prof.get('correct'))

    if not args.prof_only and not args.full:
        results['smoke'] = _run_one('smoke', *SMOKE)
        ok = ok and results['smoke']['ok']

    if not args.prof_only and ok and not args.smoke:
        results['full'] = _run_one('full', *FULL)
        ok = ok and results['full']['ok']
        full = results['full']
        if full['ok'] and full['cycles'] is not None:
            cycles = full['cycles']
            delta = ''
            if last_cycles is not None:
                diff = cycles - last_cycles
                sign = '+' if diff > 0 else ''
                delta = f'  delta={sign}{diff} vs last'
            print(
                f'score  cycles={cycles}  {BASELINE / cycles:.3f}x  '
                f'baseline={BASELINE}{delta}',
                flush=True,
            )

    if args.audit and prof is None and LAST_PROF.is_file():
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        print(f'  audit  loaded {LAST_PROF.name}', flush=True)

    row = {
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'note': args.note,
        'ok': ok,
        'total_ms': round(_ms(t0), 1),
        'smoke': results.get('smoke'),
        'full': results.get('full'),
        'profile': None
        if prof is None
        else {
            'cycles_est': prof.get('cycles_est'),
            'cycles_run': prof.get('cycles_run'),
            'correct': prof.get('correct'),
            'idle_cause': prof.get('idle_cause'),
            'bottleneck': prof.get('bottleneck'),
            'critical_path': prof.get('critical_path'),
            'cp_raw': prof.get('cp_raw'),
            'cp_waw': prof.get('cp_waw'),
            'cp_mem': prof.get('cp_mem'),
            'work_bound': prof.get('work_bound'),
            'floor': prof.get('floor'),
            'floor_engine': prof.get('floor_engine'),
            'overhead': prof.get('overhead'),
            'mix_imbalance': prof.get('mix_imbalance'),
            'gather_scalar': prof.get('gather_scalar'),
            'vselect_ops': prof.get('vselect_ops'),
            'valu_ops': prof.get('valu_ops'),
            'load_ops': prof.get('load_ops'),
            'peak_live': prof.get('peak_live'),
            'peak_scratch': prof.get('peak_live'),
            'zero_load_cycles': prof.get('zero_load_cycles'),
            'load0_valu_lt6': prof.get('load0_valu_lt6'),
            'ii_est': (prof.get('pipeline') or {}).get('ii_est'),
            'regions': {
                'startup': ((prof.get('regions') or {}).get('startup') or {}).get('cycles'),
                'steady': ((prof.get('regions') or {}).get('steady') or {}).get('cycles'),
                'drain': ((prof.get('regions') or {}).get('drain') or {}).get('cycles'),
            },
            'bounds': prof.get('bounds'),
            'gathers_by_depth': prof.get('gathers_by_depth'),
            'integrity': prof.get('integrity'),
            'hypotheses': [h.get('tag') for h in (prof.get('hypotheses') or [])],
            'fingerprint': prof.get('fingerprint'),
        },
    }
    if prof is not None:
        diff = prof.get('diff') or {}
        cycles_now = prof.get('cycles_run') or prof.get('cycles_est')
        keep = args.keep
        if keep is None and last_cycles is not None and cycles_now is not None:
            keep = int(cycles_now) <= int(last_cycles)
        elif keep is None:
            keep = True
        keep = bool(keep)
        revert = not keep
        peak_scratch = prof.get('peak_live')
        peak_cap = prof.get('scratch_capacity')
        row['keep'] = keep
        row['revert'] = revert
        row['peak_scratch'] = peak_scratch
        row['peak_scratch_cap'] = peak_cap
        row['valu_ops'] = prof.get('valu_ops')
        row['load_ops'] = prof.get('load_ops')
        ablation = {
            'ts': row['ts'],
            'note': args.note,
            'hypothesis': args.hypothesis,
            'keep': keep,
            'revert': revert,
            'cycles': cycles_now,
            'delta_cycles': diff.get('cycles_est'),
            'floor_engine': prof.get('floor_engine'),
            'floor_moved': diff.get('floor_engine_changed'),
            'valu_ops': prof.get('valu_ops'),
            'load_ops': prof.get('load_ops'),
            'peak_scratch': peak_scratch,
            'peak_scratch_cap': peak_cap,
            'zero_load_cycles': prof.get('zero_load_cycles'),
            'load0_valu_lt6': prof.get('load0_valu_lt6'),
            'ii_est': (prof.get('pipeline') or {}).get('ii_est'),
            'integrity': prof.get('integrity'),
            'fingerprint': prof.get('fingerprint'),
        }
        row['ablation'] = ablation
        with ABLATION.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(ablation, ensure_ascii=True) + '\n')
        print(
            f'  history  keep={str(keep).lower()}  revert={str(revert).lower()}  '
            f'peak_scratch={peak_scratch}/{peak_cap}  '
            f'valu_ops={prof.get("valu_ops")}  load_ops={prof.get("load_ops")}',
            flush=True,
        )
        print(
            f'  ablation  keep={str(keep).lower()}  revert={str(revert).lower()}  '
            f'hyp={args.hypothesis or args.note or "-"}  '
            f'delta_cycles={diff.get("cycles_est")}  '
            f'floor_moved={diff.get("floor_engine_changed")}',
            flush=True,
        )
    if args.audit:
        _print_audit(prof)
    if results.get('full') or results.get('smoke') or prof is not None:
        _append_history(row)
    print(f'done  {_ms(t0):.0f} ms  {"ok" if ok else "FAIL"}', flush=True)

    if args.trace:
        dest = ROOT / 'trace.json'
        write_small_trace(dest)
        return open_trace(dest)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
