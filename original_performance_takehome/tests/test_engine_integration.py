"""Integration tests: KernelBuilder → encode → C++ engine → reference_kernel2."""

from __future__ import annotations

import ctypes
import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perf_takehome import BASELINE, get_kernel, quick_kernel_check
from problem import (
    DebugInfo,
    Input,
    Machine,
    N_CORES,
    PythonMachine,
    Tree,
    build_mem_image,
    reference_final,
    reference_kernel2,
)
from vliw_native import (
    FastMachine,
    VliwProfileExtra,
    VliwSlotDesc,
    _err,
    _lib,
    cpp_available,
    encode_program,
    encode_slot,
    profile_program,
)


def _scenario(height: int, rounds: int, batch: int, seed: int = 123):
    random.seed(seed)
    forest = Tree.generate(height)
    inp = Input.generate(forest, batch, rounds)
    mem = build_mem_image(forest, inp)
    kb = get_kernel(forest.height, len(forest.values), len(inp.indices), rounds, emit_debug=True)
    return forest, inp, mem, kb


def _ref_final(mem: list[int]) -> list[int]:
    return reference_final(list(mem))


class TestFactoryAndCApi(unittest.TestCase):
    def test_machine_factory_is_cpp(self):
        self.assertTrue(cpp_available())
        m = Machine([0] * 8, [{'flow': [('halt',)]}], DebugInfo(scratch_map={}))
        self.assertIsInstance(m, FastMachine)

    def test_c_api_oneslot_add_store(self):
        lib = _lib()
        program = [
            {'load': [('const', 0, 40)]},
            {'load': [('const', 1, 2)]},
            {'alu': [('+', 2, 0, 1)]},
            {'load': [('const', 3, 0)]},
            {'store': [('store', 3, 2)]},
            {'flow': [('halt',)]},
        ]
        keys: list = []
        n = len(program)
        arr = (VliwSlotDesc * n)()
        for i, instr in enumerate(program):
            name, slots = next(iter(instr.items()))
            e, op, dest, a, b, c = encode_slot(name, slots[0], keys)
            arr[i].engine, arr[i].op = e, op
            arr[i].dest, arr[i].a, arr[i].b, arr[i].c = dest, a, b, c
        prog = lib.vliw_program_create()
        self.assertTrue(prog)
        self.assertEqual(lib.vliw_program_load_oneslot(prog, arr, n), 0, _err())
        raw = (ctypes.c_uint32 * 8)(*([0] * 8))
        machine = lib.vliw_machine_create(raw, 8, 1, 1536, prog)
        self.assertTrue(machine, _err())
        lib.vliw_machine_set_flags(machine, 0, 0)
        self.assertEqual(lib.vliw_machine_run(machine), 0, _err())
        self.assertEqual(lib.vliw_machine_cycle(machine), 6)
        mem_ptr = lib.vliw_machine_mem(machine)
        mem = ctypes.cast(mem_ptr, ctypes.POINTER(ctypes.c_uint32))
        self.assertEqual(int(mem[0]), 42)
        lib.vliw_machine_destroy(machine)
        lib.vliw_program_destroy(prog)


