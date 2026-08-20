"""Unit tests: C++ FastMachine vs PythonMachine, plus encode/C API."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from problem import HASH_STAGES, CoreState, DebugInfo, PythonMachine, myhash
from vliw_native import FastMachine, cpp_available, encode_program, encode_slot, profile_program


def _occ_hist(prof: dict, name: str) -> list:
    row = (prof.get('occupancy_hist') or {}).get(name) or {}
    return list(row.get('hist') or [])


def _info() -> DebugInfo:
    return DebugInfo(scratch_map={})


def _make(cls, mem: list[int], program: list, *, pause: bool = True, debug: bool = True,
          value_trace: dict | None = None, n_cores: int = 1):
    machine = cls(
        list(mem),
        program,
        _info(),
        n_cores=n_cores,
        value_trace=value_trace or {},
    )
    machine.enable_pause = pause
    machine.enable_debug = debug
    return machine


class TestAvailability(unittest.TestCase):
    def test_dll_present(self):
        self.assertTrue(cpp_available(), 'vliw_machine.dll is missing; run build.bat')


class TestKernelCache(unittest.TestCase):
    def test_helper_change_busts_cache(self):
        from perf_takehome import KernelBuilder, _KERNEL_CACHE, get_kernel

        print('  get_kernel cache key covers helpers', flush=True)
        kb1 = get_kernel(3, 15, 8, 2, emit_debug=False)
        orig = KernelBuilder._emit_rounds_nodebug

        def wrapped(*args, **kwargs):
            return orig(*args, **kwargs)

        KernelBuilder._emit_rounds_nodebug = wrapped
        try:
            kb2 = get_kernel(3, 15, 8, 2, emit_debug=False)
            self.assertIsNot(kb1, kb2)
        finally:
            KernelBuilder._emit_rounds_nodebug = orig
            _KERNEL_CACHE.clear()
        kb3 = get_kernel(3, 15, 8, 2, emit_debug=False)
        kb4 = get_kernel(3, 15, 8, 2, emit_debug=False)
        self.assertIs(kb3, kb4)


class TestEncodeSlot(unittest.TestCase):
    def test_alu_and_const(self):
        keys: list = []
        self.assertEqual(encode_slot('alu', ('+', 2, 0, 1), keys), (0, 0, 2, 0, 1, 0))
        self.assertEqual(encode_slot('load', ('const', 3, 40), keys), (2, 3, 3, 40, 0, 0))
        self.assertEqual(keys, [])

    def test_debug_keys_appended_in_order(self):
        keys: list = []
        encode_slot('debug', ('compare', 4, ('a', 1)), keys)
        encode_slot('debug', ('vcompare', 8, ['k0', 'k1', 'k2', 'k3', 'k4', 'k5', 'k6', 'k7']), keys)
        self.assertEqual(keys[0], ('a', 1))
        self.assertEqual(len(keys), 9)


class TestMyhash(unittest.TestCase):
    def test_unrolled_matches_hash_stages(self):
        fns = {
            '+': lambda x, y: x + y,
            '^': lambda x, y: x ^ y,
            '<<': lambda x, y: x << y,
            '>>': lambda x, y: x >> y,
        }

        def slow(a: int) -> int:
            a %= 2**32
            for op1, val1, op2, op3, val3 in HASH_STAGES:
                a = (
                    fns[op2]((fns[op1](a, val1) % 2**32), (fns[op3](a, val3) % 2**32))
                    % 2**32
                )
            return a

        for a in (0, 1, 2, 7, 0x7ED55D16, 0xFFFFFFFF, 123456789, 2**30 - 1):
            self.assertEqual(myhash(a), slow(a), a)


class TestProfile(unittest.TestCase):
    def test_dep_chain_metrics(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'load': [('const', 1, 2)]},
            {'alu': [('+', 2, 0, 1)]},
            {'load': [('const', 3, 0)]},
            {'store': [('store', 3, 2)]},
        ]
        prof = profile_program(program)
        self.assertEqual(prof['cycles_est'], 5)
        self.assertEqual(prof['critical_path'], 3)
        self.assertEqual(prof['cp_raw'], 3)
        self.assertEqual(prof['cp_waw'], 3)
        self.assertEqual(prof['idle_cause'], 'deps')
        self.assertGreater(prof['schedule_waste'], 0.2)
        self.assertIn('top_slack', prof)
        self.assertIn('ready_not_issued', prof)
        self.assertEqual(prof['floor'], 2)
        self.assertEqual(prof['floor_engine'], 'load')
        self.assertEqual(prof['overhead'], 3)
        self.assertIn('hypotheses', prof)
        self.assertIn('select_vs_gather', prof)
        self.assertEqual(len(prof['select_vs_gather']['levels']), 6)
        again = profile_program(program, prev_json=json.dumps(prof))
        self.assertTrue(again['diff']['same_program'])
        self.assertEqual(again['diff']['cycles_est'], 0)
        self.assertIn('bottleneck_moved', again['diff'])

    def test_kernel_phases_and_names(self):
        from perf_takehome import get_kernel

        kb = get_kernel(3, 15, 4, 2, emit_debug=False)
        prof = profile_program(
            kb.instrs,
            phases=kb.phases,
            scratch_debug=kb.scratch_debug,
        )
        self.assertGreater(prof['phase_hash'], 0)
        self.assertGreater(prof['phase_ldst'], 0)
        self.assertGreater(prof['phase_walk'], 0)
        self.assertGreater(prof['phase_store'], 0)
        self.assertGreater(prof['phase_gather'], 0)
        self.assertIn('gather', prof['phases'])
        self.assertEqual(sum(prof['phases'].values()), prof['cycles_est'])
        names = {row['name'] for row in prof['named_live']}
        self.assertIn('tmp_val', names)
        self.assertTrue(any(row.get('loop_carried') for row in prof['named_live']))
        self.assertGreater(prof['gather_scalar'], 0)
        self.assertEqual(prof['mix_imbalance'], 'scalar_alu')
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertTrue({'pipeline', 'oneslot', 'valu_unused'} & tags)
        gathers = sum(
            int(row.get('gathers') or 0)
            for row in (prof.get('gathers_by_depth') or {}).values()
            if isinstance(row, dict)
        )
        self.assertEqual(gathers, 4 * 2)
        self.assertEqual(prof['bounds']['height'], 3)
        self.assertEqual(prof['bounds']['gather_floor_all_scalar'], 4)
        self.assertTrue(prof['integrity']['hash_ops_present'])
        self.assertTrue(prof['integrity']['index_stores'])
        self.assertFalse(prof['integrity']['suspect_cheat'])
        self.assertIn('regions', prof)
        self.assertEqual(
            int(prof['regions']['startup']['cycles'])
            + int(prof['regions']['steady']['cycles'])
            + int(prof['regions']['drain']['cycles']),
            prof['cycles_est'],
        )
        self.assertEqual(prof['occupancy_hist']['alu']['limit'], 12)
        self.assertEqual(prof['occupancy_hist']['valu']['limit'], 6)
        self.assertEqual(prof['occupancy_hist']['load']['limit'], 2)
        self.assertEqual(len(_occ_hist(prof, 'alu')), 13)
        self.assertEqual(len(_occ_hist(prof, 'valu')), 7)
        self.assertEqual(len(_occ_hist(prof, 'load')), 3)
        self.assertEqual(sum(_occ_hist(prof, 'load')), prof['cycles_est'])
        self.assertEqual(prof['occupancy_series']['n'], 0)
        self.assertIn('peak', prof['pressure'])
        self.assertIn('ii_est', prof['pipeline'])
        self.assertIn('wavefront', prof['pipeline'])
        self.assertIn('load_to_use_p50', prof['pipeline'])
        self.assertIn('load_to_use_hist', prof['pipeline'])
        self.assertIn('war_same_cycle', prof)
        self.assertGreaterEqual(prof['zero_load_cycles'], 0)

    def test_official_bounds_and_gathers(self):
        from perf_takehome import get_kernel

        kb = get_kernel(10, 2047, 256, 16, emit_debug=False)
        prof = profile_program(
            kb.instrs,
            phases=kb.phases,
            scratch_debug=kb.scratch_debug,
            forest_height=10,
            rounds=16,
            batch_size=256,
        )
        self.assertEqual(prof['bounds']['gather_floor_all_scalar'], 2048)
        self.assertEqual(prof['bounds']['useful_op_floor'], 1093)
        self.assertEqual(prof['bounds']['fused_hash_floor'], 1024)
        self.assertEqual(prof['bounds']['tiles'], 32)
        self.assertEqual(prof['phase_gather'], 256 * 16)
        gathers = sum(
            int(row.get('gathers') or 0)
            for row in (prof.get('gathers_by_depth') or {}).values()
            if isinstance(row, dict)
        )
        self.assertEqual(gathers, 256 * 16)
        self.assertEqual(sum(prof['phases'].values()), prof['cycles_est'])
        self.assertTrue(prof['integrity']['hash_ops_present'])
        self.assertFalse(prof['integrity']['suspect_cheat'])
        self.assertGreater(prof['scratch_vectors']['capacity_vecs'], 0)
        self.assertEqual(prof['cycles_est'], 147734)
        self.assertEqual(
            int(prof['regions']['startup']['cycles'])
            + int(prof['regions']['steady']['cycles'])
            + int(prof['regions']['drain']['cycles']),
            prof['cycles_est'],
        )
        self.assertEqual(prof['occupancy_series']['n'], 0)
        self.assertEqual(sum(_occ_hist(prof, 'load')), prof['cycles_est'])
        self.assertEqual(prof['occupancy_hist']['valu']['mean_used'], 0)
        self.assertIn('ii_est', prof['pipeline'])
        self.assertIn('wavefront', prof['pipeline'])
        self.assertIn('load_to_use_hist', prof['pipeline'])
        self.assertIn('live_overlaps', prof)

    def test_nodebug_stamp_matches_full_encode(self):
        from perf_takehome import KernelBuilder
        from vliw_native import encode_kernel_rows

        kb = KernelBuilder()
        kb.build_kernel(3, 15, 4, 2, emit_debug=False)
        stamped = kb.ensure_encoded(True)
        full = encode_kernel_rows(kb._eng, kb._slots, True, n=kb._n)
        self.assertEqual(bytes(stamped.buf), bytes(full.buf))

    def test_query_trace_occupancy(self):
        import importlib.util
        import tempfile

        spec = importlib.util.spec_from_file_location(
            'query_trace', ROOT / 'scripts' / 'query_trace.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        raw = (
            '[\n'
            '{"name": "thread_name", "ph": "M", "pid": 0, "tid": 1, '
            '"args": {"name": "alu-0"}},\n'
            '{"name": "thread_name", "ph": "M", "pid": 0, "tid": 2, '
            '"args": {"name": "load-0"}},\n'
            '{"name": "+", "cat": "op", "ph": "X", "pid": 0, "tid": 1, '
            '"ts": 1, "dur": 1},\n'
            '{"name": "load", "cat": "op", "ph": "X", "pid": 0, "tid": 2, '
            '"ts": 2, "dur": 1},\n'
            ']\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.json'
            path.write_text(raw, encoding='utf-8')
            row = mod.summarize_trace(path)
        self.assertEqual(row['cycles'], 2)
        self.assertEqual(row['engines']['alu']['ops'], 1)
        self.assertEqual(row['engines']['load']['ops'], 1)
        self.assertAlmostEqual(row['engines']['alu']['occupancy'], 1 / (2 * 12))


class TestProfileFloorMix(unittest.TestCase):
    def test_floor_overhead_and_load_engine(self):
        program = [{'load': [('const', i, 1)]} for i in range(32)]
        prof = profile_program(program)
        self.assertEqual(prof['cycles_est'], 32)
        self.assertEqual(prof['floor'], 16)
        self.assertEqual(prof['floor_engine'], 'load')
        self.assertEqual(prof['overhead'], 16)
        self.assertAlmostEqual(prof['overhead_frac'], 0.5, places=4)
        self.assertEqual(prof['mix_imbalance'], 'load_heavy')
        self.assertEqual(prof['mix']['valu_hungry'], 32)
        self.assertEqual(prof['mix']['empty'], 0)
        self.assertEqual(prof['mix']['target']['valu'], 6)
        self.assertEqual(prof['mix']['target']['load'], 2)
        self.assertEqual(prof['mix']['target']['flow'], 1)

    def test_packed_load_saturates_floor(self):
        program = [{'load': [('const', 0, 1), ('const', 1, 2)]}]
        prof = profile_program(program)
        self.assertEqual(prof['cycles_est'], 1)
        self.assertEqual(prof['slots'], 2)
        self.assertEqual(prof['floor'], 1)
        self.assertEqual(prof['floor_engine'], 'load')
        self.assertEqual(prof['overhead'], 0)
        self.assertEqual(prof['saturation_cycles'], 1)
        self.assertEqual(prof['port_full']['load'], 1)
        self.assertEqual(prof['occupancy_hist']['load']['limit'], 2)
        self.assertEqual(_occ_hist(prof, 'load'), [0, 0, 1])
        self.assertAlmostEqual(prof['occupancy_hist']['load']['mean_used'], 2.0)
        self.assertEqual(prof['zero_load_cycles'], 0)
        self.assertEqual(prof['load0_valu_lt6'], 0)

    def test_valu_bundle_is_valu_floor(self):
        slots = [('+', i * 8, 0, 0) for i in range(6)]
        program = [{'valu': slots}]
        prof = profile_program(program)
        self.assertEqual(prof['valu_ops'], 6)
        self.assertEqual(prof['floor_engine'], 'valu')
        self.assertEqual(prof['floor'], 1)
        self.assertEqual(prof['saturation_cycles'], 1)
        self.assertEqual(prof['port_full']['valu'], 1)
        self.assertEqual(prof['occupancy_hist']['valu']['limit'], 6)
        self.assertEqual(_occ_hist(prof, 'valu')[6], 1)
        self.assertAlmostEqual(prof['occupancy_hist']['valu']['mean_used'], 6.0)
        self.assertGreater(prof['occupancy_series']['n'], 0)
        self.assertEqual(prof['zero_load_cycles'], 1)
        self.assertEqual(prof['load0_valu_lt6'], 0)

    def test_valu_heavy_oneslot(self):
        program = [{'valu': [('+', i * 8, 0, 0)]} for i in range(18)]
        prof = profile_program(program)
        self.assertEqual(prof['floor'], 3)
        self.assertEqual(prof['floor_engine'], 'valu')
        self.assertEqual(prof['mix_imbalance'], 'valu_heavy')
        self.assertEqual(prof['occupancy_series']['n'], 0)
        self.assertEqual(prof['occupancy_hist']['valu']['limit'], 6)

    def test_flow_selects_are_flow_floor(self):
        program = [{'flow': [('select', 0, 0, 0, 0)]} for _ in range(12)]
        prof = profile_program(program)
        self.assertEqual(prof['floor_engine'], 'flow')
        self.assertEqual(prof['floor'], 12)
        self.assertEqual(prof['overhead'], 0)
        self.assertEqual(prof['select_ops'], 12)
        self.assertEqual(prof['mix_imbalance'], 'flow_heavy')
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertIn('control_bounds', tags)


class TestProfileScheduleMetrics(unittest.TestCase):
    def test_regions_ii_and_war(self):
        program = [{'load': [('const', i, 1)]} for i in range(6)]
        phases = [1, 1, 3, 3, 3, 1]
        prof = profile_program(program, phases=phases, rounds=3, batch_size=2)
        self.assertEqual(prof['regions']['startup_end'], 2)
        self.assertEqual(prof['regions']['drain_start'], 5)
        self.assertEqual(prof['regions']['startup']['cycles'], 2)
        self.assertEqual(prof['regions']['steady']['cycles'], 3)
        self.assertEqual(prof['regions']['drain']['cycles'], 1)
        self.assertAlmostEqual(prof['pipeline']['ii_est'], 0.5, places=4)
        self.assertEqual(prof['pipeline']['wavefront']['hash'], 3)
        self.assertEqual(prof['pipeline']['item_rounds'], 6)

        war = [{'alu': [('+', 2, 0, 1)], 'load': [('const', 0, 9)]}]
        wprof = profile_program(war)
        self.assertEqual(wprof['war_same_cycle'], 1)

        lu = [
            {'load': [('const', 0, 10)]},
            {'load': [('load', 1, 0)]},
            {'alu': [('+', 2, 1, 1)]},
        ]
        lprof = profile_program(lu)
        self.assertEqual(lprof['pipeline']['load_to_use_n'], 1)
        self.assertEqual(lprof['pipeline']['load_to_use_p50'], 1)
        self.assertEqual(lprof['pipeline']['load_to_use_hist']['1'], 1)

    def test_named_overlaps_and_series_cap(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'load': [('const', 1, 2)]},
            {'alu': [('+', 2, 0, 1)]},
        ]
        scratch = {
            0: ('tmp_a', 1),
            1: ('tmp_b', 1),
            2: ('tmp_c', 1),
        }
        prof = profile_program(program, scratch_debug=scratch)
        self.assertEqual(prof['war_named_overlaps'], 3)
        self.assertGreaterEqual(len(prof['live_overlaps']), 1)
        names = {(row['a'], row['b']) for row in prof['live_overlaps']}
        self.assertTrue(names)

        longp = [{'load': [('const', i % 64, 1)]} for i in range(300)]
        sprof = profile_program(longp)
        self.assertEqual(sprof['occupancy_series']['n'], 0)
        self.assertEqual(sprof['pressure']['series'], [])
        self.assertEqual(sprof['occupancy_hist']['load']['limit'], 2)


class TestProfileGatherSelect(unittest.TestCase):
    def test_op_class_counts(self):
        program = [
            {'load': [('const', 0, 10)]},
            {'load': [('load', 1, 0)]},
            {'load': [('load', 2, 0)]},
            {'load': [('vload', 8, 0)]},
            {'flow': [('vselect', 16, 1, 8, 8)]},
            {'flow': [('select', 3, 1, 2, 1)]},
            {'valu': [('multiply_add', 24, 8, 8, 8)]},
        ]
        prof = profile_program(program)
        self.assertEqual(prof['gather_scalar'], 2)
        self.assertEqual(prof['vload_ops'], 1)
        self.assertEqual(prof['vselect_ops'], 1)
        self.assertEqual(prof['select_ops'], 1)
        self.assertEqual(prof['madd_ops'], 1)
        self.assertEqual(prof['const_ops'], 1)
        levels = prof['select_vs_gather']['levels']
        self.assertEqual(len(levels), 6)
        self.assertEqual(levels[0]['prefer'], 'select')
        self.assertEqual(levels[3]['prefer'], 'select')
        self.assertEqual(levels[4]['prefer'], 'mixed')
        self.assertEqual(levels[5]['prefer'], 'gather')

    def test_gather_hypothesis(self):
        program = [{'load': [('const', 0, 1)]}] + [
            {'load': [('load', i + 1, 0)]} for i in range(10)
        ]
        prof = profile_program(program)
        self.assertEqual(prof['gather_scalar'], 10)
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertIn('gather', tags)
        self.assertIn('memory_layout', tags)
        self.assertTrue(all('tag' in h and 'why' in h for h in prof['hypotheses']))

    def test_waw_store_lifetime_tag(self):
        program = [{'load': [('const', 0, i + 1)]} for i in range(20)]
        prof = profile_program(program)
        self.assertEqual(prof['cp_raw'], 1)
        self.assertEqual(prof['cp_waw'], 20)
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertIn('store_lifetime', tags)

    def test_diff_floor_and_gather(self):
        loads = [{'load': [('load', i, 0)]} for i in range(8)]
        valu = [{'valu': [('+', i * 8, 0, 0)]} for i in range(12)]
        prev = profile_program(loads)
        cur = profile_program(valu, prev_json=json.dumps(prev))
        self.assertEqual(prev['floor_engine'], 'load')
        self.assertEqual(cur['floor_engine'], 'valu')
        self.assertTrue(cur['diff']['floor_engine_changed'])
        self.assertEqual(cur['diff']['gather_scalar'], -8)
        self.assertFalse(cur['diff']['same_program'])

    def test_top_slack_omits_pause(self):
        program = [
            {'flow': [('pause',)]},
            {'load': [('const', 0, 1)]},
            {'load': [('const', 1, 2)]},
            {'alu': [('+', 2, 0, 1)]},
        ]
        prof = profile_program(program)
        ops = [row['op'] for row in prof['top_slack']]
        self.assertNotIn('flow.pause', ops)


class TestEncodeProgram(unittest.TestCase):
    def test_oneslot_and_skip_debug(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'debug': [('comment',)]},
            {'flow': [('halt',)]},
        ]
        full = encode_program(program)
        slim = encode_program(program, skip_debug=True)
        self.assertTrue(full.oneslot)
        self.assertTrue(slim.oneslot)
        self.assertEqual(full.n_slots, 3)
        self.assertEqual(slim.n_slots, 2)
        self.assertEqual(full.keys, [])

    def test_omit_debug_matches_debug_off_cycles(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'debug': [('comment',)]},
            {'load': [('const', 1, 2)]},
            {'flow': [('halt',)]},
        ]
        keep = _make(FastMachine, [0] * 8, program, pause=False, debug=False)
        omit = FastMachine([0] * 8, program, _info(), omit_debug=True)
        omit.enable_pause = False
        omit.enable_debug = False
        keep.run()
        omit.run()
        self.assertEqual(keep.cycle, omit.cycle)
        self.assertEqual(keep.cycle, 3)


class TestFastVsPython(unittest.TestCase):
    def _agree(self, mem, program, *, pause=True, debug=True, value_trace=None, scratch_n=16):
        py = _make(PythonMachine, mem, program, pause=pause, debug=debug, value_trace=value_trace)
        cpp = _make(FastMachine, mem, program, pause=pause, debug=debug, value_trace=value_trace)
        py.run()
        cpp.run()
        self.assertEqual(py.cycle, cpp.cycle)
        self.assertEqual(list(py.mem), cpp.mem[:])
        self.assertEqual(py.cores[0].scratch[:scratch_n], cpp.cores[0].scratch[:scratch_n])
        self.assertEqual(py.cores[0].trace_buf, cpp.cores[0].trace_buf)
        self.assertEqual(int(py.cores[0].state.value), int(cpp.cores[0].state.value))
        return py, cpp

    def test_const_add_store(self):
        program = [
            {'load': [('const', 0, 40)]},
            {'load': [('const', 1, 2)]},
            {'alu': [('+', 2, 0, 1)]},
            {'load': [('const', 3, 0)]},
            {'store': [('store', 3, 2)]},
        ]
        self._agree([0] * 8, program)
        py, cpp = self._agree([0] * 8, program, pause=False, debug=False)
        self.assertEqual(cpp.mem[0], 42)

    def test_alu_wrap_and_logic(self):
        program = [
            {'load': [('const', 0, 0xFFFFFFFF)]},
            {'load': [('const', 1, 2)]},
            {'alu': [('+', 2, 0, 1)]},
            {'alu': [('-', 3, 1, 0)]},
            {'alu': [('&', 4, 0, 1)]},
            {'alu': [('|', 5, 0, 1)]},
            {'alu': [('^', 6, 0, 1)]},
            {'alu': [('<<', 7, 1, 1)]},
            {'alu': [('>>', 8, 0, 1)]},
        ]
        self._agree([0] * 8, program, scratch_n=9)

    def test_deferred_write(self):
        program = [
            {'load': [('const', 0, 5)]},
            {'load': [('const', 1, 7)]},
            {'alu': [('+', 0, 0, 1), ('+', 2, 0, 0)]},
        ]
        py, cpp = self._agree([0] * 8, program)
        self.assertEqual(cpp.cores[0].scratch[0], 12)
        self.assertEqual(cpp.cores[0].scratch[2], 10)

    def test_pause_resume(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'flow': [('pause',)]},
            {'load': [('const', 1, 2)]},
        ]
        py = _make(PythonMachine, [0] * 8, program)
        cpp = _make(FastMachine, [0] * 8, program)
        py.run()
        cpp.run()
        self.assertEqual(py.cores[0].state, CoreState.PAUSED)
        self.assertEqual(cpp.cores[0].state, CoreState.PAUSED)
        self.assertEqual(py.cycle, cpp.cycle)
        self.assertEqual(cpp.cores[0].scratch[1], 0)
        py.run()
        cpp.run()
        self.assertEqual(cpp.cores[0].scratch[1], 2)
        self.assertEqual(py.cycle, cpp.cycle)

    def test_pause_disabled(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'flow': [('pause',)]},
            {'load': [('const', 1, 2)]},
        ]
        py, cpp = self._agree([0] * 8, program, pause=False, debug=False)
        self.assertEqual(cpp.cores[0].scratch[1], 2)

    def test_select_and_add_imm(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'load': [('const', 1, 9)]},
            {'load': [('const', 2, 8)]},
            {'flow': [('select', 3, 0, 1, 2)]},
            {'flow': [('add_imm', 4, 0, 0xFFFFFFFF)]},
        ]
        py, cpp = self._agree([0] * 8, program)
        self.assertEqual(cpp.cores[0].scratch[3], 9)
        self.assertEqual(cpp.cores[0].scratch[4], 0)

    def test_vload_vstore(self):
        mem = [0] * 32
        for i in range(8):
            mem[10 + i] = 100 + i
        program = [
            {'load': [('const', 0, 10)]},
            {'load': [('vload', 8, 0)]},
            {'load': [('const', 1, 20)]},
            {'store': [('vstore', 1, 8)]},
        ]
        self._agree(mem, program, scratch_n=16)
        _, cpp = self._agree(mem, program, pause=False, debug=False, scratch_n=16)
        self.assertEqual(list(cpp.mem[20:28]), list(range(100, 108)))

    def test_valu_broadcast(self):
        program = [
            {'load': [('const', 0, 3)]},
            {'valu': [('vbroadcast', 8, 0)]},
        ]
        py, cpp = self._agree([0] * 8, program, scratch_n=16)
        self.assertEqual(cpp.cores[0].scratch[8:16], [3] * 8)

    def test_jump(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'flow': [('jump', 4)]},
            {'load': [('const', 1, 99)]},
            {'flow': [('halt',)]},
            {'load': [('const', 1, 7)]},
            {'flow': [('halt',)]},
        ]
        py, cpp = self._agree([0] * 8, program)
        self.assertEqual(cpp.cores[0].scratch[1], 7)

    def test_cond_jump_rel(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'flow': [('cond_jump_rel', 0, 2)]},
            {'load': [('const', 1, 99)]},
            {'flow': [('halt',)]},
            {'load': [('const', 1, 7)]},
            {'flow': [('halt',)]},
        ]
        py, cpp = self._agree([0] * 8, program)
        self.assertEqual(cpp.cores[0].scratch[1], 7)

    def test_debug_compare(self):
        program = [
            {'load': [('const', 0, 7)]},
            {'debug': [('compare', 0, 'k')]},
        ]
        self._agree([0] * 8, program, value_trace={'k': 7})

    def test_debug_disabled_ignores_mismatch(self):
        program = [
            {'load': [('const', 0, 7)]},
            {'debug': [('compare', 0, 'k')]},
        ]
        self._agree([0] * 8, program, debug=False, value_trace={'k': 99})

    def test_debug_only_bundle_no_cycle(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'debug': [('comment',)]},
        ]
        py, cpp = self._agree([0] * 8, program)
        self.assertEqual(cpp.cycle, 1)

    def test_coreid(self):
        program = [{'flow': [('coreid', 0)]}, {'flow': [('halt',)]}]
        self._agree([0] * 8, program)

    def _both_raise(self, mem, program, py_exc):
        py = _make(PythonMachine, mem, program)
        cpp = _make(FastMachine, mem, program)
        with self.assertRaises(py_exc):
            py.run()
        with self.assertRaises(RuntimeError):
            cpp.run()

    def test_oob_load_raises(self):
        program = [
            {'load': [('const', 0, 99)]},
            {'load': [('load', 1, 0)]},
            {'flow': [('halt',)]},
        ]
        self._both_raise([0] * 8, program, IndexError)

    def test_oob_store_raises(self):
        program = [
            {'load': [('const', 0, 99)]},
            {'load': [('const', 1, 1)]},
            {'store': [('store', 0, 1)]},
            {'flow': [('halt',)]},
        ]
        self._both_raise([0] * 8, program, IndexError)

    def test_oob_vector_scratch_write_raises(self):
        program = [
            {'load': [('const', 0, 1)]},
            {'valu': [('+', 1530, 0, 0)]},
            {'flow': [('halt',)]},
        ]
        self._both_raise([0] * 8, program, IndexError)

    def test_div_mod_cdiv_by_zero_raise(self):
        for op in ('//', '%', 'cdiv'):
            program = [
                {'load': [('const', 0, 10)]},
                {'load': [('const', 1, 0)]},
                {'alu': [(op, 2, 0, 1)]},
                {'flow': [('halt',)]},
            ]
            self._both_raise([0] * 8, program, ZeroDivisionError)

    def test_trace_write_reaches_python(self):
        program = [
            {'load': [('const', 0, 42)]},
            {'flow': [('trace_write', 0)]},
            {'flow': [('trace_write', 0)]},
            {'flow': [('halt',)]},
        ]
        py, cpp = self._agree([0] * 8, program)
        self.assertEqual(py.cores[0].trace_buf, [42, 42])
        self.assertEqual(cpp.cores[0].trace_buf, [42, 42])
        py2, cpp2 = self._agree([0] * 8, program, pause=False, debug=False)
        self.assertEqual(py2.cores[0].trace_buf, [42, 42])
        self.assertEqual(cpp2.cores[0].trace_buf, [42, 42])

    def test_mem_view_roundtrip(self):
        program = [{'flow': [('halt',)]}]
        cpp = _make(FastMachine, [1, 2, 3, 4, 5, 6, 7, 8], program)
        self.assertEqual(len(cpp.mem), 8)
        self.assertEqual(cpp.mem[0], 1)
        cpp.mem[0] = 99
        self.assertEqual(cpp.mem[0], 99)
        self.assertEqual(cpp.mem[1:3], [2, 3])
        self.assertEqual(list(cpp.mem), [99, 2, 3, 4, 5, 6, 7, 8])
        with self.assertRaises(IndexError):
            _ = cpp.mem[99]


class TestLinearPath(unittest.TestCase):
    def test_full_run_matches_python(self):
        program = [
            {'load': [('const', 0, 10)]},
            {'load': [('const', 1, 3)]},
            {'alu': [('%', 2, 0, 1)]},
            {'alu': [('==', 3, 2, 1)]},
            {'flow': [('select', 4, 3, 0, 1)]},
            {'debug': [('comment',)]},
            {'flow': [('pause',)]},
            {'load': [('const', 5, 0)]},
            {'store': [('store', 5, 4)]},
            {'flow': [('halt',)]},
        ]
        py = _make(PythonMachine, [0] * 8, program, pause=False, debug=False)
        cpp = _make(FastMachine, [0] * 8, program, pause=False, debug=False)
        py.run()
        cpp.run()
        self.assertEqual(py.cycle, cpp.cycle)
        self.assertEqual(list(py.mem), cpp.mem[:])
        self.assertEqual(cpp.mem[0], 3)


def main() -> int:
    print('engine python tests', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
