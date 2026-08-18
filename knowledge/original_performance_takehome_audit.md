# Audit: `original_performance_takehome`

Target: `original_performance_takehome/` on branch `autoresearch/aug17`
(commit `c10467f`, "Add the VLIW takehome with native engine and profiler").
Everything below was executed, not inferred; commands are given so each claim is re-runnable.

## What the folder is

Anthropic's original performance-engineering take-home. A VLIW/SIMD machine is simulated in
Python; the task is to rewrite `KernelBuilder.build_kernel` (`perf_takehome.py`) so a
tree-walk + 32-bit-hash kernel finishes in as few **simulated clock cycles** as possible.
The score comes from `tests/submission_tests.py`, which runs the *frozen* pure-Python
simulator in `tests/frozen_problem.py`. Baseline is 147,734 cycles.

On top of the take-home, this copy adds ~10k lines of owner-built infrastructure:

| Component | Files | Lines |
|---|---|---|
| C++ reimplementation of the simulator | `src/machine.cpp`, `include/machine.hpp`, `src/c_api.cpp`, `vliw_native.py` | ~2,200 |
| Static analyzer / profiler | `src/profiler.cpp`, `include/profiler.hpp` | ~1,700 |
| Native test suites | `tests/*.cpp`, `tests/test_*.py` | ~3,900 |
| Benchmarks & tooling | `check.py`, `scripts/`, `tools/`, `watch_trace.*` | ~2,200 |

`tests/frozen_problem.py` is the pristine upstream `problem.py`; the root `problem.py` has been
extended by the owner (native dispatch, unrolled `myhash`, `reference_final`).

## Headline: the deliverable is not started

```
$ python tests/submission_tests.py
CYCLES: 147734        Speedup over baseline: 1.000
Ran 9 tests — 1 passed (correctness), 8 failed (every speed threshold)
```

147,734 is **exactly** `BASELINE`. Even `test_kernel_speedup`, which only requires
`cycles() < 147734` — a single cycle of improvement — fails.

Cycle count equals the emitted slot count exactly (147,734 slots, IPC 1.00), because
`build_kernel` still emits one slot per instruction bundle. Distance to each published
threshold:

| Threshold | Cycles | Speedup needed | Status |
|---|---|---|---|
| `test_kernel_speedup` | < 147,734 | 1.0x | FAIL |
| updated starter code | < 18,532 | 8.0x | FAIL |
| Opus 4, many hours | < 2,164 | 68.3x | FAIL |
| Opus 4.5, casual (≈ best human in 2h) | < 1,790 | 82.5x | FAIL |
| Opus 4.5, 2h harness | < 1,579 | 93.6x | FAIL |
| Sonnet 4.5, many hours | < 1,548 | 95.4x | FAIL |
| Opus 4.5, 11.5h harness | < 1,487 | 99.4x | FAIL |
| Opus 4.5, improved harness | < 1,363 | 108.4x | FAIL |

What exists is a very good *measurement rig* for an optimization that has not begun.

## Score integrity: clean

The Readme warns that most sub-1300 submissions on day one were models editing the tests. Six
independent checks, all passing:

1. `tests/frozen_problem.py`'s `Machine` class is **byte-identical** to `problem.py`'s
   `PythonMachine` (diff of the two class bodies is empty).
2. The owner's unrolled `problem.myhash` matches the frozen loop version on **200,005** inputs
   including `0`, `1`, `2**31`, `2**32-1`.
3. `problem.reference_final` and the fast untraced `reference_kernel2` path produce memory
   **identical** to the frozen traced reference.
4. `emit_debug=True` and `emit_debug=False` emit **byte-identical billed slot sequences**
   (147,734 both) at three shapes — the fast iteration path and the scored path agree today.
5. Thresholds in `tests/submission_tests.py` (1363 / 1487 / 1548 / 1579 / 1790 / 2164 / 18532)
   exactly match the numbers quoted in `Readme.md`, and both `BASELINE = 147734` constants
   agree with the measured unmodified kernel.
