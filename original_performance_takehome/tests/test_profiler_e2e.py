"""End-to-end profiler tests: candidate CLI -> artifacts -> every metric family.

Drives check.py / check.bat the way a candidate would. Asserts the printed
lines, _last_profile.json schema, oneslot identities, and history/ablation
keep/revert fields. Restores the candidate's check artifacts afterwards.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from perf_takehome import BASELINE
from test_profiler_integration import _assert_oneslot_kernel, _assert_schema

LAST_PROF = ROOT / '_last_profile.json'
HISTORY = ROOT / '_check_history.jsonl'
ABLATION = ROOT / '_ablation.jsonl'

STDOUT_METRIC_LINES = (
    'cycles_est=',
    'ipc=',
    'idle=',
    'bottleneck=',
    'correct=true',
    'cycles_run=',
    'floor=',
    'overhead=',
    'sat=',
    'cp=',
    'cp_raw=',
    'cp_waw=',
    'cp_mem=',
    'dep=',
    'ports=',
    'waste=',
    'alu=',
    'valu=',
    'load=',
    'store=',
    'flow=',
    'ops=',
    'phases  ',
    'bounds  ',
    'depth  ',
    'alu_class  ',
    'scratch  ',
    'peak_vecs=',
    'war=',
    'same_cyc=',
    'ii=',
    'load_to_use=',
    'hist=',
    'regions  ',
    'unused  steady',
    'unused  drain',
    'occ_hist  ',
    'pressure  ',
    'overlap  ',
    'integrity  ',
    'rni_mean=',
    'mix  ',
    'mix_rle  ',
    'gather  ',
    'peak_live=',
    'top_ops  ',
    'slack  ',
    'live  ',
    'hyp  ',
    'history  keep=',
    'ablation  keep=',
    'revert=',
    'peak_scratch=',
    'valu_ops=',
    'load_ops=',
    'done',
)

HISTORY_PROFILE_KEYS = (
    'cycles_est',
    'cycles_run',
    'correct',
    'idle_cause',
    'bottleneck',
    'critical_path',
    'cp_raw',
    'cp_waw',
    'cp_mem',
    'work_bound',
    'floor',
    'floor_engine',
    'overhead',
    'mix_imbalance',
    'gather_scalar',
    'vselect_ops',
    'valu_ops',
    'load_ops',
    'peak_live',
    'peak_scratch',
    'zero_load_cycles',
    'load0_valu_lt6',
    'ii_est',
    'regions',
    'bounds',
    'gathers_by_depth',
    'integrity',
    'hypotheses',
    'fingerprint',
)

ABLATION_KEYS = (
    'ts',
    'note',
    'hypothesis',
    'keep',
    'revert',
    'cycles',
    'delta_cycles',
    'floor_engine',
    'floor_moved',
    'valu_ops',
    'load_ops',
    'peak_scratch',
    'peak_scratch_cap',
    'zero_load_cycles',
    'load0_valu_lt6',
    'ii_est',
    'integrity',
    'fingerprint',
)


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    print('    $ ' + ' '.join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _check(*flags: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return _run([sys.executable, '-u', str(ROOT / 'check.py'), *flags], timeout)


def _last_jsonl(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8').strip().splitlines()[-1])


class _RestoreCheckArtifacts(unittest.TestCase):
    """Keep the candidate's last profile / history / ablation after CLI tests."""

    def setUp(self):
        self._saved = {
            LAST_PROF: LAST_PROF.read_bytes() if LAST_PROF.is_file() else None,
            HISTORY: HISTORY.read_bytes() if HISTORY.is_file() else None,
            ABLATION: ABLATION.read_bytes() if ABLATION.is_file() else None,
        }
        LAST_PROF.unlink(missing_ok=True)

    def tearDown(self):
        for path, data in self._saved.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


