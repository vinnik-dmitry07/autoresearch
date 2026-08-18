"""Unit tests for every static profiler metric."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vliw_native import profile_program

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


def _hist(prof: dict, name: str) -> list[int]:
    return list(((prof.get('occupancy_hist') or {}).get(name) or {}).get('hist') or [])


def _valu6(base: int = 0) -> dict:
    return {'valu': [('+', base + i * 8, 0, 0) for i in range(6)]}


class TestSchema(unittest.TestCase):
    def test_all_top_level_keys(self):
        prof = profile_program([{'load': [('const', 0, 1)]}])
        missing = [k for k in SCHEMA if k not in prof]
        self.assertEqual(missing, [])

    def test_nested_shapes(self):
        prof = profile_program([{'load': [('const', 0, 1)]}])
        self.assertEqual(set(prof['engines']), set(OCC_LIMIT))
        self.assertEqual(tuple(prof['phases']), PHASES)
        self.assertEqual(set(prof['occupancy_hist']), set(OCC_LIMIT))
        for name, limit in OCC_LIMIT.items():
            row = prof['occupancy_hist'][name]
            self.assertEqual(row['limit'], limit)
            self.assertEqual(len(row['hist']), OCC_HIST_LEN[name])
            self.assertIn('mean_used', row)
            self.assertIn('full', row)
        self.assertEqual(prof['mix']['target'], {'valu': 6, 'load': 2, 'store': 2, 'flow': 1})
        self.assertEqual(len(prof['select_vs_gather']['levels']), 6)
        self.assertEqual(set(prof['pipeline']['load_to_use_hist']), set(LOAD_USE_KEYS))
        self.assertEqual(set(prof['pipeline']['wavefront']), set(PHASES))
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
                self.assertIn(key, row)
        integ = prof['integrity']
        for key in (
            'hash_ops_present',
            'index_stores',
            'mux_used',
            'hash_like_ops',
            'suspect_skip_hash',
            'suspect_cheat',
        ):
            self.assertIn(key, integ)


class TestCoreSchedule(unittest.TestCase):
    def test_dep_chain_counts(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'load': [('const', 1, 2)]},
                {'alu': [('+', 2, 0, 1)]},
                {'load': [('const', 3, 0)]},
                {'store': [('store', 3, 2)]},
            ]
        )
        self.assertEqual(prof['cycles_est'], 5)
        self.assertEqual(prof['bundles'], 5)
        self.assertEqual(prof['slots'], 5)
        self.assertEqual(prof['debug_bundles'], 0)
        self.assertAlmostEqual(prof['ipc'], 1.0)
        self.assertEqual(prof['alu_ops'], 1)
        self.assertEqual(prof['valu_ops'], 0)
        self.assertEqual(prof['load_ops'], 3)
        self.assertEqual(prof['store_ops'], 1)
        self.assertEqual(prof['flow_ops'], 0)
        self.assertEqual(prof['const_ops'], 3)
        self.assertEqual(prof['store_scalar'], 1)
        self.assertEqual(prof['floor'], 2)
        self.assertEqual(prof['floor_engine'], 'load')
        self.assertEqual(prof['overhead'], 3)
        self.assertAlmostEqual(prof['overhead_frac'], 0.6, places=4)
        self.assertEqual(prof['critical_path'], 3)
        self.assertEqual(prof['cp_raw'], 3)
        self.assertEqual(prof['idle_cause'], 'deps')
        self.assertTrue(prof['assumes_linear'])
        self.assertFalse(prof['has_jumps'])

    def test_debug_skips_cycle(self):
        billed = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'debug': [('comment',)]},
                {'load': [('const', 1, 2)]},
            ],
            omit_debug=True,
        )
        kept = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'debug': [('comment',)]},
                {'load': [('const', 1, 2)]},
            ],
            omit_debug=False,
        )
        self.assertEqual(billed['cycles_est'], 2)
        self.assertEqual(billed['debug_bundles'], 0)
        self.assertEqual(kept['cycles_est'], 2)
        self.assertEqual(kept['debug_bundles'], 1)

    def test_debug_only_is_zero_cycles(self):
        prof = profile_program([{'debug': [('comment',)]}], omit_debug=False)
        self.assertEqual(prof['cycles_est'], 0)
        self.assertEqual(prof['debug_bundles'], 1)
        self.assertEqual(prof['slots'], 0)

    def test_jump_breaks_linear(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'flow': [('jump', 0)]},
            ]
        )
        self.assertTrue(prof['has_jumps'])
        self.assertFalse(prof['assumes_linear'])
        self.assertEqual(prof['flow_ops'], 1)

    def test_waw_and_mem_cp(self):
        waw = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'load': [('const', 0, 2)]},
            ]
        )
        self.assertEqual(waw['cp_raw'], 1)
        self.assertEqual(waw['cp_waw'], 2)
        mem = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'load': [('const', 1, 2)]},
                {'store': [('store', 0, 1)]},
                {'load': [('const', 2, 3)]},
                {'load': [('load', 3, 2)]},
            ]
        )
        self.assertEqual(mem['cp_raw'], 2)
        self.assertEqual(mem['cp_mem'], 3)


class TestOccupancy(unittest.TestCase):
    def test_oneslot_hist_is_ops_and_idle(self):
        prof = profile_program([{'load': [('const', i, 1)]} for i in range(8)])
        self.assertEqual(prof['zero_load_cycles'], 0)
        self.assertEqual(prof['load0_valu_lt6'], 0)
        self.assertEqual(_hist(prof, 'load'), [0, 8, 0])
        self.assertEqual(_hist(prof, 'alu'), [8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertAlmostEqual(prof['occupancy_hist']['load']['mean_used'], 1.0)
        self.assertEqual(prof['occupancy_hist']['load']['full'], 0)
        self.assertEqual(prof['occupancy_series']['n'], 0)

    def test_packed_load_hist(self):
        prof = profile_program([{'load': [('const', 0, 1), ('const', 1, 2)]}])
        self.assertEqual(prof['cycles_est'], 1)
        self.assertAlmostEqual(prof['ipc'], 2.0)
        self.assertEqual(_hist(prof, 'load'), [0, 0, 1])
        self.assertEqual(prof['zero_load_cycles'], 0)
        self.assertEqual(prof['port_full']['load'], 1)
        self.assertEqual(prof['saturation_cycles'], 1)
        self.assertEqual(prof['occupancy_series']['n'], 0)

    def test_packed_valu_full_and_series(self):
        prof = profile_program([_valu6()])
        self.assertEqual(prof['valu_ops'], 6)
        self.assertEqual(prof['zero_load_cycles'], 1)
        self.assertEqual(prof['load0_valu_lt6'], 0)
        self.assertEqual(_hist(prof, 'valu')[6], 1)
        self.assertEqual(prof['occupancy_hist']['valu']['full'], 1)
        self.assertEqual(prof['occupancy_series']['n'], 1)
        self.assertEqual(prof['occupancy_series']['valu'], [6])
        self.assertEqual(len(prof['pressure']['series']), 1)

    def test_full_valu_no_load_counts_bubble(self):
        prof = profile_program([_valu6(), {'load': [('const', 8, 1)]}, _valu6(16)])
        self.assertEqual(prof['zero_load_cycles'], 2)
        self.assertEqual(prof['load0_valu_lt6'], 0)
        self.assertEqual(prof['zero_load_cycles'] - prof['load0_valu_lt6'], 2)
        self.assertEqual(_hist(prof, 'valu')[6], 2)

    def test_oneslot_valu_gates_series(self):
        prof = profile_program([{'valu': [('+', i * 8, 0, 0)]} for i in range(18)])
        self.assertGreater(prof['overhead_frac'], 0.30)
        self.assertEqual(prof['occupancy_series']['n'], 0)
        self.assertEqual(prof['pressure']['series'], [])
        self.assertEqual(prof['zero_load_cycles'], prof['load0_valu_lt6'])

    def test_series_on_when_valu_and_overhead_low(self):
        prog = [_valu6(i * 48) for i in range(10)]
        prog.extend([{'load': [('const', 800, 1)]}, {'load': [('const', 801, 2)]}])
        prof = profile_program(prog)
        self.assertGreater(prof['valu_ops'], 0)
        self.assertLess(prof['overhead_frac'], 0.30)
        self.assertGreater(prof['occupancy_series']['n'], 0)
        self.assertEqual(len(prof['occupancy_series']['valu']), prof['occupancy_series']['n'])
        self.assertEqual(max(prof['occupancy_series']['valu']), 6)

    def test_unused_slots_match_limit_minus_used(self):
        prof = profile_program([{'load': [('const', i, 1)]} for i in range(4)])
        cycles = prof['cycles_est']
        regs = prof['regions']
        valu_unused = sum(int(regs[p]['valu_unused_slots']) for p in ('startup', 'steady', 'drain'))
        load_unused = sum(int(regs[p]['load_unused_slots']) for p in ('startup', 'steady', 'drain'))
        self.assertEqual(valu_unused, cycles * 6 - prof['valu_ops'])
        self.assertEqual(load_unused, cycles * 2 - prof['load_ops'])

    def test_engine_occupancy_matches_ops(self):
        prof = profile_program([{'alu': [('+', 0, 0, 0)]} for _ in range(12)])
        alu = prof['engines']['alu']
        self.assertEqual(alu['ops'], 12)
        self.assertEqual(alu['limit'], 12)
        self.assertAlmostEqual(alu['occupancy'], 12 / (12 * 12), places=4)
        self.assertEqual(alu['work_bound'], 1)


class TestRegions(unittest.TestCase):
    def test_init_prefix_and_suffix(self):
        prof = profile_program(
            [{'load': [('const', i, 1)]} for i in range(6)],
            phases=[1, 1, 3, 3, 3, 1],
            rounds=3,
            batch_size=2,
        )
        r = prof['regions']
        self.assertEqual(r['startup_end'], 2)
        self.assertEqual(r['drain_start'], 5)
        self.assertEqual(r['startup']['cycles'], 2)
        self.assertEqual(r['steady']['cycles'], 3)
        self.assertEqual(r['drain']['cycles'], 1)
        self.assertEqual(r['startup']['cycles'] + r['steady']['cycles'] + r['drain']['cycles'], 6)
        self.assertEqual(r['startup']['cycles'] + r['drain']['cycles'], prof['phase_init'])
        self.assertAlmostEqual(prof['pipeline']['ii_est'], 0.5, places=4)
        self.assertEqual(prof['pipeline']['steady_cycles'], 3)
        self.assertEqual(prof['pipeline']['item_rounds'], 6)
        self.assertEqual(prof['pipeline']['wavefront']['hash'], 3)
        self.assertEqual(prof['pipeline']['wavefront']['init'], 0)
        self.assertEqual(prof['bounds']['item_rounds'], 6)

    def test_drain_trailing_idle_flow(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'alu': [('+', 1, 0, 0)]},
                {'flow': [('pause',)]},
                {'flow': [('pause',)]},
            ]
        )
        r = prof['regions']
        self.assertEqual(r['startup']['cycles'], 0)
        self.assertEqual(r['steady']['cycles'], 2)
        self.assertEqual(r['drain']['cycles'], 2)
        self.assertEqual(r['drain']['zero_load'], 2)
        self.assertEqual(r['drain']['valu_unused_slots'], 12)
        self.assertEqual(r['drain']['flow_unused_slots'], 0)

    def test_no_phase_is_all_steady(self):
        prof = profile_program([{'load': [('const', 0, 1)]}] * 3)
        r = prof['regions']
        self.assertEqual(r['startup_end'], 0)
        self.assertEqual(r['drain_start'], 3)
        self.assertEqual(r['steady']['cycles'], 3)


class TestLiveAndWar(unittest.TestCase):
    def test_peak_live_and_pressure(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'load': [('const', 1, 2)]},
                {'alu': [('+', 2, 0, 1)]},
            ]
        )
        self.assertEqual(prof['peak_live'], 3)
        self.assertEqual(prof['cells_touched'], 3)
        self.assertEqual(prof['pressure']['peak'], 3)
        self.assertEqual(prof['scratch_vectors']['peak_live'], 3)
        self.assertEqual(prof['scratch_capacity'], 1536)
        self.assertEqual(prof['scratch_vectors']['capacity_vecs'], 192)

    def test_war_same_cycle_packed(self):
        prof = profile_program([{'alu': [('+', 2, 0, 1)], 'load': [('const', 0, 9)]}])
        self.assertEqual(prof['war_same_cycle'], 1)
        self.assertEqual(prof['scratch_vectors']['war_same_cycle'], 1)

    def test_named_overlaps(self):
        scratch = {0: ('tmp_a', 1), 1: ('tmp_b', 1), 2: ('tmp_c', 1)}
        prof = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'load': [('const', 1, 2)]},
                {'alu': [('+', 2, 0, 1)]},
            ],
            scratch_debug=scratch,
        )
        self.assertEqual(prof['war_named_overlaps'], 3)
        pairs = {(row['a'], row['b']) for row in prof['live_overlaps']}
        self.assertGreaterEqual(len(pairs), 1)
        names = {row['name'] for row in prof['named_live']}
        self.assertEqual(names, {'tmp_a', 'tmp_b', 'tmp_c'})
        self.assertTrue(all(row['writes'] == 1 for row in prof['named_live']))

    def test_loop_carried_needs_many_writes(self):
        scratch = {0: ('acc', 1)}
        prog = [{'load': [('const', 0, i + 1)]} for i in range(20)]
        prof = profile_program(prog, scratch_debug=scratch)
        acc = next(row for row in prof['named_live'] if row['name'] == 'acc')
        self.assertTrue(acc['loop_carried'])
        self.assertEqual(acc['writes'], 20)


class TestPipelineLoadToUse(unittest.TestCase):
    def test_immediate_use(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 10)]},
                {'load': [('load', 1, 0)]},
                {'alu': [('+', 2, 1, 1)]},
            ]
        )
        pipe = prof['pipeline']
        self.assertEqual(pipe['load_to_use_n'], 1)
        self.assertEqual(pipe['load_to_use_p50'], 1)
        self.assertEqual(pipe['load_to_use_p95'], 1)
        self.assertAlmostEqual(pipe['load_to_use_mean'], 1.0)
        self.assertEqual(pipe['load_to_use_hist']['1'], 1)

    def test_hist_buckets_and_percentiles(self):
        prog = []
        for i in range(4):
            base = i * 8
            prog.append({'load': [('const', base, 10)]})
            prog.append({'load': [('load', base + 1, base)]})
            prog.append({'alu': [('+', base + 2, base + 1, base + 1)]})
        prog.append({'load': [('const', 40, 10)]})
        prog.append({'load': [('load', 41, 40)]})
        for _ in range(19):
            prog.append({'load': [('const', 50, 1)]})
        prog.append({'alu': [('+', 42, 41, 41)]})
        prof = profile_program(prog)
        hist = prof['pipeline']['load_to_use_hist']
        self.assertEqual(hist['1'], 4)
        self.assertEqual(hist['16_31'], 1)
        self.assertEqual(prof['pipeline']['load_to_use_n'], 5)
        self.assertEqual(prof['pipeline']['load_to_use_p50'], 1)
        self.assertGreaterEqual(prof['pipeline']['load_to_use_p95'], 1)

    def test_const_is_not_load_to_use(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 1)]},
                {'alu': [('+', 1, 0, 0)]},
            ]
        )
        self.assertEqual(prof['pipeline']['load_to_use_n'], 0)


class TestMixBoundsIntegrity(unittest.TestCase):
    def test_mix_ratios_and_rle(self):
        prof = profile_program([_valu6(), {'load': [('const', 0, 1), ('const', 1, 2)]}])
        self.assertAlmostEqual(prof['valu_per_load'], 3.0)
        self.assertEqual(prof['mix']['target']['valu'], 6)
        self.assertTrue(prof['mix']['rle'])
        self.assertIn(prof['mix_imbalance'], ('balanced', 'valu_heavy', 'load_heavy'))

    def test_bounds_from_shape(self):
        prof = profile_program(
            [{'load': [('load', i, 0)]} for i in range(4)],
            forest_height=10,
            rounds=16,
            batch_size=256,
        )
        b = prof['bounds']
        self.assertEqual(b['height'], 10)
        self.assertEqual(b['rounds'], 16)
        self.assertEqual(b['batch'], 256)
        self.assertEqual(b['item_rounds'], 4096)
        self.assertEqual(b['tiles'], 32)
        self.assertEqual(b['gather_floor_all_scalar'], 2048)
        self.assertEqual(b['useful_op_floor'], 1093)
        self.assertEqual(b['fused_hash_floor'], 1024)
        self.assertEqual(b['load_floor'], 2)
        self.assertEqual(b['peak_slots'], 23)

    def test_gathers_by_depth_and_alu_class(self):
        prof = profile_program(
            [
                {'alu': [('^', 0, 1, 2)]},
                {'load': [('load', 3, 0)]},
                {'load': [('load', 4, 0)]},
            ],
            phases=[3, 6, 6],
            depths=[0, 0, 2],
        )
        self.assertEqual(prof['alu_class']['hash'], 1)
        self.assertEqual(prof['gathers_by_depth']['0']['gathers'], 1)
        self.assertEqual(prof['gathers_by_depth']['2']['gathers'], 1)
        self.assertEqual(prof['pipeline']['shallow_gathers'], 2)

    def test_integrity_hash_mux_stores(self):
        hashed = profile_program(
            [
                {'alu': [('^', 0, 1, 2)]},
                {'store': [('store', 3, 0)]},
                {'flow': [('vselect', 16, 1, 8, 8)]},
            ]
        )
        self.assertTrue(hashed['integrity']['hash_ops_present'])
        self.assertTrue(hashed['integrity']['index_stores'])
        self.assertTrue(hashed['integrity']['mux_used'])
        self.assertGreater(hashed['integrity']['hash_like_ops'], 0)
        self.assertFalse(hashed['integrity']['suspect_skip_hash'])

    def test_integrity_skip_hash_and_cheat(self):
        prof = profile_program(
            [{'load': [('load', i, 0)]} for i in range(4)],
            forest_height=10,
            rounds=16,
            batch_size=8,
        )
        self.assertGreater(prof['bounds']['item_rounds'], 64)
        self.assertTrue(prof['integrity']['suspect_skip_hash'])
        self.assertTrue(prof['integrity']['suspect_cheat'])
        self.assertFalse(prof['integrity']['hash_ops_present'])

    def test_op_class_counts(self):
        prof = profile_program(
            [
                {'load': [('const', 0, 10)]},
                {'load': [('load', 1, 0)]},
                {'load': [('load_offset', 2, 0, 1)]},
                {'load': [('vload', 8, 0)]},
                {'store': [('vstore', 3, 8)]},
                {'flow': [('vselect', 16, 1, 8, 8)]},
                {'flow': [('select', 4, 1, 2, 1)]},
                {'flow': [('add_imm', 5, 4, 1)]},
                {'valu': [('multiply_add', 24, 8, 8, 8)]},
                {'valu': [('vbroadcast', 32, 0)]},
            ]
        )
        self.assertEqual(prof['gather_scalar'], 1)
        self.assertEqual(prof['load_ops'], 4)
        self.assertEqual(prof['vload_ops'], 1)
        self.assertEqual(prof['vstore_ops'], 1)
        self.assertEqual(prof['vselect_ops'], 1)
        self.assertEqual(prof['select_ops'], 1)
        self.assertEqual(prof['madd_ops'], 1)
        self.assertEqual(prof['const_ops'], 1)
        self.assertEqual(prof['flow_ops'], 3)

    def test_select_vs_gather_levels(self):
        prof = profile_program([{'load': [('const', 0, 1)]}])
        levels = prof['select_vs_gather']['levels']
        self.assertEqual(levels[0]['prefer'], 'select')
        self.assertEqual(levels[3]['prefer'], 'select')
        self.assertEqual(levels[4]['prefer'], 'mixed')
        self.assertEqual(levels[5]['prefer'], 'gather')


class TestDiffFingerprintHints(unittest.TestCase):
    def test_fingerprint_stable(self):
        a = profile_program([{'load': [('const', 0, 7)]}])
        b = profile_program([{'load': [('const', 0, 7)]}])
        c = profile_program([{'load': [('const', 0, 8)]}])
        self.assertEqual(a['fingerprint'], b['fingerprint'])
        self.assertNotEqual(a['fingerprint'], c['fingerprint'])
        self.assertEqual(len(a['fingerprint']), 16)

    def test_diff_deltas(self):
        prev = profile_program([{'load': [('load', i, 0)]} for i in range(8)])
        cur = profile_program(
            [{'valu': [('+', i * 8, 0, 0)]} for i in range(12)],
            prev_json=json.dumps(prev),
        )
        d = cur['diff']
        self.assertFalse(d['same_program'])
        self.assertTrue(d['floor_engine_changed'])
        self.assertEqual(d['gather_scalar'], -8)
        self.assertEqual(d['valu_ops'], 12)
        self.assertEqual(d['load_ops'], -8)
        same = profile_program(
            [{'load': [('load', i, 0)]} for i in range(8)],
            prev_json=json.dumps(prev),
        )
        self.assertTrue(same['diff']['same_program'])
        self.assertEqual(same['diff']['cycles_est'], 0)

    def test_hypotheses_and_hints_oneslot(self):
        prof = profile_program([{'load': [('const', i, 1)]} for i in range(32)])
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertTrue({'pipeline', 'oneslot'} <= tags)
        self.assertTrue(all('tag' in h and 'why' in h for h in prof['hypotheses']))
        self.assertGreater(len(prof['hints']), 0)
        self.assertEqual(prof['top_ops'][0][0], 'load.const')
        self.assertEqual(prof['top_ops'][0][1], 32)

    def test_top_slack_omits_pause(self):
        prof = profile_program(
            [
                {'flow': [('pause',)]},
                {'load': [('const', 0, 1)]},
                {'load': [('const', 1, 2)]},
                {'alu': [('+', 2, 0, 1)]},
            ]
        )
        self.assertNotIn('flow.pause', [row['op'] for row in prof['top_slack']])


class TestHistoryContract(unittest.TestCase):
    def test_fields_history_reads_exist(self):
        prof = profile_program([_valu6(), {'load': [('const', 0, 1)]}])
        for key in (
            'cycles_est',
            'valu_ops',
            'load_ops',
            'peak_live',
            'zero_load_cycles',
            'load0_valu_lt6',
            'floor_engine',
            'fingerprint',
            'regions',
            'integrity',
        ):
            self.assertIn(key, prof)
        self.assertIn('ii_est', prof['pipeline'])

    def test_keep_revert_rule(self):
        def decide(cycles_now, last_cycles, explicit=None):
            if explicit is not None:
                keep = bool(explicit)
            elif last_cycles is not None and cycles_now is not None:
                keep = int(cycles_now) <= int(last_cycles)
            else:
                keep = True
            return keep, not keep

        self.assertEqual(decide(100, 120), (True, False))
        self.assertEqual(decide(130, 120), (False, True))
        self.assertEqual(decide(120, 120), (True, False))
        self.assertEqual(decide(100, None), (True, False))
        self.assertEqual(decide(200, 100, explicit=True), (True, False))
        self.assertEqual(decide(50, 100, explicit=False), (False, True))


def main() -> int:
    print('profiler metric tests', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
