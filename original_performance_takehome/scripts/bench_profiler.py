"""Time the profiler path. Prints progress."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perf_takehome import get_kernel
from vliw_native import encode_program, profile_program, _lib, _phase_ids


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def _line(name: str, samples: list[float]) -> None:
    print(
        f'  {name:<36} mean {statistics.mean(samples):7.2f} ms  '
        f'median {statistics.median(samples):7.2f} ms  '
        f'min {min(samples):7.2f} ms',
        flush=True,
    )


def main() -> int:
    height, rounds, batch = 10, 16, 256
    n_rep = 8
    print(f'profiler bench  {height}/{rounds}/{batch}  reps={n_rep}', flush=True)

    print('[1/6] KernelBuilder', flush=True)
    t0 = time.perf_counter()
    kb = get_kernel(height, 2 ** (height + 1) - 1, batch, rounds, emit_debug=False)
    print(f'  { _ms(t0):.1f} ms  instrs={len(kb.instrs)}', flush=True)

    print('[2/6] encode cold + warm', flush=True)
    t0 = time.perf_counter()
    enc = encode_program(kb.instrs, skip_debug=True)
    cold_enc = _ms(t0)
    t0 = time.perf_counter()
    enc2 = encode_program(kb.instrs, skip_debug=True)
    warm_enc = _ms(t0)
    print(f'  cold {cold_enc:.1f} ms  warm {warm_enc:.1f} ms  same={enc is enc2}', flush=True)

    print('[3/6] phase_ids', flush=True)
    samples = []
    for i in range(n_rep):
        print(f'  phase_ids {i + 1}/{n_rep}', flush=True)
        t0 = time.perf_counter()
        ids = _phase_ids(kb.instrs, kb.phases, True)
        samples.append(_ms(t0))
    _line('phase_ids', samples)
    print(f'    billed_phases={len(ids or [])}', flush=True)

    print('[4/6] profile_program first + repeats', flush=True)
    t0 = time.perf_counter()
    prof = profile_program(
        kb.instrs,
        omit_debug=True,
        phases=kb.phases,
        scratch_debug=kb.scratch_debug,
    )
    first = _ms(t0)
    print(f'  first {first:.1f} ms  cycles_est={prof["cycles_est"]}', flush=True)
    samples = []
    for i in range(n_rep):
        print(f'  profile {i + 1}/{n_rep}', flush=True)
        t0 = time.perf_counter()
        prof = profile_program(
            kb.instrs,
            omit_debug=True,
            phases=kb.phases,
            scratch_debug=kb.scratch_debug,
        )
        samples.append(_ms(t0))
    _line('profile_program', samples)

    print('[5/6] C++ profile_ex on cached native', flush=True)
    enc.ensure_native()
    lib = _lib()
    samples = []
    for i in range(n_rep):
        print(f'  native {i + 1}/{n_rep}', flush=True)
        t0 = time.perf_counter()
        raw = lib.vliw_program_profile(enc.native, None)
        text = __import__('ctypes').cast(raw, __import__('ctypes').c_char_p).value
        lib.vliw_profile_free(raw)
        samples.append(_ms(t0))
    _line('vliw_program_profile', samples)
    print(f'    json_bytes={len(text or b"")}', flush=True)

    print('[6/6] json.loads of last profile', flush=True)
    samples = []
    blob = json.dumps(prof)
    for i in range(n_rep):
        t0 = time.perf_counter()
        json.loads(blob)
        samples.append(_ms(t0))
    _line('json.loads', samples)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