class TestProfilerE2E(_RestoreCheckArtifacts):
    def _assert_stdout_metrics(self, out: str) -> None:
        for needle in STDOUT_METRIC_LINES:
            self.assertIn(needle, out, needle)
        self.assertNotIn('occ_series  ', out)

    def _assert_history_ablation(self, prof: dict, hypothesis: str) -> None:
        self.assertTrue(HISTORY.is_file())
        self.assertTrue(ABLATION.is_file())
        row = _last_jsonl(HISTORY)
        self.assertIn('keep', row)
        self.assertIn('revert', row)
        self.assertEqual(row['revert'], (not row['keep']))
        self.assertEqual(row['peak_scratch'], prof['peak_live'])
        self.assertEqual(row['peak_scratch_cap'], prof['scratch_capacity'])
        self.assertEqual(row['valu_ops'], prof['valu_ops'])
        self.assertEqual(row['load_ops'], prof['load_ops'])
        compact = row['profile']
        missing = [k for k in HISTORY_PROFILE_KEYS if k not in compact]
        self.assertEqual(missing, [])
        self.assertEqual(compact['cycles_est'], prof['cycles_est'])
        self.assertEqual(compact['cycles_run'], prof['cycles_run'])
        self.assertEqual(compact['zero_load_cycles'], prof['zero_load_cycles'])
        self.assertEqual(compact['load0_valu_lt6'], prof['load0_valu_lt6'])
        self.assertEqual(compact['ii_est'], prof['pipeline']['ii_est'])
        self.assertEqual(compact['peak_scratch'], prof['peak_live'])
        self.assertEqual(compact['regions']['startup'], prof['regions']['startup']['cycles'])
        self.assertEqual(compact['regions']['steady'], prof['regions']['steady']['cycles'])
        self.assertEqual(compact['regions']['drain'], prof['regions']['drain']['cycles'])
        self.assertEqual(compact['fingerprint'], prof['fingerprint'])
        abl = _last_jsonl(ABLATION)
        missing_abl = [k for k in ABLATION_KEYS if k not in abl]
        self.assertEqual(missing_abl, [])
        self.assertEqual(abl['hypothesis'], hypothesis)
        self.assertEqual(abl['keep'], row['keep'])
        self.assertEqual(abl['revert'], row['revert'])
        self.assertEqual(abl['cycles'], prof['cycles_run'])
        self.assertEqual(abl['peak_scratch'], prof['peak_live'])
        self.assertEqual(abl['valu_ops'], prof['valu_ops'])
        self.assertEqual(abl['load_ops'], prof['load_ops'])
        self.assertEqual(abl['zero_load_cycles'], prof['zero_load_cycles'])
        self.assertEqual(abl['load0_valu_lt6'], prof['load0_valu_lt6'])
        self.assertEqual(abl['ii_est'], prof['pipeline']['ii_est'])
        self.assertEqual(abl['fingerprint'], prof['fingerprint'])

    def test_smoke_prof_only_all_metric_families(self):
        print('[1/8] check.py --prof-only --smoke --hypothesis e2e_metrics', flush=True)
        proc = _check(
            '--prof-only',
            '--smoke',
            '--hypothesis',
            'e2e_metrics',
            '-m',
            'profiler_e2e_smoke',
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self._assert_stdout_metrics(out)
        self.assertIn('profile 3/2/8', out)
        self.assertTrue(LAST_PROF.is_file(), out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], 610)
        self.assertEqual(prof['cycles_run'], 610)
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 3, 2, 8)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['1'], 16)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['16_31'], 16)
        self._assert_history_ablation(prof, 'e2e_metrics')

    def test_official_prof_only_all_metrics(self):
        print('[2/8] check.py --prof-only --full -m profiler_e2e_full', flush=True)
        proc = _check('--prof-only', '--full', '-m', 'profiler_e2e_full', timeout=120)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self._assert_stdout_metrics(out)
        self.assertIn(f'cycles_est={BASELINE}', out)
        self.assertIn(f'cycles_run={BASELINE}', out)
        self.assertIn('profile 10/16/256', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], BASELINE)
        self.assertEqual(prof['cycles_run'], BASELINE)
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 10, 16, 256)
        self.assertEqual(prof['phase_gather'], 4096)
        self.assertEqual(prof['bounds']['gather_floor_all_scalar'], 2048)
        self.assertEqual(prof['bounds']['useful_op_floor'], 1093)
        self.assertEqual(prof['bounds']['fused_hash_floor'], 1024)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['1'], 4096)
        self.assertEqual(prof['pipeline']['load_to_use_hist']['16_31'], 4096)
        self.assertAlmostEqual(prof['pipeline']['ii_est'], 36.0, places=4)
        self.assertEqual(prof['alu_class']['idx'], 20480)
        self.assertEqual(prof['war_same_cycle'], 20480)
        self.assertEqual(prof['occupancy_series']['n'], 0)
        self._assert_history_ablation(prof, '')

    def test_prof_and_full_score_together(self):
        print('[3/8] check.py --prof --full (score + all profiler metrics)', flush=True)
        proc = _check(
            '--prof',
            '--full',
            '--hypothesis',
            'e2e_score',
            '-m',
            'profiler_e2e_score',
            timeout=120,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self._assert_stdout_metrics(out)
        self.assertIn(f'score  cycles={BASELINE}', out)
        self.assertIn('1.000x', out)
        self.assertIn('full 10/16/256', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertEqual(prof['cycles_est'], BASELINE)
        self.assertEqual(prof['cycles_run'], BASELINE)
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 10, 16, 256)
        row = _last_jsonl(HISTORY)
        self.assertTrue(row['ok'])
        self.assertEqual(row['full']['cycles'], BASELINE)
        self.assertEqual(row['profile']['cycles_est'], BASELINE)
        self.assertEqual(row['profile']['cycles_run'], row['full']['cycles'])
        self.assertIsNone(row.get('smoke'))
        self._assert_history_ablation(prof, 'e2e_score')

    def test_second_profile_zero_diff(self):
        print('[4/8] second --prof-only --smoke emits same-program diff', flush=True)
        first = _check('--prof-only', '--smoke', '-m', 'e2e_diff_a')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        first_fp = json.loads(LAST_PROF.read_text(encoding='utf-8'))['fingerprint']
        second = _check('--prof-only', '--smoke', '-m', 'e2e_diff_b')
        out = (second.stdout or '') + (second.stderr or '')
        self.assertEqual(second.returncode, 0, out)
        self.assertIn('diff  cycles=0', out)
        self.assertIn('same=True', out)
        self.assertIn('floor_moved=False', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['diff']['same_program'])
        self.assertEqual(prof['diff']['cycles_est'], 0)
        self.assertFalse(prof['diff']['floor_engine_changed'])
        self.assertFalse(prof['diff']['bottleneck_moved'])
        self.assertEqual(prof['fingerprint'], first_fp)
        abl = _last_jsonl(ABLATION)
        self.assertEqual(abl['delta_cycles'], 0)
        self.assertFalse(abl['floor_moved'])

    def test_keep_and_no_keep_flags(self):
        print('[5/8] check.py --keep / --no-keep write revert correctly', flush=True)
        kept = _check('--prof-only', '--smoke', '--keep', '--hypothesis', 'e2e_keep')
        out = (kept.stdout or '') + (kept.stderr or '')
        self.assertEqual(kept.returncode, 0, out)
        self.assertIn('history  keep=true', out)
        self.assertIn('revert=false', out)
        row = _last_jsonl(HISTORY)
        self.assertTrue(row['keep'])
        self.assertFalse(row['revert'])
        self.assertTrue(_last_jsonl(ABLATION)['keep'])
        reverted = _check('--prof-only', '--smoke', '--no-keep', '--hypothesis', 'e2e_revert')
        out = (reverted.stdout or '') + (reverted.stderr or '')
        self.assertEqual(reverted.returncode, 0, out)
        self.assertIn('history  keep=false', out)
        self.assertIn('revert=true', out)
        row = _last_jsonl(HISTORY)
        self.assertFalse(row['keep'])
        self.assertTrue(row['revert'])
        abl = _last_jsonl(ABLATION)
        self.assertFalse(abl['keep'])
        self.assertTrue(abl['revert'])
        self.assertEqual(abl['hypothesis'], 'e2e_revert')

    def test_audit_prints_integrity(self):
        print('[6/8] check.py --prof-only --smoke --audit', flush=True)
        proc = _check('--prof-only', '--smoke', '--audit', '--hypothesis', 'e2e_audit')
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self._assert_stdout_metrics(out)
        self.assertIn('  audit', out)
        self.assertIn('tests  tests/submission_tests.py', out)
        self.assertIn('tests  tests/frozen_problem.py', out)
        self.assertIn('tests  tests/test_engine.py', out)
        self.assertIn('frozen_vs_problem', out)
        self.assertIn('integrity  hash=', out)
        self.assertIn('skip_hash=', out)
        self.assertIn('cheat=', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['integrity']['hash_ops_present'])
        self.assertTrue(prof['integrity']['index_stores'])
        self.assertFalse(prof['integrity']['suspect_cheat'])
        self.assertFalse(prof['integrity']['suspect_skip_hash'])

    def test_check_bat_smoke_metrics(self):
        print('[7/8] check.bat --prof-only --smoke', flush=True)
        if sys.platform != 'win32':
            self.skipTest('check.bat is Windows')
        proc = _run(
            ['cmd', '/c', str(ROOT / 'check.bat'), '--prof-only', '--smoke', '-m', 'e2e_bat'],
            timeout=90,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self._assert_stdout_metrics(out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertEqual(prof['cycles_est'], 610)
        _assert_schema(self, prof)
        _assert_oneslot_kernel(self, prof, 3, 2, 8)

    def test_prof_smoke_pairs_score_and_profile(self):
        print('[8/8] check.py --prof --smoke pairs smoke cycles with profile', flush=True)
        proc = _check('--prof', '--smoke', '-m', 'e2e_pair', '--hypothesis', 'e2e_pair')
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self._assert_stdout_metrics(out)
        self.assertIn('smoke 3/2/8', out)
        self.assertIn('cycles=610', out)
        self.assertNotIn('full 10/16/256', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        row = _last_jsonl(HISTORY)
        self.assertTrue(row['ok'])
        self.assertTrue(row['smoke']['ok'])
        self.assertEqual(row['smoke']['cycles'], 610)
        self.assertEqual(row['profile']['cycles_est'], row['smoke']['cycles'])
        self.assertEqual(row['profile']['cycles_run'], row['smoke']['cycles'])
        self.assertIsNone(row.get('full'))
        _assert_schema(self, prof)
        self._assert_history_ablation(prof, 'e2e_pair')


def main() -> int:
    print('profiler end-to-end tests', flush=True)
    ordered = (
        'test_smoke_prof_only_all_metric_families',
        'test_official_prof_only_all_metrics',
        'test_prof_and_full_score_together',
        'test_second_profile_zero_diff',
        'test_keep_and_no_keep_flags',
        'test_audit_prints_integrity',
        'test_check_bat_smoke_metrics',
        'test_prof_smoke_pairs_score_and_profile',
    )
    suite = unittest.TestSuite()
    for name in ordered:
        suite.addTest(TestProfilerE2E(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
