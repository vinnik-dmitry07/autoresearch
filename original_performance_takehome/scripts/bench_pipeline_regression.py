"""Regression bench for every pipeline stage: build, encode, run, ref, profile, trace.

Also locks official / smoke profiler metrics so a silent metric drift fails --check.

Usage:
    python -u scripts/bench_pipeline_regression.py
    python -u scripts/bench_pipeline_regression.py --check
    python -u scripts/bench_pipeline_regression.py --update
    python -u scripts/bench_pipeline_regression.py --cli
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

T_START = time.perf_counter()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

t0 = time.perf_counter()
from perf_takehome import BASELINE, get_kernel, quick_kernel_check
from problem import Input, Machine, N_CORES, PythonMachine, Tree, build_mem_image, reference_final
from vliw_native import encode_program, profile_program, _lib

IMPORT_S = time.perf_counter() - t0

BASELINE_PATH = ROOT / 'scripts' / 'pipeline_bench_baseline.json'
RESULT_PATH = ROOT / '_pipeline_bench.json'
HISTORY_PATH = ROOT / '_pipeline_bench.jsonl'
LAST_PROF = ROOT / '_last_profile.json'
CHECK_HISTORY = ROOT / '_check_history.jsonl'
ABLATION = ROOT / '_ablation.jsonl'

# Hard ceilings (ms). Fail --check if a stage exceeds its budget.
BUDGET_MS = {
    'imports': 80,
    'kernel_build_cold': 80,
    'kernel_build_cached': 5,
    'encode_cached': 15,
    'native_load': 40,
    'tree_generate': 20,
    'input_generate': 10,
    'build_mem_image': 10,
    'machine_ctor': 40,
    'machine_run': 15,
    'reference_final': 40,
    'profile_first': 80,
    'profile_repeat': 50,
    'profile_diff': 60,
    'cpp_profile': 50,
    'quick_kernel_check': 60,
    'smoke_kernel': 20,
    'smoke_profile': 15,
    'smoke_check': 10,
    'trace_total': 250,
    'json_dumps_profile': 15,
    'json_loads_profile': 15,
    'to_first_full': 150,
    'cached_loop': 150,
    'cli_prof_smoke': 2000,
    'cli_prof_full': 2500,
}

# vs last saved baseline: slower than both ratio and absolute delta counts as a regression
REGRESS_RATIO = 1.4
REGRESS_DELTA_MS = 20.0

OFFICIAL_METRICS = {
    'cycles_est': 147734,
    'ipc': 1.0,
    'valu_ops': 0,
    'alu_ops': 118784,
    'load_ops': 12564,
    'store_ops': 8192,
    'flow_ops': 8194,
    'zero_load_cycles': 135170,
    'load0_valu_lt6': 135170,
    'war_same_cycle': 20480,
    'peak_live': 273,
    'floor': 9899,
    'floor_engine': 'alu',
    'overhead': 137835,
    'phase_gather': 4096,
    'phase_init': 278,
    'mix_imbalance': 'scalar_alu',
    'ii_est': 36.0,
    'load_to_use_n': 8192,
    'load_to_use_1': 4096,
    'load_to_use_16_31': 4096,
    'startup': 277,
    'steady': 147456,
    'drain': 1,
    'occupancy_series_n': 0,
    'alu_class_idx': 20480,
    'gather_floor_all_scalar': 2048,
    'useful_op_floor': 1093,
    'fused_hash_floor': 1024,
    'fingerprint': 'bf9464c6e64088e5',
}

SMOKE_METRICS = {
    'cycles_est': 610,
    'ipc': 1.0,
    'valu_ops': 0,
    'alu_ops': 464,
    'load_ops': 80,
    'store_ops': 32,
    'flow_ops': 34,
    'zero_load_cycles': 530,
    'load0_valu_lt6': 530,
    'war_same_cycle': 80,
    'peak_live': 29,
    'floor': 40,
    'floor_engine': 'load',
    'overhead': 570,
    'phase_gather': 16,
    'phase_init': 34,
    'mix_imbalance': 'scalar_alu',
    'ii_est': 36.0,
    'load_to_use_n': 32,
    'load_to_use_1': 16,
    'load_to_use_16_31': 16,
    'startup': 33,
    'steady': 576,
    'drain': 1,
    'occupancy_series_n': 0,
    'alu_class_idx': 80,
    'gather_floor_all_scalar': 8,
    'useful_op_floor': 5,
    'fused_hash_floor': 4,
    'fingerprint': 'd40ff359fe59b663',
}

TRACE_CYCLES = 2344


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 2)


def _median(samples: list[float]) -> float:
    return statistics.median(samples)


def _time(fn, reps: int = 1) -> float:
    if reps <= 1:
        t0 = time.perf_counter()
        fn()
        return time.perf_counter() - t0
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return _median(samples)


def _same(got, want) -> bool:
    if isinstance(got, float) or isinstance(want, float):
        return abs(float(got) - float(want)) < 1e-6
    return got == want


def _metric_snapshot(prof: dict) -> dict:
    pipe = prof.get('pipeline') or {}
    hist = pipe.get('load_to_use_hist') or {}
    regs = prof.get('regions') or {}
    bounds = prof.get('bounds') or {}
    return {
        'cycles_est': prof.get('cycles_est'),
        'ipc': prof.get('ipc'),
        'valu_ops': prof.get('valu_ops'),
        'alu_ops': prof.get('alu_ops'),
        'load_ops': prof.get('load_ops'),
        'store_ops': prof.get('store_ops'),
        'flow_ops': prof.get('flow_ops'),
        'zero_load_cycles': prof.get('zero_load_cycles'),
        'load0_valu_lt6': prof.get('load0_valu_lt6'),
        'war_same_cycle': prof.get('war_same_cycle'),
        'peak_live': prof.get('peak_live'),
        'floor': prof.get('floor'),
        'floor_engine': prof.get('floor_engine'),
        'overhead': prof.get('overhead'),
        'phase_gather': prof.get('phase_gather'),
        'phase_init': prof.get('phase_init'),
        'mix_imbalance': prof.get('mix_imbalance'),
        'ii_est': pipe.get('ii_est'),
        'load_to_use_n': pipe.get('load_to_use_n'),
        'load_to_use_1': hist.get('1'),
        'load_to_use_16_31': hist.get('16_31'),
        'startup': (regs.get('startup') or {}).get('cycles'),
        'steady': (regs.get('steady') or {}).get('cycles'),
        'drain': (regs.get('drain') or {}).get('cycles'),
        'occupancy_series_n': (prof.get('occupancy_series') or {}).get('n'),
        'alu_class_idx': (prof.get('alu_class') or {}).get('idx'),
        'gather_floor_all_scalar': bounds.get('gather_floor_all_scalar'),
        'useful_op_floor': bounds.get('useful_op_floor'),
        'fused_hash_floor': bounds.get('fused_hash_floor'),
        'fingerprint': prof.get('fingerprint'),
    }


def _check_metrics(got: dict, want: dict, prefix: str) -> list[str]:
    fails = []
    for key, expected in want.items():
        actual = got.get(key)
        if not _same(actual, expected):
            fails.append(f'{prefix}.{key}={actual} want {expected}')
    return fails


def _print_metrics(got: dict, want: dict, title: str) -> None:
    print('', flush=True)
    print(f'{title}', flush=True)
    print(f'{"metric":<28} {"got":>16} {"want":>16}  status', flush=True)
    for key, expected in want.items():
        actual = got.get(key)
        status = 'ok' if _same(actual, expected) else 'DRIFT'
        print(f'{key:<28} {str(actual):>16} {str(expected):>16}  {status}', flush=True)


def _profile(kb, height: int, rounds: int, batch: int, prev_json: str | None = None) -> dict:
    return profile_program(
        kb.instrs,
        omit_debug=True,
        prev_json=prev_json,
        phases=kb.phases,
        scratch_debug=kb.scratch_debug,
        forest_height=height,
        rounds=rounds,
        batch_size=batch,
    )


def _restore_check_artifacts(saved: dict[Path, bytes | None]) -> None:
    for path, data in saved.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(data)


def _measure(cli: bool, reps: int) -> dict:
    stages: dict[str, float] = {}
    extra: dict = {}
    n = 24 if cli else 22
    step = 0

    def mark(name: str, seconds: float, note: str = '') -> None:
        nonlocal step
        step += 1
        stages[name] = _ms(seconds)
        tail = f'  {note}' if note else ''
        print(f'[{step}/{n}] {name:<28} {stages[name]:8.1f} ms{tail}', flush=True)

    print('pipeline regression bench  10/16/256 + smoke 3/2/8 + trace 5/4/16', flush=True)
    mark('imports', IMPORT_S)

    t0 = time.perf_counter()
    kb = get_kernel(10, 2 ** 11 - 1, 256, 16, emit_debug=False)
    mark('kernel_build_cold', time.perf_counter() - t0, f'instrs={len(kb.instrs)}')
    t0 = time.perf_counter()
    kb2 = get_kernel(10, 2 ** 11 - 1, 256, 16, emit_debug=False)
    mark('kernel_build_cached', time.perf_counter() - t0, f'same={kb is kb2}')

    t0 = time.perf_counter()
    enc = encode_program(kb.instrs, skip_debug=True)
    mark('encode_cached', time.perf_counter() - t0, f'slots={enc.n_slots}')
    t0 = time.perf_counter()
    enc.ensure_native()
    mark('native_load', time.perf_counter() - t0)

    t0 = time.perf_counter()
    random.seed(123)
    forest = Tree.generate(10)
    mark('tree_generate', time.perf_counter() - t0)
    t0 = time.perf_counter()
    inp = Input.generate(forest, 256, 16)
    mark('input_generate', time.perf_counter() - t0)
    t0 = time.perf_counter()
    mem = build_mem_image(forest, inp)
    mark('build_mem_image', time.perf_counter() - t0)

    t0 = time.perf_counter()
    machine = Machine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, omit_debug=True)
    mark('machine_ctor', time.perf_counter() - t0)
    machine.enable_pause = False
    machine.enable_debug = False
    t0 = time.perf_counter()
    machine.run()
    mark('machine_run', time.perf_counter() - t0, f'cycles={machine.cycle}')
    t0 = time.perf_counter()
    ref = reference_final(list(mem))
    mark('reference_final', time.perf_counter() - t0)
    correct = machine.mem[ref[6] : ref[6] + len(inp.values)] == ref[ref[6] : ref[6] + len(inp.values)]
    extra['cycles_run'] = int(machine.cycle)
    extra['correct'] = bool(correct and machine.cycle == BASELINE)

    t0 = time.perf_counter()
    prof = _profile(kb, 10, 16, 256)
    mark('profile_first', time.perf_counter() - t0, f'cycles_est={prof["cycles_est"]}')

    def _prof_again() -> None:
        _profile(kb, 10, 16, 256)

    mark('profile_repeat', _time(_prof_again, reps=max(reps, 3)), f'reps={max(reps, 3)} median')
    prev_blob = json.dumps(prof)

    def _prof_diff() -> None:
        _profile(kb, 10, 16, 256, prev_json=prev_blob)

    mark('profile_diff', _time(_prof_diff, reps=max(reps, 3)), f'reps={max(reps, 3)} median')
    prof_diff = _profile(kb, 10, 16, 256, prev_json=prev_blob)
    extra['official'] = _metric_snapshot(prof)
    extra['cycles_est'] = int(prof['cycles_est'])
    extra['fingerprint'] = prof['fingerprint']
    extra['diff_same'] = bool((prof_diff.get('diff') or {}).get('same_program'))
    extra['diff_cycles'] = (prof_diff.get('diff') or {}).get('cycles_est')
    extra['correct'] = bool(
        extra['correct']
        and prof['cycles_est'] == BASELINE
        and extra['diff_same']
        and extra['diff_cycles'] == 0
    )

    lib = _lib()

    def _cpp() -> None:
        raw = lib.vliw_program_profile(enc.native, None)
        lib.vliw_profile_free(raw)

    mark('cpp_profile', _time(_cpp, reps=max(reps, 3)), f'reps={max(reps, 3)} median')

    t0 = time.perf_counter()
    cycles = quick_kernel_check(10, 16, 256)
    mark('quick_kernel_check', time.perf_counter() - t0, f'cycles={cycles}')
    extra['correct'] = bool(extra['correct'] and cycles == BASELINE)

    t0 = time.perf_counter()
    kb_s = get_kernel(3, 15, 8, 2, emit_debug=False)
    mark('smoke_kernel', time.perf_counter() - t0, f'instrs={len(kb_s.instrs)}')
    t0 = time.perf_counter()
    smoke_prof = _profile(kb_s, 3, 2, 8)
    mark('smoke_profile', time.perf_counter() - t0, f'cycles_est={smoke_prof["cycles_est"]}')
    t0 = time.perf_counter()
    smoke_cycles = quick_kernel_check(3, 2, 8)
    mark('smoke_check', time.perf_counter() - t0, f'cycles={smoke_cycles}')
    extra['smoke'] = _metric_snapshot(smoke_prof)
    extra['smoke_cycles'] = int(smoke_cycles)
    extra['correct'] = bool(
        extra['correct'] and smoke_cycles == smoke_prof['cycles_est'] and smoke_cycles == 610
    )

    dest = ROOT / '_pipeline_bench_trace.json'
    dest.unlink(missing_ok=True)
    old = ROOT / 'trace.json'
    saved = old.read_bytes() if old.is_file() else None
    try:
        t0 = time.perf_counter()
        random.seed(123)
        tr_forest = Tree.generate(5)
        tr_inp = Input.generate(tr_forest, 16, 4)
        tr_mem = build_mem_image(tr_forest, tr_inp)
        tr_kb = get_kernel(
            tr_forest.height, len(tr_forest.values), len(tr_inp.indices), 4, emit_debug=False
        )
        if old.is_file():
            old.unlink()
        pym = PythonMachine(
            list(tr_mem),
            tr_kb.instrs,
            tr_kb.debug_info(),
            n_cores=N_CORES,
            value_trace={},
            trace=True,
        )
        pym.enable_pause = False
        pym.enable_debug = False
        pym.run()
        tr_cycles = pym.cycle
        del pym
        if dest.resolve() != old.resolve() and old.is_file():
            dest.write_bytes(old.read_bytes())
        size = dest.stat().st_size if dest.is_file() else (old.stat().st_size if old.is_file() else 0)
        mark('trace_total', time.perf_counter() - t0, f'cycles={tr_cycles} size={size / 1e6:.2f} MB')
        extra['trace_cycles'] = int(tr_cycles)
        extra['trace_bytes'] = int(size)
        extra['correct'] = bool(extra['correct'] and tr_cycles == TRACE_CYCLES)
    finally:
        dest.unlink(missing_ok=True)
        if saved is None:
            old.unlink(missing_ok=True)
        else:
            old.write_bytes(saved)

    t0 = time.perf_counter()
    blob = json.dumps(prof, indent=2) + '\n'
    mark('json_dumps_profile', time.perf_counter() - t0, f'bytes={len(blob)}')

    def _loads() -> None:
        json.loads(blob)

    mark('json_loads_profile', _time(_loads, reps=max(reps, 3)), f'reps={max(reps, 3)} median')

    stages['to_first_full'] = round(
        stages['imports']
        + stages['kernel_build_cold']
        + stages['encode_cached']
        + stages['native_load']
        + stages['tree_generate']
        + stages['input_generate']
        + stages['build_mem_image']
        + stages['machine_ctor']
        + stages['machine_run']
        + stages['reference_final']
        + stages['profile_first'],
        2,
    )
    stages['cached_loop'] = round(stages['profile_repeat'] + stages['quick_kernel_check'], 2)
    print(f'     to_first_full                 {stages["to_first_full"]:8.1f} ms', flush=True)
    print(f'     cached_loop                   {stages["cached_loop"]:8.1f} ms', flush=True)

    if cli:
        saved_cli = {
            LAST_PROF: LAST_PROF.read_bytes() if LAST_PROF.is_file() else None,
            CHECK_HISTORY: CHECK_HISTORY.read_bytes() if CHECK_HISTORY.is_file() else None,
            ABLATION: ABLATION.read_bytes() if ABLATION.is_file() else None,
        }
        try:
            for key, flags in (
                ('cli_prof_smoke', ['--prof-only', '--smoke']),
                ('cli_prof_full', ['--prof-only', '--full']),
            ):
                cmd = [sys.executable, '-u', str(ROOT / 'check.py'), *flags]
                t0 = time.perf_counter()
                proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
                mark(key, time.perf_counter() - t0, f'exit={proc.returncode}')
                extra['correct'] = bool(extra['correct'] and proc.returncode == 0)
        finally:
            _restore_check_artifacts(saved_cli)

    extra['wall_ms'] = _ms(time.perf_counter() - T_START)
    extra['baseline_cycles'] = BASELINE
    extra['instrs'] = len(kb.instrs)
    extra['metric_ok'] = not (
        _check_metrics(extra.get('official') or {}, OFFICIAL_METRICS, 'official')
        + _check_metrics(extra.get('smoke') or {}, SMOKE_METRICS, 'smoke')
    )
    extra['correct'] = bool(extra['correct'] and extra['metric_ok'])
    return {'stages': stages, 'extra': extra}


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _compare(current: dict, baseline: dict | None) -> tuple[list[str], list[str]]:
    locks: list[str] = []
    timing: list[str] = []
    stages = current['stages']
    extra = current['extra']
    if not extra.get('correct'):
        locks.append('correctness failed (cycles/mem/profile/metrics)')
    if extra.get('cycles_run') != BASELINE:
        locks.append(f'cycles_run={extra.get("cycles_run")} want {BASELINE}')
    if extra.get('cycles_est') != BASELINE:
        locks.append(f'cycles_est={extra.get("cycles_est")} want {BASELINE}')
    if extra.get('smoke_cycles') != 610:
        locks.append(f'smoke_cycles={extra.get("smoke_cycles")} want 610')
    if extra.get('trace_cycles') != TRACE_CYCLES:
        locks.append(f'trace_cycles={extra.get("trace_cycles")} want {TRACE_CYCLES}')
    if extra.get('diff_same') is not True:
        locks.append(f'diff_same={extra.get("diff_same")} want True')
    if extra.get('diff_cycles') != 0:
        locks.append(f'diff_cycles={extra.get("diff_cycles")} want 0')

    official = extra.get('official') or {}
    smoke = extra.get('smoke') or {}
    _print_metrics(official, OFFICIAL_METRICS, 'official 10/16/256 metrics')
    _print_metrics(smoke, SMOKE_METRICS, 'smoke 3/2/8 metrics')
    locks.extend(_check_metrics(official, OFFICIAL_METRICS, 'official'))
    locks.extend(_check_metrics(smoke, SMOKE_METRICS, 'smoke'))

    base_extra = (baseline or {}).get('extra') or {}
    for label, got, prev in (
        ('official', official, base_extra.get('official') or {}),
        ('smoke', smoke, base_extra.get('smoke') or {}),
    ):
        if prev:
            locks.extend(_check_metrics(got, prev, f'baseline.{label}'))

    base_stages = (baseline or {}).get('stages') or {}
    print('', flush=True)
    print(f'{"stage":<28} {"ms":>8} {"budget":>8} {"base":>8} {"x":>6}  status', flush=True)
    for name, ms in stages.items():
        budget = BUDGET_MS.get(name)
        prev = base_stages.get(name)
        ratio = (ms / prev) if prev else None
        status = 'ok'
        if budget is not None and ms > budget:
            status = 'BUDGET'
            timing.append(f'{name} {ms:.1f} ms > budget {budget:.0f} ms')
        elif prev is not None and ms > prev * REGRESS_RATIO and (ms - prev) > REGRESS_DELTA_MS:
            status = 'REGRESS'
            timing.append(
                f'{name} {ms:.1f} ms vs baseline {prev:.1f} ms '
                f'({ratio:.2f}x, +{ms - prev:.1f} ms)'
            )
        prev_s = f'{prev:8.1f}' if prev is not None else f'{"-":>8}'
        ratio_s = f'{ratio:6.2f}' if ratio is not None else f'{"-":>6}'
        budget_s = f'{budget:8.0f}' if budget is not None else f'{"-":>8}'
        print(f'{name:<28} {ms:8.1f} {budget_s} {prev_s} {ratio_s}  {status}', flush=True)
    return locks, timing


def _write_baseline(row: dict) -> None:
    payload = {
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'note': 'pipeline regression baseline',
        'budget_ms': BUDGET_MS,
        'regress_ratio': REGRESS_RATIO,
        'regress_delta_ms': REGRESS_DELTA_MS,
        'stages': row['stages'],
        'extra': {
            'cycles_run': row['extra'].get('cycles_run'),
            'cycles_est': row['extra'].get('cycles_est'),
            'smoke_cycles': row['extra'].get('smoke_cycles'),
            'trace_cycles': row['extra'].get('trace_cycles'),
            'instrs': row['extra'].get('instrs'),
            'baseline_cycles': BASELINE,
            'fingerprint': row['extra'].get('fingerprint'),
            'official': row['extra'].get('official'),
            'smoke': row['extra'].get('smoke'),
        },
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f'wrote baseline {BASELINE_PATH}', flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Pipeline regression benchmark')
    parser.add_argument('--check', action='store_true', help='fail on budget/baseline/metric regression')
    parser.add_argument('--update', action='store_true', help='write scripts/pipeline_bench_baseline.json')
    parser.add_argument('--cli', action='store_true', help='also time check.py from process launch')
    parser.add_argument('--reps', type=int, default=3, help='median repeats for profile/cpp')
    parser.add_argument('--json', type=Path, default=RESULT_PATH, help='write this run as JSON')
    args = parser.parse_args(argv)

    row = _measure(cli=args.cli, reps=max(1, args.reps))
    row['ts'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    args.json.write_text(json.dumps(row, indent=2) + '\n', encoding='utf-8')
    with HISTORY_PATH.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps({'ts': row['ts'], 'stages': row['stages'], 'extra': row['extra']}) + '\n')

    baseline = _load_json(BASELINE_PATH)
    locks, timing = _compare(row, baseline)
    print('', flush=True)
    print(
        f'wall {row["extra"]["wall_ms"]:.1f} ms  correct={row["extra"]["correct"]}  '
        f'metric_ok={row["extra"]["metric_ok"]}',
        flush=True,
    )

    if args.update:
        if locks:
            print('FAIL  not writing baseline', flush=True)
            for item in locks:
                print(f'  {item}', flush=True)
            return 1
        _write_baseline(row)
        return 0

    fails = locks + timing
    if args.check or baseline is not None:
        if fails:
            print('FAIL', flush=True)
            for item in fails:
                print(f'  {item}', flush=True)
            return 1
        print('ok  no pipeline regression', flush=True)
    return 0 if row['extra']['correct'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
