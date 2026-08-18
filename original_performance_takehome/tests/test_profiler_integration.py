"""Integration tests: real kernels through encode → C++ profiler → run → check.py."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perf_takehome import BASELINE, get_kernel, quick_kernel_check
from problem import Input, N_CORES, Tree, build_mem_image
from vliw_native import (
    FastMachine,
    VliwProfileExtra,
    _err,
    _lib,
    encode_program,
    profile_program,
)

LAST_PROF = ROOT / '_last_profile.json'
HISTORY = ROOT / '_check_history.jsonl'
ABLATION = ROOT / '_ablation.jsonl'

SCHEMA = (
    'fingerprint',
    'assumes_linear',
    'has_jumps',
    'bundles',
    'debug_bundles',
    'slots',
    'cycles_est',
    'ipc',
    'work_bound',
    'floor',
    'floor_engine',
    'overhead',
    'overhead_frac',
    'saturation_cycles',
    'critical_path',
    'cp_raw',
    'cp_waw',
    'cp_mem',
    'alu_ops',
    'valu_ops',
    'load_ops',
    'store_ops',
    'flow_ops',
    'dep_pressure',
    'resource_pressure',
    'schedule_waste',
    'idle_cause',
    'bottleneck',
    'slack_mean',
    'slack_p50',
    'slack_max',
    'ready_not_issued_mean',
    'peak_live',
    'scratch_capacity',
    'cells_touched',
    'zero_load_cycles',
    'load0_valu_lt6',
    'war_same_cycle',
    'war_named_overlaps',
    'engines',
    'phases',
    'ready_not_issued',
    'limit_engine',
    'port_full',
    'mix',
    'bounds',
    'gathers_by_depth',
    'alu_class',
    'scratch_vectors',
    'pipeline',
    'regions',
    'occupancy_hist',
    'occupancy_series',
    'pressure',
    'live_overlaps',
    'integrity',
    'select_vs_gather',
    'hypotheses',
    'top_ops',
    'top_slack',
    'named_live',
    'hints',
)

OCC_LIMIT = {'alu': 12, 'valu': 6, 'load': 2, 'store': 2, 'flow': 1}
OCC_HIST_LEN = {'alu': 13, 'valu': 7, 'load': 3, 'store': 3, 'flow': 2}
PHASES = ('unknown', 'init', 'ldst', 'hash', 'walk', 'store', 'gather')
LOAD_USE_KEYS = ('1', '2', '3', '4_7', '8_15', '16_31', '32p')
@lru_cache(maxsize=None)
def _kernel(height: int, rounds: int, batch: int):
    n_nodes = 2 ** (height + 1) - 1
    return get_kernel(height, n_nodes, batch, rounds, emit_debug=False)


@lru_cache(maxsize=None)
def _profile(height: int, rounds: int, batch: int) -> dict:
    kb = _kernel(height, rounds, batch)
    return profile_program(
        kb.instrs,
        omit_debug=True,
        phases=kb.phases,
        scratch_debug=kb.scratch_debug,
        forest_height=height,
        rounds=rounds,
        batch_size=batch,
    )


def _hist(prof: dict, name: str) -> list[int]:
    return list(((prof.get('occupancy_hist') or {}).get(name) or {}).get('hist') or [])


def _assert_schema(tc: unittest.TestCase, prof: dict) -> None:
    missing = [k for k in SCHEMA if k not in prof]
    tc.assertEqual(missing, [])
    tc.assertEqual(set(prof['engines']), set(OCC_LIMIT))
    tc.assertEqual(tuple(prof['phases']), PHASES)
    tc.assertEqual(set(prof['occupancy_hist']), set(OCC_LIMIT))
    tc.assertEqual(set(prof['pipeline']['wavefront']), set(PHASES))
    tc.assertEqual(set(prof['pipeline']['load_to_use_hist']), set(LOAD_USE_KEYS))
    tc.assertEqual(len(prof['select_vs_gather']['levels']), 6)
    tc.assertEqual(prof['mix']['target'], {'valu': 6, 'load': 2, 'store': 2, 'flow': 1})
    for name, limit in OCC_LIMIT.items():
        row = prof['occupancy_hist'][name]
        tc.assertEqual(row['limit'], limit)
        tc.assertEqual(len(row['hist']), OCC_HIST_LEN[name])
        tc.assertEqual(sum(row['hist']), prof['cycles_est'])
    for part in ('startup', 'steady', 'drain'):
        row = prof['regions'][part]
        for key in (
            'cycles',
            'zero_load',
            'load0_valu_lt6',
            'valu_unused_slots',
            'load_unused_slots',
            'store_unused_slots',
            'alu_unused_slots',
            'flow_unused_slots',
        ):
            tc.assertIn(key, row)


def _assert_oneslot_kernel(tc: unittest.TestCase, prof: dict, height: int, rounds: int, batch: int) -> None:
    cycles = int(prof['cycles_est'])
    tc.assertGreater(cycles, 0)
    tc.assertAlmostEqual(prof['ipc'], 1.0)
    tc.assertEqual(prof['bundles'], cycles)
    tc.assertEqual(prof['slots'], cycles)
    tc.assertEqual(prof['debug_bundles'], 0)
    tc.assertTrue(prof['assumes_linear'])
    tc.assertFalse(prof['has_jumps'])
    tc.assertEqual(prof['valu_ops'], 0)
    tc.assertEqual(sum(prof['phases'].values()), cycles)
    tc.assertEqual(prof['floor'], prof['work_bound'])
    tc.assertEqual(prof['overhead'], cycles - prof['floor'])
    tc.assertAlmostEqual(prof['overhead_frac'], prof['overhead'] / cycles, places=4)
    tc.assertEqual(prof['zero_load_cycles'], cycles - prof['load_ops'])
    tc.assertEqual(prof['load0_valu_lt6'], prof['zero_load_cycles'])
    ops = {
        'alu': prof['alu_ops'],
        'valu': prof['valu_ops'],
        'load': prof['load_ops'],
        'store': prof['store_ops'],
        'flow': prof['flow_ops'],
    }
    for name, n_ops in ops.items():
        hist = _hist(prof, name)
        tc.assertEqual(hist[0], cycles - n_ops)
        tc.assertEqual(hist[1], n_ops)
        tc.assertTrue(all(v == 0 for v in hist[2:]))
        tc.assertAlmostEqual(
            prof['occupancy_hist'][name]['mean_used'],
            n_ops / cycles,
            places=4,
        )
        eng = prof['engines'][name]
        tc.assertEqual(eng['ops'], n_ops)
        tc.assertEqual(eng['limit'], OCC_LIMIT[name])
        tc.assertAlmostEqual(eng['occupancy'], n_ops / (cycles * OCC_LIMIT[name]), places=4)
    regs = prof['regions']
    tc.assertEqual(
        regs['startup']['cycles'] + regs['steady']['cycles'] + regs['drain']['cycles'],
        cycles,
    )
    tc.assertEqual(regs['startup']['cycles'] + regs['drain']['cycles'], prof['phase_init'])
    valu_unused = sum(int(regs[p]['valu_unused_slots']) for p in ('startup', 'steady', 'drain'))
    tc.assertEqual(valu_unused, cycles * 6)
    tc.assertEqual(prof['pipeline']['wavefront']['init'], 0)
    for name in PHASES:
        if name == 'init':
            continue
        tc.assertEqual(prof['pipeline']['wavefront'][name], prof['phases'][name])
    item_rounds = rounds * batch
    tc.assertEqual(prof['bounds']['item_rounds'], item_rounds)
    tc.assertEqual(prof['pipeline']['item_rounds'], item_rounds)
    tc.assertAlmostEqual(
        prof['pipeline']['ii_est'],
        regs['steady']['cycles'] / item_rounds,
        places=4,
    )
    tc.assertEqual(prof['occupancy_series']['n'], 0)
    tc.assertEqual(prof['pressure']['series'], [])
    tc.assertEqual(prof['pressure']['peak'], prof['peak_live'])
    tc.assertEqual(prof['scratch_vectors']['peak_live'], prof['peak_live'])
    tc.assertEqual(prof['scratch_vectors']['war_same_cycle'], prof['war_same_cycle'])
    tc.assertEqual(prof['war_same_cycle'], prof['alu_class']['idx'])
    tc.assertEqual(prof['bounds']['height'], height)
    tc.assertEqual(prof['bounds']['rounds'], rounds)
    tc.assertEqual(prof['bounds']['batch'], batch)
    tc.assertEqual(prof['bounds']['tiles'], batch // 8 if batch >= 8 else batch)
    tc.assertEqual(prof['bounds']['gather_floor_all_scalar'], (item_rounds + 1) // 2)
    tc.assertEqual(prof['bounds']['useful_op_floor'], (item_rounds * 16 + 59) // 60)
    tc.assertEqual(prof['bounds']['fused_hash_floor'], (prof['bounds']['tiles'] * rounds * 12 + 5) // 6)
    tc.assertEqual(prof['bounds']['peak_slots'], 23)
    gathers = sum(
        int(row.get('gathers') or 0)
        for row in prof['gathers_by_depth'].values()
        if isinstance(row, dict)
    )
    tc.assertEqual(gathers, prof['phase_gather'])
    tc.assertEqual(gathers, batch * rounds)
    tc.assertGreater(prof['pipeline']['load_to_use_n'], 0)
    tc.assertGreaterEqual(prof['pipeline']['load_to_use_p95'], prof['pipeline']['load_to_use_p50'])
    tc.assertTrue(prof['integrity']['hash_ops_present'])
    tc.assertTrue(prof['integrity']['index_stores'])
    tc.assertFalse(prof['integrity']['suspect_cheat'])
    tc.assertFalse(prof['integrity']['suspect_skip_hash'])
    tc.assertIn('tmp_val', {row['name'] for row in prof['named_live']})
    tc.assertTrue(any(row.get('loop_carried') for row in prof['named_live']))
    tc.assertGreaterEqual(len(prof['live_overlaps']), 1)
    tc.assertEqual(len(prof['fingerprint']), 16)
    tc.assertEqual(prof['mix_imbalance'], 'scalar_alu')
    tc.assertGreater(len(prof['hypotheses']), 0)
    tc.assertGreater(len(prof['hints']), 0)
    tc.assertGreater(len(prof['top_ops']), 0)
    tc.assertGreater(len(prof['top_slack']), 0)
    tc.assertIn(prof['idle_cause'], ('deps', 'ports', 'schedule'))
    tc.assertIn(prof['bottleneck'], ('deps', 'ports', 'schedule', 'mixed'))


class TestSmokeKernelMetrics(unittest.TestCase):
    def test_all_metrics_3_2_8(self):
        print('[1/9] smoke 3/2/8 all metric blocks', flush=True)
        prof = _profile(3, 2, 8)
        print(f'    cycles={prof["cycles_est"]} floor={prof["floor"]}', flush=True)
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 3, 2, 8)
        self.assertEqual(prof['cycles_est'], 610)
        self.assertEqual(prof['phase_gather'], 16)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['1'], 16)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['16_31'], 16)


class TestMidKernelMetrics(unittest.TestCase):
    def test_all_metrics_5_4_16(self):
        print('[2/9] mid 5/4/16 all metric blocks', flush=True)
        prof = _profile(5, 4, 16)
        print(f'    cycles={prof["cycles_est"]} floor={prof["floor"]}', flush=True)
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 5, 4, 16)
        self.assertEqual(prof['phase_gather'], 64)
        self.assertGreater(prof['cycles_est'], 610)
        self.assertLess(prof['cycles_est'], BASELINE)


class TestOfficialKernelMetrics(unittest.TestCase):
    def test_all_metrics_10_16_256(self):
        print('[3/9] official 10/16/256 all metric blocks', flush=True)
        prof = _profile(10, 16, 256)
        print(
            f'    cycles={prof["cycles_est"]} floor={prof["floor"]} '
            f'zero_load={prof["zero_load_cycles"]} ii={prof["pipeline"]["ii_est"]}',
            flush=True,
        )
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 10, 16, 256)
        self.assertEqual(prof['cycles_est'], BASELINE)
        self.assertEqual(prof['phase_gather'], 4096)
        self.assertEqual(prof['bounds']['gather_floor_all_scalar'], 2048)
        self.assertEqual(prof['bounds']['useful_op_floor'], 1093)
        self.assertEqual(prof['bounds']['fused_hash_floor'], 1024)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['1'], 4096)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['16_31'], 4096)
        self.assertAlmostEqual(prof['pipeline']['ii_est'], 36.0, places=4)
        self.assertEqual(prof['alu_class']['idx'], 20480)
        self.assertEqual(prof['war_same_cycle'], 20480)


class TestProfileMatchesRun(unittest.TestCase):
    def test_smoke_profile_equals_run_and_check(self):
        print('[4/9] 3/2/8 cycles_est == FastMachine.run == quick_kernel_check', flush=True)
        height, rounds, batch = 3, 2, 8
        prof = _profile(height, rounds, batch)
        forest = Tree.generate(height)
        inp = Input.generate(forest, batch, rounds)
        mem = build_mem_image(forest, inp)
        kb = _kernel(height, rounds, batch)
        machine = FastMachine(
            list(mem), kb.instrs, kb.debug_info(), n_cores=N_CORES, omit_debug=True
        )
        machine.enable_pause = False
        machine.enable_debug = False
        machine.run()
        checked = quick_kernel_check(height, rounds, batch)
        print(
            f'    est={prof["cycles_est"]} run={machine.cycle} check={checked}',
            flush=True,
        )
        self.assertEqual(prof['cycles_est'], machine.cycle)
        self.assertEqual(prof['cycles_est'], checked)

    def test_official_profile_equals_check(self):
        print('[5/9] 10/16/256 cycles_est == quick_kernel_check', flush=True)
        prof = _profile(10, 16, 256)
        checked = quick_kernel_check(10, 16, 256)
        self.assertEqual(prof['cycles_est'], checked)
        self.assertEqual(checked, BASELINE)


class TestCApiMatchesWrapper(unittest.TestCase):
    def test_profile_ex_matches_python_wrapper(self):
        print('[6/9] C API profile_ex == profile_program on 3/2/8', flush=True)
        kb = _kernel(3, 2, 8)
        wrapped = _profile(3, 2, 8)
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
            raw_ph = bytes(kb.billed_phases())
            ph_arr = (ctypes.c_uint8 * len(raw_ph)).from_buffer_copy(raw_ph)
            extra.phase = ph_arr
            extra.n_phase = len(raw_ph)
            extra.forest_height = 3
            extra.rounds = 2
            extra.batch_size = 8
            raw = lib.vliw_program_profile_ex(prog, None, ctypes.byref(extra))
            self.assertTrue(raw, _err())
            try:
                text = ctypes.cast(raw, ctypes.c_char_p).value
                native = json.loads(text.decode('utf-8'))
            finally:
                lib.vliw_profile_free(raw)
        finally:
            lib.vliw_program_destroy(prog)
        for key in (
            'cycles_est',
            'fingerprint',
            'zero_load_cycles',
            'load0_valu_lt6',
            'war_same_cycle',
            'peak_live',
            'alu_ops',
            'load_ops',
            'floor',
        ):
            self.assertEqual(native[key], wrapped[key], key)
        self.assertEqual(native['regions']['startup']['cycles'], wrapped['regions']['startup']['cycles'])
        self.assertEqual(native['pipeline']['ii_est'], wrapped['pipeline']['ii_est'])
        self.assertEqual(native['occupancy_hist']['load']['hist'], wrapped['occupancy_hist']['load']['hist'])


class TestDiffAcrossShapes(unittest.TestCase):
    def test_smoke_vs_official_diff(self):
        print('[7/9] diff 3/2/8 -> 10/16/256', flush=True)
        smoke = _profile(3, 2, 8)
        official = profile_program(
            _kernel(10, 16, 256).instrs,
            omit_debug=True,
            phases=_kernel(10, 16, 256).phases,
            scratch_debug=_kernel(10, 16, 256).scratch_debug,
            forest_height=10,
            rounds=16,
            batch_size=256,
            prev_json=json.dumps(smoke),
        )
        d = official['diff']
        self.assertFalse(d['same_program'])
        self.assertEqual(d['cycles_est'], BASELINE - smoke['cycles_est'])
        self.assertGreater(d['alu_ops'], 0)
        self.assertGreater(d['load_ops'], 0)


class TestCheckPyLoop(unittest.TestCase):
    def setUp(self):
        self._saved = {
            LAST_PROF: LAST_PROF.read_bytes() if LAST_PROF.is_file() else None,
            HISTORY: HISTORY.read_bytes() if HISTORY.is_file() else None,
            ABLATION: ABLATION.read_bytes() if ABLATION.is_file() else None,
        }

    def tearDown(self):
        for path, data in self._saved.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)

    def test_prof_only_smoke_writes_history(self):
        print('[8/9] check.py --prof-only --smoke --hypothesis itest', flush=True)
        proc = subprocess.run(
            [
                sys.executable,
                '-u',
                str(ROOT / 'check.py'),
                '--prof-only',
                '--smoke',
                '--hypothesis',
                'itest',
                '-m',
                'profiler_integration',
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        for needle in (
            'regions  ',
            'occ_hist  ',
            'history  keep=',
            'revert=',
            'peak_scratch=',
            'valu_ops=',
            'load_ops=',
            'correct=true',
        ):
            self.assertIn(needle, out, needle)
        self.assertNotIn('occ_series  ', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], prof['cycles_run'])
        _assert_schema(self, prof)
        hist_line = HISTORY.read_text(encoding='utf-8').strip().splitlines()[-1]
        row = json.loads(hist_line)
        self.assertIn('keep', row)
        self.assertIn('revert', row)
        self.assertEqual(row['revert'], (not row['keep']))
        self.assertEqual(row['peak_scratch'], prof['peak_live'])
        self.assertEqual(row['valu_ops'], 0)
        self.assertEqual(row['load_ops'], prof['load_ops'])
        self.assertEqual(row['profile']['zero_load_cycles'], prof['zero_load_cycles'])
        self.assertEqual(row['profile']['regions']['startup'], prof['regions']['startup']['cycles'])
        abl = json.loads(ABLATION.read_text(encoding='utf-8').strip().splitlines()[-1])
        self.assertEqual(abl['hypothesis'], 'itest')
        self.assertIn('keep', abl)
        self.assertIn('revert', abl)
        self.assertEqual(abl['peak_scratch'], prof['peak_live'])
        self.assertEqual(abl['valu_ops'], 0)
        self.assertEqual(abl['load_ops'], prof['load_ops'])

    def test_prof_only_full_official(self):
        print('[9/9] check.py --prof-only --full', flush=True)
        proc = subprocess.run(
            [sys.executable, '-u', str(ROOT / 'check.py'), '--prof-only', '--full', '-m', 'itest_full'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('cycles_est=147734', out)
        self.assertIn('history  keep=', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertEqual(prof['cycles_est'], BASELINE)
        self.assertEqual(prof['cycles_run'], BASELINE)
        self.assertTrue(prof['correct'])
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 10, 16, 256)


def main() -> int:
    print('profiler integration tests', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
