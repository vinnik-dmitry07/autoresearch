"""Wall-clock of every stage from process start to trace / metrics / profile."""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

T_START = time.perf_counter()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

t0 = time.perf_counter()
from perf_takehome import BASELINE, get_kernel, quick_kernel_check
from problem import Input, Machine, N_CORES, PythonMachine, Tree, build_mem_image, reference_final
from vliw_native import encode_program, profile_program, _lib

IMPORT_S = time.perf_counter() - t0


def _ms(t: float) -> float:
    return t * 1000.0


def _line(i: int, n: int, name: str, seconds: float, extra: str = '') -> None:
    extra_s = f'  {extra}' if extra else ''
    print(f'[{i}/{n}] {name:<34} {_ms(seconds):8.1f} ms{extra_s}', flush=True)


def main() -> int:
    n = 14
    print('all-stages bench  official 10/16/256 + smoke + trace 5/4/16', flush=True)
    _line(1, n, 'imports', IMPORT_S)
    _line(2, n, 'process start -> after imports', time.perf_counter() - T_START)

    print('[3/14] KernelBuilder 10/16/256 cold', flush=True)
    t0 = time.perf_counter()
    kb = get_kernel(10, 2 ** 11 - 1, 256, 16, emit_debug=False)
    build_s = time.perf_counter() - t0
    _line(3, n, 'KernelBuilder cold', build_s, f'instrs={len(kb.instrs)}')

    t0 = time.perf_counter()
    kb2 = get_kernel(10, 2 ** 11 - 1, 256, 16, emit_debug=False)
    _line(4, n, 'KernelBuilder cached', time.perf_counter() - t0, f'same={kb is kb2}')

    print('[5/14] encode + native load', flush=True)
    t0 = time.perf_counter()
    enc = encode_program(kb.instrs, skip_debug=True)
    encode_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    enc.ensure_native()
    native_s = time.perf_counter() - t0
    _line(5, n, 'encode cold', encode_s, f'slots={enc.n_slots}')
    _line(5, n, 'native load', native_s)

    print('[6/14] forest / input / mem image', flush=True)
    t0 = time.perf_counter()
    random.seed(123)
    forest = Tree.generate(10)
    gen_forest = time.perf_counter() - t0
    t0 = time.perf_counter()
    inp = Input.generate(forest, 256, 16)
    gen_inp = time.perf_counter() - t0
    t0 = time.perf_counter()
    mem = build_mem_image(forest, inp)
    gen_mem = time.perf_counter() - t0
    _line(6, n, 'Tree.generate', gen_forest)
    _line(6, n, 'Input.generate', gen_inp)
    _line(6, n, 'build_mem_image', gen_mem)

    print('[7/14] Machine ctor + run + reference', flush=True)
    t0 = time.perf_counter()
    machine = Machine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, omit_debug=True)
    ctor_s = time.perf_counter() - t0
    machine.enable_pause = False
    machine.enable_debug = False
    t0 = time.perf_counter()
    machine.run()
    run_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    ref = reference_final(list(mem))
    ref_s = time.perf_counter() - t0
    ok = machine.mem[ref[6] : ref[6] + len(inp.values)] == ref[ref[6] : ref[6] + len(inp.values)]
    _line(7, n, 'Machine ctor', ctor_s)
    _line(7, n, 'Machine.run', run_s, f'cycles={machine.cycle} ok={ok}')
    _line(7, n, 'reference_final', ref_s)

    print('[8/14] profile first (phases + scratch)', flush=True)
    t0 = time.perf_counter()
    prof = profile_program(
        kb.instrs,
        omit_debug=True,
        phases=kb.phases,
        scratch_debug=kb.scratch_debug,
    )
    prof1_s = time.perf_counter() - t0
    _line(8, n, 'profile_program first', prof1_s, f'cycles_est={prof["cycles_est"]}')

    t0 = time.perf_counter()
    prof2 = profile_program(
        kb.instrs,
        omit_debug=True,
        phases=kb.phases,
        scratch_debug=kb.scratch_debug,
    )
    prof2_s = time.perf_counter() - t0
    _line(9, n, 'profile_program repeat', prof2_s, f'fp={prof2["fingerprint"][:8]}')

    print('[10/14] C++ profile_ex only', flush=True)
    lib = _lib()
    t0 = time.perf_counter()
    raw = lib.vliw_program_profile(enc.native, None)
    cpp_s = time.perf_counter() - t0
    import ctypes

    n_json = len(ctypes.cast(raw, ctypes.c_char_p).value or b'')
    lib.vliw_profile_free(raw)
    _line(10, n, 'vliw_program_profile', cpp_s, f'json={n_json} B')

    print('[11/14] quick_kernel_check cached', flush=True)
    t0 = time.perf_counter()
    cycles = quick_kernel_check(10, 16, 256)
    check_s = time.perf_counter() - t0
    _line(11, n, 'quick_kernel_check', check_s, f'cycles={cycles} baseline={BASELINE}')

    print('[12/14] smoke 3/2/8 profile + check', flush=True)
    t0 = time.perf_counter()
    kb_s = get_kernel(3, 15, 8, 2, emit_debug=False)
    smoke_build = time.perf_counter() - t0
    t0 = time.perf_counter()
    smoke_prof = profile_program(
        kb_s.instrs, omit_debug=True, phases=kb_s.phases, scratch_debug=kb_s.scratch_debug
    )
    smoke_prof_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    smoke_cycles = quick_kernel_check(3, 2, 8)
    smoke_check = time.perf_counter() - t0
    _line(12, n, 'smoke KernelBuilder', smoke_build, f'instrs={len(kb_s.instrs)}')
    _line(12, n, 'smoke profile', smoke_prof_s, f'cycles_est={smoke_prof["cycles_est"]}')
    _line(12, n, 'smoke quick_kernel_check', smoke_check, f'cycles={smoke_cycles}')

    print('[13/14] write_small_trace 5/4/16 (PythonMachine)', flush=True)
    dest = ROOT / '_stage_trace.json'
    dest.unlink(missing_ok=True)
    old = ROOT / 'trace.json'
    saved = old.read_bytes() if old.is_file() else None
    try:
        t0 = time.perf_counter()
        random.seed(123)
        tr_forest = Tree.generate(5)
        tr_inp = Input.generate(tr_forest, 16, 4)
        tr_mem = build_mem_image(tr_forest, tr_inp)
        gen_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        tr_kb = get_kernel(
            tr_forest.height, len(tr_forest.values), len(tr_inp.indices), 4, emit_debug=False
        )
        tr_build = time.perf_counter() - t0
        t0 = time.perf_counter()
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
        ctor_tr = time.perf_counter() - t0
        t0 = time.perf_counter()
        pym.run()
        run_tr = time.perf_counter() - t0
        tr_cycles = pym.cycle
        del pym
        t0 = time.perf_counter()
        if dest.resolve() != old.resolve() and old.is_file():
            dest.write_bytes(old.read_bytes())
        write_s = time.perf_counter() - t0
        size = dest.stat().st_size if dest.is_file() else old.stat().st_size
        _line(13, n, 'trace data gen 5/4/16', gen_s)
        _line(13, n, 'trace KernelBuilder', tr_build, f'instrs={len(tr_kb.instrs)}')
        _line(13, n, 'PythonMachine ctor+trace open', ctor_tr)
        _line(13, n, 'PythonMachine.run (writes JSON)', run_tr, f'cycles={tr_cycles}')
        _line(13, n, 'copy trace artifact', write_s, f'size={size / 1e6:.2f} MB')
        trace_total = gen_s + tr_build + ctor_tr + run_tr + write_s
        _line(13, n, 'trace path total', trace_total)
    finally:
        dest.unlink(missing_ok=True)
        if saved is None:
            old.unlink(missing_ok=True)
        else:
            old.write_bytes(saved)

    print('[14/14] write last-profile JSON', flush=True)
    t0 = time.perf_counter()
    blob = json.dumps(prof, indent=2) + '\n'
    dump_s = time.perf_counter() - t0
    _line(14, n, 'json.dumps profile', dump_s, f'bytes={len(blob)}')

    total = time.perf_counter() - T_START
    print('', flush=True)
    print('--- totals from process start ---', flush=True)
    print(
        f'  to first full profile+run metrics:  '
        f'{_ms(IMPORT_S + build_s + encode_s + native_s + gen_forest + gen_inp + gen_mem + ctor_s + run_s + ref_s + prof1_s):.1f} ms',
        flush=True,
    )
    print(f'  this script wall:                   {_ms(total):.1f} ms', flush=True)
    print(
        f'  official loop (cached):             '
        f'profile { _ms(prof2_s):.1f} + run { _ms(check_s):.1f} = {_ms(prof2_s + check_s):.1f} ms',
        flush=True,
    )
    return 0 if ok and cycles == BASELINE else 1


if __name__ == '__main__':
    raise SystemExit(main())