class TestKernelVsReference(unittest.TestCase):
    def _run_paused_debug(self, height, rounds, batch, seed=123):
        _forest, inp, mem, kb = _scenario(height, rounds, batch, seed)
        print(
            f'  paused debug-on height={height} rounds={rounds} batch={batch} '
            f'instrs={len(kb.instrs)}',
            flush=True,
        )
        vt: dict = {}
        machine = FastMachine(
            list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, value_trace=vt
        )
        n_yields = 0
        for i, ref in enumerate(reference_kernel2(list(mem), vt)):
            machine.run()
            n_yields += 1
            got = machine.mem[ref[6] : ref[6] + len(inp.values)]
            want = ref[ref[6] : ref[6] + len(inp.values)]
            self.assertEqual(got, want, f'values mismatch after yield {i}')
            got_i = machine.mem[ref[5] : ref[5] + len(inp.indices)]
            want_i = ref[ref[5] : ref[5] + len(inp.indices)]
            self.assertEqual(got_i, want_i, f'indices mismatch after yield {i}')
        self.assertEqual(n_yields, 2)
        return machine

    def _run_submission(self, height, rounds, batch, seed=123):
        _forest, inp, mem, kb = _scenario(height, rounds, batch, seed)
        print(
            f'  submission height={height} rounds={rounds} batch={batch} '
            f'instrs={len(kb.instrs)}',
            flush=True,
        )
        ref = _ref_final(mem)
        machine = FastMachine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, value_trace={})
        machine.enable_pause = False
        machine.enable_debug = False
        machine.run()
        self.assertEqual(
            machine.mem[ref[6] : ref[6] + len(inp.values)],
            ref[ref[6] : ref[6] + len(inp.values)],
        )
        self.assertEqual(
            machine.mem[ref[5] : ref[5] + len(inp.indices)],
            ref[ref[5] : ref[5] + len(inp.indices)],
        )
        return machine, kb

    def test_small_paused_debug_matches_reference(self):
        print('[1/9] small paused debug-on', flush=True)
        m = self._run_paused_debug(3, 2, 8)
        self.assertGreater(m.cycle, 0)

    def test_small_submission_matches_reference(self):
        print('[2/9] small submission path', flush=True)
        m, _ = self._run_submission(3, 2, 8)
        self.assertGreater(m.cycle, 0)

    def test_medium_submission_two_seeds(self):
        print('[3/9] medium submission two seeds', flush=True)
        cycles = []
        for seed in (123, 999):
            m, _ = self._run_submission(5, 4, 16, seed=seed)
            cycles.append(m.cycle)
        self.assertEqual(cycles[0], cycles[1], 'cycle count must be data-independent')

    def test_full_submission_baseline_cycles(self):
        print('[4/9] full 10/16/256 submission', flush=True)
        m, kb = self._run_submission(10, 16, 256)
        self.assertEqual(m.cycle, BASELINE)
        self.assertGreater(len(kb.instrs), 100000)

    def test_full_paused_debug_matches_reference(self):
        print('[5/9] full 10/16/256 paused debug-on', flush=True)
        m = self._run_paused_debug(10, 16, 256)
        self.assertEqual(m.cycle, BASELINE)

    def test_cpp_matches_python_on_small_kernel(self):
        print('[6/9] FastMachine vs PythonMachine small kernel', flush=True)
        _forest, inp, mem, kb = _scenario(3, 2, 8)
        vt: dict = {}
        py = PythonMachine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, value_trace=vt)
        cpp = FastMachine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, value_trace=vt)
        for ref in reference_kernel2(list(mem), vt):
            py.run()
            cpp.run()
            p = ref[6]
            n = len(inp.values)
            self.assertEqual(py.mem[p : p + n], cpp.mem[p : p + n])
            self.assertEqual(py.cycle, cpp.cycle)
        self.assertEqual(py.cycle, cpp.cycle)

    def test_submission_second_run_is_stable(self):
        print('[7/9] second run after halt/end does not change mem', flush=True)
        _forest, inp, mem, kb = _scenario(3, 2, 8)
        m = FastMachine(list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, value_trace={})
        m.enable_pause = False
        m.enable_debug = False
        m.run()
        cycles = m.cycle
        values = m.mem[mem[6] : mem[6] + len(inp.values)]
        m.run()
        self.assertEqual(m.cycle, cycles)
        self.assertEqual(m.mem[mem[6] : mem[6] + len(inp.values)], values)


class TestMultiSlotLoadPath(unittest.TestCase):
    def test_deferred_bundle_through_fastmachine(self):
        program = [
            {'load': [('const', 0, 5)]},
            {'load': [('const', 1, 7)]},
            {'alu': [('+', 0, 0, 1), ('+', 2, 0, 0)]},
            {'load': [('const', 3, 0)]},
            {'store': [('store', 3, 2)]},
        ]
        info = DebugInfo(scratch_map={})
        py = PythonMachine([0] * 8, program, info)
        cpp = FastMachine([0] * 8, program, info)
        py.enable_pause = False
        cpp.enable_pause = False
        py.enable_debug = False
        cpp.enable_debug = False
        py.run()
        cpp.run()
        self.assertEqual(py.cycle, cpp.cycle)
        self.assertEqual(cpp.mem[0], 10)
        self.assertEqual(cpp.cores[0].scratch[0], 12)
        self.assertEqual(cpp.cores[0].scratch[2], 10)


