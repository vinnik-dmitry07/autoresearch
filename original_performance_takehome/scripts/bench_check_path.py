"""Time the local check path: KernelBuilder + ctor + run + reference_final."""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perf_takehome import BASELINE, get_kernel, quick_kernel_check
from problem import Input, Machine, N_CORES, Tree, build_mem_image, reference_final
from vliw_native import encode_program


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def main() -> int:
    height, rounds, batch = 10, 16, 256
    steps = 7
    print(f'check-path bench  {height}/{rounds}/{batch}', flush=True)

    print(f'[1/{steps}] cold KernelBuilder emit_debug=False', flush=True)
    t0 = time.perf_counter()
    kb = get_kernel(height, 2 ** (height + 1) - 1, batch, rounds, emit_debug=False)
    build_ms = _ms(t0)
    print(f'  {build_ms:.1f} ms  instrs={len(kb.instrs)}', flush=True)

    print(f'[2/{steps}] cached KernelBuilder', flush=True)
    t0 = time.perf_counter()
    kb2 = get_kernel(height, 2 ** (height + 1) - 1, batch, rounds, emit_debug=False)
    cached_build_ms = _ms(t0)
    print(f'  {cached_build_ms:.1f} ms  same={kb is kb2}', flush=True)

    print(f'[3/{steps}] cold encode + native load', flush=True)
    t0 = time.perf_counter()
    enc = encode_program(kb.instrs, skip_debug=True)
    encode_ms = _ms(t0)
    t0 = time.perf_counter()
    enc.ensure_native()
    native_ms = _ms(t0)
    print(f'  encode {encode_ms:.1f} ms  native {native_ms:.1f} ms  slots={enc.n_slots}', flush=True)

    print(f'[4/{steps}] cached encode', flush=True)
    t0 = time.perf_counter()
    enc2 = encode_program(kb.instrs, skip_debug=True)
    cached_encode_ms = _ms(t0)
    print(f'  {cached_encode_ms:.1f} ms  same={enc is enc2}', flush=True)

    print(f'[5/{steps}] ctor + run + reference_final (cached kernel)', flush=True)
    random.seed(123)
    forest = Tree.generate(height)
    inp = Input.generate(forest, batch, rounds)
    mem = build_mem_image(forest, inp)
    t0 = time.perf_counter()
    machine = Machine(
        mem, kb.instrs, kb.debug_info(), n_cores=N_CORES, omit_debug=True
    )
    ctor_ms = _ms(t0)
    machine.enable_pause = False
    machine.enable_debug = False
    t0 = time.perf_counter()
    machine.run()
    run_ms = _ms(t0)
    t0 = time.perf_counter()
    ref = reference_final(list(mem))
    ref_ms = _ms(t0)
    ok = machine.mem[ref[6] : ref[6] + len(inp.values)] == ref[ref[6] : ref[6] + len(inp.values)]
    print(
        f'  ctor {ctor_ms:.1f} ms  run {run_ms:.1f} ms  ref {ref_ms:.1f} ms  '
        f'cycles={machine.cycle} match={ok}',
        flush=True,
    )
    if machine.cycle != BASELINE or not ok:
        print('FAIL: cycles or memory mismatch', flush=True)
        return 1

    print(f'[6/{steps}] second cached check (quick_kernel_check)', flush=True)
    t0 = time.perf_counter()
    cycles = quick_kernel_check(height, rounds, batch)
    check_ms = _ms(t0)
    print(f'  {check_ms:.1f} ms  cycles={cycles}', flush=True)

    print(f'[7/{steps}] third cached check', flush=True)
    t0 = time.perf_counter()
    cycles = quick_kernel_check(height, rounds, batch)
    check2_ms = _ms(t0)
    print(f'  {check2_ms:.1f} ms  cycles={cycles}', flush=True)

    print(
        f'summary  cold_build={build_ms:.1f}  cached_check={check2_ms:.1f}  '
        f'ctor={ctor_ms:.1f}  run={run_ms:.1f}  ref={ref_ms:.1f}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