6. The owner's own detector agrees: `integrity hash=True stores=True mux=False
   skip_hash=False cheat=False`.

Fidelity of the native engine against the scoring oracle, measured two ways:

- **Real workload**: identical cycles *and* identical final memory at 5 shapes
  (`10/16/256`, `6/9/64`, `4/6/32`, `3/5/16`, `2/4/8`), with and without debug slots.
  Native is **1,100–1,900x faster** (0.46 s → 0.0004 s at the official shape).
- **Differential fuzz**: 1,800 random programs (900 one-slot-per-bundle, 900 packed to the port
  limits), comparing cycles, full memory, full scratch and trace buffer.
  **1,800 / 1,800 agree exactly.**

All 10 `ctest` suites pass; `check.py`, `scripts/audit_score.py --run` and
`scripts/bench_pipeline_regression.py --check` all pass.

## Findings

### F1 — `tests/` contains 11 added files, which breaks the submission protocol (High, process)

`Readme.md` prescribes:

```
# This should be empty, the tests folder must be unchanged
git diff origin/main tests/
```

`tests/` now tracks 13 files. Two are upstream (`frozen_problem.py`, `submission_tests.py`);
**eleven are owner-added**: `test_engine.py`, `test_engine_e2e.py`, `test_engine_integration.py`,
`test_profiler_e2e.py`, `test_profiler_integration.py`, `test_profiler_metrics.py`,
`engine_tests.cpp`, `engine_integration_tests.cpp`, `profiler_tests.cpp`,
`bench_asymptotics.cpp`, `test_util.hpp`.

They are benign — the six checks above prove the scoring files are untouched — but a reviewer
running the prescribed command sees a dirty `tests/`, which is precisely the signal the Readme
says means cheating. Anyone submitting this would be arguing against their own evidence.

**Fix**: move the native suites to `tests_native/` and update the `add_test`/
`target_include_directories` entries in `CMakeLists.txt`. Leave `tests/` upstream-pristine.

### F2 — The native engine has no bounds checking and diverges from the oracle on every error path (High, correctness of the tooling)

`exec_direct` in `src/machine.cpp:75` does raw `mem[...]` / `scratch[...]` reads and writes with
no bounds check. It is used for **every single-slot bundle**, and `run_checked` (`:646`) routes
single-slot bundles to it too — so `enable_debug=True` does not buy checking, and the entire
current kernel runs unchecked on every path.

Measured against `tests/frozen_problem.Machine`:

| Case | Frozen Python (the oracle) | Native engine |
|---|---|---|
| `load` from out-of-range address | `IndexError` | **SEGFAULT** |
| `store` to out-of-range address (1-slot) | `IndexError` | **SEGFAULT** |
| `store` to out-of-range address (multi-slot) | `IndexError` | silently grows `mem` |
| vector write past end of scratch | `IndexError` | **HANG** (heap corruption) |
| `//` by zero | `ZeroDivisionError` | returns `0` |
| `%` by zero | `ZeroDivisionError` | returns `0` |
| `cdiv` by zero | `ZeroDivisionError` | returns `0` |

Minimal repro (2 instructions):

```python
prog = [{"load": [("const", 0, 4000000)]}, {"load": [("load", 1, 0)]}]
# frozen: IndexError: list index out of range
# native: Segmentation fault (whole Python process dies)
```

This does not affect the score — the scored run uses the frozen Python `Machine`. It affects the
thing the engine exists for. The optimization work ahead (SIMD packing, `vload`/`vstore`,
select-trees, scratch tiling) is exactly the work where address arithmetic goes wrong, and today
a mistake there kills the interpreter or hangs instead of printing a line number, while a
div/mod bug yields a plausible wrong answer instead of an exception.

**Fix**: give `exec_direct` a compile-time `checked` template parameter so the checked build
validates `mem` and `scratch` indices while the fast path stays branch-free; make div/mod/cdiv
by zero `fail()` instead of returning 0. Then run the checked engine in `check.py` and the fast
one only for timing.

### F3 — Linux build is broken: static lib not compiled with `-fPIC` (Medium)

`vliw_engine` is a `STATIC` library linked into the `SHARED` `vliw_machine`
(`CMakeLists.txt:19-31`). GCC/ld refuses:

```
/usr/bin/ld: libvliw_engine.a(machine.cpp.o): relocation R_X86_64_PC32 against symbol
  '_ZN4vliw10kSlotLimitE' can not be used when making a shared object; recompile with -fPIC
/usr/bin/ld: final link failed: bad value
```

Only `build.bat`, `check.bat`, `perfetto.bat` exist — no shell equivalents — so the project is
MSVC/Windows-only in practice, where this link happens to work. Everything in this audit needed
`-DCMAKE_POSITION_INDEPENDENT_CODE=ON` to build at all.

**Fix**: one line —
`set_property(TARGET vliw_engine PROPERTY POSITION_INDEPENDENT_CODE ON)`. A `build.sh` alongside
`build.bat` would make the repo portable.

### F4 — `trace_write` results are silently lost in the native engine (Medium)

The C++ side does populate `core.trace_buf` (`src/machine.cpp:183`, `:357`, `:816`), but
`vliw_native.FastMachine._sync_cores` copies only `pc`, `state` and `scratch` back from native —
there is no C API accessor for the trace buffer. So `FastMachine.cores[i].trace_buf` is always
empty:

```
frozen Python        cycle=4  trace_buf=[42, 42]
native FastMachine   cycle=4  trace_buf=[]
```

`trace_write` is one of the ISA's debugging affordances, so this quietly removes a tool.
Found by differential fuzzing; `tests/test_engine.py` has no `trace_write` agreement case.

**Fix**: add `vliw_machine_trace_buf(m, core, &n)` to the C API and copy it in `_sync_cores`;
add the agreement case to the native suite.

### F5 — The tamper guard prints digests but never checks them (Medium)