class TestFastCheckPath(unittest.TestCase):
    def test_get_kernel_reuses_builder(self):
        a = get_kernel(3, 15, 8, 2, emit_debug=False)
        b = get_kernel(3, 15, 8, 2, emit_debug=False)
        self.assertIs(a, b)
        debug = get_kernel(3, 15, 8, 2, emit_debug=True)
        self.assertIsNot(a, debug)
        self.assertGreater(len(debug.instrs), len(a.instrs))

    def test_no_debug_kernel_matches_baseline(self):
        print('[8/9] emit_debug=False full kernel', flush=True)
        random.seed(123)
        forest = Tree.generate(10)
        inp = Input.generate(forest, 256, 16)
        mem = build_mem_image(forest, inp)
        kb = get_kernel(forest.height, len(forest.values), len(inp.indices), 16, emit_debug=False)
        ref = _ref_final(mem)
        machine = FastMachine(
            list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, omit_debug=True
        )
        machine.enable_pause = False
        machine.enable_debug = False
        machine.run()
        self.assertEqual(machine.cycle, BASELINE)
        self.assertEqual(
            machine.mem[ref[6] : ref[6] + len(inp.values)],
            ref[ref[6] : ref[6] + len(inp.values)],
        )

    def test_quick_kernel_check(self):
        print('[9/9] quick_kernel_check 10/16/256', flush=True)
        cycles = quick_kernel_check(10, 16, 256)
        self.assertEqual(cycles, BASELINE)


