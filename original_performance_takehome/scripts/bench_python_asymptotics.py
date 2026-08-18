from __future__ import annotations

from pathlib import Path
import json
import math
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from problem import DebugInfo, Machine, PythonMachine, Tree, Input, build_mem_image, N_CORES
from perf_takehome import KernelBuilder
from vliw_native import encode_slot


def median(xs: list[float]) -> float:
    return statistics.median(xs)


def time_fn(repeats: int, fn) -> float:
    fn()
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(float(time.perf_counter_ns() - t0))
    return median(samples)


def fit_loglog(points: list[dict]) -> tuple[float, float]:
    xs, ys = [], []
    for p in points:
        if p['n'] > 0 and p['ns'] > 0:
            xs.append(math.log(p['n']))
            ys.append(math.log(p['ns']))
    m = len(xs)
    if m < 2:
        return 0.0, 0.0
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    den = m * sxx - sx * sx
    exp = 0.0 if abs(den) < 1e-18 else (m * sxy - sx * sy) / den
    ymean = sy / m
    intercept = (sy - exp * sx) / m
    ss_tot = sum((y - ymean) ** 2 for y in ys)
    ss_res = sum((y - (intercept + exp * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 if ss_tot < 1e-18 else 1.0 - ss_res / ss_tot
    return exp, r2


def class_match(theory_exp: float, emp: float) -> bool:
    if theory_exp <= 0.05:
        return emp < 0.40
    return abs(emp - theory_exp) <= 0.35


def finish(r: dict) -> dict:
    exp, r2 = fit_loglog(r['points'])
    r['empirical_exp'] = exp
    r['r2'] = r2
    last = r['points'][-1]
    r['ns_per_unit'] = last['ns'] / last['n'] if last['n'] else 0.0
    r['match'] = class_match(r['theory_exp'], exp)
    print(
        f"  {r['name']:<28} theory={r['theoretical']:<6} emp={exp:.2f}  R2={r2:.3f}  "
        f"{r['ns_per_unit']:.2f} ns/{r['unit']}  {'MATCH' if r['match'] else 'DRIFT'}",
        flush=True,
    )
    return r


def alu_program(n: int) -> list:
    prog = [
        {'load': [('const', 0, 1)]},
        {'load': [('const', 1, 1)]},
    ]
    prog.extend({'alu': [('+', 0, 0, 1)]} for _ in range(n))
    return prog


def main() -> None:
    print('=== Python wrapper / kernel asymptotics ===', flush=True)
    results = []
    dbg = DebugInfo(scratch_map={})
    sizes = [2048, 4096, 8192, 16384]

    print('[1/6] encode_slot', flush=True)
    r = {
        'name': 'encode_slot',
        'family': 'python',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'slot',
        'points': [],
    }
    keys: list = []
    for n in sizes:
        ns = time_fn(7, lambda n=n: [encode_slot('alu', ('+', 0, 0, 1), keys) for _ in range(n)])
        r['points'].append({'n': n, 'ns': ns})
    results.append(finish(r))

    print('[2/6] FastMachine ctor', flush=True)
    r = {
        'name': 'FastMachine.ctor',
        'family': 'python',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'bundle',
        'points': [],
    }
    for n in sizes:
        prog = alu_program(n)
        mem = [0] * 32
        ns = time_fn(3, lambda: Machine(mem, prog, dbg, n_cores=1, value_trace={}))
        r['points'].append({'n': n, 'ns': ns})
    results.append(finish(r))

    print('[3/6] FastMachine.run', flush=True)
    r = {
        'name': 'FastMachine.run',
        'family': 'python',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'op',
        'points': [],
    }
    for n in sizes:
        prog = alu_program(n)
        mem = [0] * 32

        def ctor():
            m = Machine(mem, prog, dbg, n_cores=1, value_trace={})
            m.enable_debug = False
            m.enable_pause = False
            return m

        ctor_ns = time_fn(3, ctor)

        def both():
            m = ctor()
            m.run()

        both_ns = time_fn(3, both)
        r['points'].append({'n': n, 'ns': max(0.0, both_ns - ctor_ns)})
    results.append(finish(r))

    print('[4/6] PythonMachine.run', flush=True)
    r = {
        'name': 'PythonMachine.run',
        'family': 'python',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'op',
        'points': [],
    }
    py_sizes = [512, 1024, 2048, 4096]
    for n in py_sizes:
        prog = alu_program(n)
        mem = [0] * 32
        ctor_ns = time_fn(3, lambda: PythonMachine(mem, prog, dbg, value_trace={}))

        def both(n=n):
            m = PythonMachine(mem, prog, dbg, value_trace={})
            m.enable_debug = False
            m.enable_pause = False
            m.run()

        both_ns = time_fn(3, both)
        r['points'].append({'n': n, 'ns': max(0.0, both_ns - ctor_ns)})
    results.append(finish(r))

    print('[5/6] mem slice / cores sync', flush=True)
    prog = alu_program(1024)
    m = Machine([0] * 32, prog, dbg, n_cores=1, value_trace={})
    m.enable_debug = False
    m.enable_pause = False
    m.run()
    r = {
        'name': 'mem.__getitem__ slice',
        'family': 'python',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'word',
        'points': [],
    }
    for n in [4, 8, 16, 32]:
        ns = time_fn(9, lambda n=n: m.mem[0:n])
        r['points'].append({'n': n, 'ns': ns})
    results.append(finish(r))

    r = {
        'name': 'cores sync',
        'family': 'python',
        'theoretical': 'O(1)',
        'theory_exp': 0.0,
        'unit': 'call',
        'points': [],
    }
    for n in [1, 2, 4, 8]:
        ns = time_fn(7, lambda: m.cores)
        r['points'].append({'n': n, 'ns': ns})
    results.append(finish(r))

    print('[6/6] KernelBuilder + full kernel run', flush=True)
    r_build = {
        'name': 'KernelBuilder.build_kernel',
        'family': 'kernel',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'item',
        'points': [],
    }
    r_run = {
        'name': 'kernel FastMachine.run',
        'family': 'kernel',
        'theoretical': 'O(n)',
        'theory_exp': 1.0,
        'unit': 'item',
        'points': [],
    }
    configs = [(4, 2, 16), (5, 4, 32), (6, 8, 64), (8, 8, 128)]
    for height, rounds, batch in configs:
        n = rounds * batch
        print(f'  kernel height={height} rounds={rounds} batch={batch} n={n}', flush=True)
        forest = Tree.generate(height)
        inp = Input.generate(forest, batch, rounds)
        mem = build_mem_image(forest, inp)

        def build():
            kb = KernelBuilder()
            kb.build_kernel(forest.height, len(forest.values), len(inp.indices), rounds)
            return kb

        build_ns = time_fn(2, build)
        r_build['points'].append({'n': n, 'ns': build_ns})
        kb = build()

        def run_kernel():
            machine = Machine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, value_trace={})
            machine.enable_pause = False
            machine.enable_debug = False
            machine.run()

        run_ns = time_fn(2, run_kernel)
        r_run['points'].append({'n': n, 'ns': run_ns})
    results.append(finish(r_build))
    results.append(finish(r_run))

    nres = len(results)
    mae = sum(abs(r['empirical_exp'] - r['theory_exp']) for r in results) / nres
    mr2 = sum(r['r2'] for r in results) / nres
    match_rate = sum(1 for r in results if r['match']) / nres
    print(
        f'\n=== python macro metrics ===\nmethods={nres}  macro_MAE(exp)={mae:.3f}  '
        f'macro_R2={mr2:.3f}  match_rate={match_rate:.3f}',
        flush=True,
    )
    payload = {
        'macro': {
            'n_methods': nres,
            'mean_abs_exp_error': mae,
            'mean_r2': mr2,
            'match_rate': match_rate,
        },
        'methods': results,
    }
    out = ROOT / 'build' / 'python_asymptotics.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f'wrote {out}', flush=True)


if __name__ == '__main__':
    main()