`check.py::_print_audit` prints `sha256=...` for the three scoring files and a
`frozen_vs_problem same|differ` line, and compares nothing. Since `problem.py` legitimately
diverged from the frozen copy, that line now always reads `differ`, so the signal is dead —
it can no longer distinguish a legitimate divergence from a weakened oracle.

**Fix**: pin the expected digests of `tests/submission_tests.py` and `tests/frozen_problem.py`
in a constant and make `check.py` / `scripts/audit_score.py` exit non-zero on mismatch. Replace
the byte-compare with the semantic equivalence checks (the `myhash` and reference-path
comparisons in the "Score integrity" section above are exactly the right assertions).

### F6 — `get_kernel` cache key covers only one function (Low)

`perf_takehome.py:543`:

```python
src = hash(KernelBuilder.build_kernel.__code__.co_code)
```

Edits to `_emit_rounds_nodebug`, `build_hash`, `add_rows`, `_repeat_body` or `ensure_encoded` do
not invalidate the cache. Harmless for a one-shot `python check.py`, but a long-lived tuning
loop or a `watch_trace` process can serve a stale kernel and report the previous cycle count as
if it were the new one — the worst possible failure mode in an optimization loop.

**Fix**: fold the `co_code` of every builder method into the key, or key on a hash of
`perf_takehome.py` itself.

### F7 — Write-buffer headroom is thin and unguarded (Low)

`include/machine.hpp:14-15` sets `kMaxScratchWrites = 128`, `kMaxMemWrites = 32`. The legal
maxima under `kSlotLimit = {12, 6, 2, 2, 1, 64}` are 84 scratch writes
(12 alu + 6 valu x 8 + 2 load x 8 + 1 flow x 8) and 16 mem writes (2 vstore x 8), so it is safe
today. But `write_scratch` / `write_mem` do not bounds-check, so raising any `SLOT_LIMITS` entry
turns into a stack buffer overflow rather than an error.

**Fix**: a `static_assert` deriving the two constants from `kSlotLimit`, plus a `fail()` guard.

## What is genuinely good

- The native engine is faithful where it matters: identical cycles and memory on the real
  workload at five shapes, and 1,800/1,800 random programs agree exactly on cycles, memory and
  scratch once the F2 error paths are excluded.
- 1,100–1,900x faster than the Python simulator, with graceful fallback to `PythonMachine` when
  the shared library is absent (verified by removing `build/libvliw_machine.so`: `check.py`
  still runs and still reports 147,734).
- `scripts/bench_pipeline_regression.py --check` locks per-stage timings *and* profiler metrics,
  so a silent metric drift fails CI. All 17 stages within budget.
- The profiler is the strongest piece of work here. It already names the right optimizations,
  in the right order, with quantities attached.

## The work that remains, per the project's own profiler

```
$ python scripts/audit_score.py --run
cycles_est=147734  ipc=1.00  bottleneck=deps  cycles_run=147734
floor=9899 alu  overhead=137835 (93.3%)  cp_raw=26  cp_waw=90121
alu=0.80/12  valu=0.00/6  load=0.09/2  store=0.06/2  flow=0.06/1
limit={'flow': 8193, 'policy': 139540, 'none': 1}
bounds  valu=0  gather=6148  fused_hash=1024  useful=1093
peak_live=273/1536   gather  load.load=12295  vload=0  vselect=0  madd=0
```

- **IPC is exactly 1.00** and 139,540 of 147,734 cycles (94.5%) are limited by the *one-slot
  issue policy*, not by any port. Packing alone, at the current op mix, floors at 9,899
  cycles — **14.9x** for no algorithmic change.
- **SIMD is completely unused**: `valu=0.00/6`, `vload=0`, `vselect=0`, `madd=0`, while the hash
  is 73,728 of the alu slots and is perfectly lane-parallel across the 256-element batch.
- **The critical path is WAW, not RAW**: `cp_waw=90121` vs `cp_raw=26`. Four shared temps
  (`tmp1`, `tmp2`, `tmp3`, `tmp_val`, `tmp_idx`, `tmp_addr`, `tmp_node_val`) serialize
  everything, while `peak_live=273/1536` leaves 82% of scratch unused. Per-lane renaming is
  nearly free.
- The profiler's own achievable estimate is **`useful=1093`** cycles — below the best published
  Claude result (1,363).

Order implied by the tool's hypotheses (`valu_unused`, `oneslot`, `store_lifetime`, `gather`,
`gather_depth`): vectorize the hash across lanes → rename temps per lane to break the WAW chain
→ replace shallow-depth scalar gathers with select-trees and `vload` → then pack bundles up to
the port limits.

## Reproducing this audit

```bash
cd original_performance_takehome
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON        # workaround for F3
cmake --build build -j
(cd build && ctest --output-on-failure)            # 10/10 pass
python tests/submission_tests.py                  # 147734, 1 pass / 8 fail
python check.py
python scripts/audit_score.py --run
python scripts/bench_pipeline_regression.py --check --cli
```

The differential fuzzer and the divergence-table script written for this audit are not committed;
they are ~120 lines each and are described precisely enough above to rebuild.