class TestProfileIntegration(unittest.TestCase):
    def test_small_profile_matches_run_and_check(self):
        print('[profile 1/6] 3/2/8 profile == run == quick_kernel_check', flush=True)
        height, rounds, batch = 3, 2, 8
        _forest, inp, mem, _kb = _scenario(height, rounds, batch)
        kb = get_kernel(height, 2 ** (height + 1) - 1, batch, rounds, emit_debug=False)
        prof = profile_program(
            kb.instrs,
            omit_debug=True,
            phases=kb.phases,
            scratch_debug=kb.scratch_debug,
        )
        machine = FastMachine(
            list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, omit_debug=True
        )
        machine.enable_pause = False
        machine.enable_debug = False
        machine.run()
        checked = quick_kernel_check(height, rounds, batch)
        print(
            f'    cycles_est={prof["cycles_est"]} run={machine.cycle} check={checked}',
            flush=True,
        )
        self.assertEqual(prof['cycles_est'], machine.cycle)
        self.assertEqual(prof['cycles_est'], checked)
        self.assertEqual(
            machine.mem[mem[6] : mem[6] + len(inp.values)],
            _ref_final(mem)[mem[6] : mem[6] + len(inp.values)],
        )
        phase_sum = sum((prof.get('phases') or {}).values())
        self.assertEqual(phase_sum, prof['cycles_est'])
        names = {row['name'] for row in prof['named_live']}
        self.assertIn('tmp_val', names)
        self.assertTrue(prof['hypotheses'])
        self.assertEqual(len(kb.phases), len(kb.instrs))

    def test_profile_independent_of_memory(self):
        print('[profile 2/6] fingerprint stable across seeds', flush=True)
        kb = get_kernel(3, 15, 8, 2, emit_debug=False)
        a = profile_program(kb.instrs, phases=kb.phases, scratch_debug=kb.scratch_debug)
        b = profile_program(kb.instrs, phases=kb.phases, scratch_debug=kb.scratch_debug)
        self.assertEqual(a['fingerprint'], b['fingerprint'])
        self.assertEqual(a['cycles_est'], b['cycles_est'])
        again = profile_program(
            kb.instrs,
            phases=kb.phases,
            scratch_debug=kb.scratch_debug,
            prev_json=json.dumps(a),
        )
        self.assertTrue(again['diff']['same_program'])
        self.assertEqual(again['diff']['cycles_est'], 0)

    def test_omit_debug_matches_nodebug_kernel(self):
        print('[profile 3/6] omit_debug profile == emit_debug=False kernel', flush=True)
        debug = get_kernel(3, 15, 8, 2, emit_debug=True)
        slim = get_kernel(3, 15, 8, 2, emit_debug=False)
        keep = profile_program(debug.instrs, omit_debug=False)
        skip = profile_program(debug.instrs, omit_debug=True, phases=debug.phases)
        slim_p = profile_program(slim.instrs, omit_debug=True, phases=slim.phases)
        self.assertGreater(keep['debug_bundles'], 0)
        self.assertEqual(skip['debug_bundles'], 0)
        self.assertEqual(slim_p['debug_bundles'], 0)
        self.assertEqual(keep['cycles_est'], skip['cycles_est'])
        self.assertEqual(skip['cycles_est'], slim_p['cycles_est'])
        self.assertEqual(skip['alu_ops'], slim_p['alu_ops'])

    def test_c_api_profile_ex_roundtrip(self):
        print('[profile 4/6] C API profile_ex on encoded kernel', flush=True)
        kb = get_kernel(3, 15, 8, 2, emit_debug=False)
        encoded = encode_program(kb.instrs, skip_debug=True)
        lib = _lib()
        prog = lib.vliw_program_create()
        self.assertTrue(prog, _err())
        try:
            encoded.load_into(prog)
            extra = VliwProfileExtra()
            names = [n.encode('utf-8') for _, (n, _) in kb.scratch_debug.items()]
            addrs = [int(a) for a in kb.scratch_debug]
            lens = [int(ln) for _, ln in kb.scratch_debug.values()]
            n = len(addrs)
            addr_arr = (ctypes.c_uint32 * n)(*addrs)
            len_arr = (ctypes.c_uint16 * n)(*lens)
            name_arr = (ctypes.c_char_p * n)(*names)
            extra.scratch_addr = addr_arr
            extra.scratch_len = len_arr
            extra.scratch_names = name_arr
            extra.n_scratch = n
            raw = lib.vliw_program_profile_ex(prog, None, ctypes.byref(extra))
            self.assertTrue(raw, _err())
            try:
                text = ctypes.cast(raw, ctypes.c_char_p).value.decode('utf-8')
                prof = json.loads(text)
            finally:
                lib.vliw_profile_free(raw)
        finally:
            lib.vliw_program_destroy(prog)
        self.assertGreater(prof['cycles_est'], 0)
        self.assertIn('tmp_val', {row['name'] for row in prof['named_live']})
        self.assertIn('floor_engine', prof)
        self.assertIn('hypotheses', prof)

    def test_full_profile_matches_baseline(self):
        print('[profile 5/6] 10/16/256 profile == BASELINE', flush=True)
        n_nodes = 2 ** 11 - 1
        kb = get_kernel(10, n_nodes, 256, 16, emit_debug=False)
        prof = profile_program(
            kb.instrs,
            omit_debug=True,
            phases=kb.phases,
            scratch_debug=kb.scratch_debug,
        )
        print(
            f'    cycles_est={prof["cycles_est"]} floor={prof["floor"]} '
            f'{prof["floor_engine"]} overhead={prof["overhead"]}',
            flush=True,
        )
        self.assertEqual(prof['cycles_est'], BASELINE)
        self.assertEqual(prof['mix_imbalance'], 'scalar_alu')
        self.assertEqual(prof['valu_ops'], 0)
        self.assertGreater(prof['gather_scalar'], 0)
        self.assertGreater(prof['phase_hash'], prof['phase_store'])
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertTrue({'pipeline', 'oneslot', 'valu_unused', 'gather'} & tags)

    def test_check_prof_only_smoke(self):
        print('[profile 6/6] check.py --prof-only --smoke', flush=True)
        proc = subprocess.run(
            [sys.executable, '-u', str(ROOT / 'check.py'), '--prof-only', '--smoke'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('correct=true', out)
        self.assertIn('floor=', out)
        self.assertIn('hyp  ', out)
        last = ROOT / '_last_profile.json'
        self.assertTrue(last.is_file(), out)
        prof = json.loads(last.read_text(encoding='utf-8'))
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], prof['cycles_run'])


def main() -> int:
    print('engine integration tests', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
