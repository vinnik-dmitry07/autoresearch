"""End-to-end tests: documented user commands and the submission harness.

Drives the C++ engine the same way a candidate would: KernelBuilder, problem.Machine
factory, perf_takehome.do_kernel_test, check.py / check.bat, and the frozen
reference from tests/. Does not modify submission_tests.py or frozen_problem.py.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import frozen_problem
from perf_takehome import BASELINE, KernelBuilder, do_kernel_test
from problem import DebugInfo, Machine, PythonMachine
from vliw_native import FastMachine, cpp_available, _lib_path

LAST_PROF = ROOT / '_last_profile.json'
HISTORY = ROOT / '_check_history.jsonl'
TRACE = ROOT / 'trace.json'


@lru_cache(maxsize=None)
def _kernel(forest_height: int, n_nodes: int, batch_size: int, rounds: int) -> KernelBuilder:
    kb = KernelBuilder()
    kb.build_kernel(forest_height, n_nodes, batch_size, rounds)
    return kb


def _submission_shaped(forest_height: int, rounds: int, batch_size: int) -> int:
    """Same protocol as tests/submission_tests.py, but Machine is our C++ factory."""
    forest = frozen_problem.Tree.generate(forest_height)
    inp = frozen_problem.Input.generate(forest, batch_size, rounds)
    mem = frozen_problem.build_mem_image(forest, inp)
    kb = _kernel(forest.height, len(forest.values), len(inp.indices), rounds)
    machine = Machine(list(mem), kb.instrs, kb.debug_info(), n_cores=frozen_problem.N_CORES)
    machine.enable_pause = False
    machine.enable_debug = False
    machine.run()
    ref_mem = None
    for ref_mem in frozen_problem.reference_kernel2(mem):
        pass
    inp_values_p = ref_mem[6]
    got = machine.mem[inp_values_p : inp_values_p + len(inp.values)]
    want = ref_mem[inp_values_p : inp_values_p + len(inp.values)]
    if got != want:
        raise AssertionError('Incorrect output values')
    return machine.cycle


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


class _RestoreCheckArtifacts(unittest.TestCase):
    """Keep the candidate's last profile / history after CLI tests."""

    def setUp(self):
        self._saved = {
            LAST_PROF: LAST_PROF.read_bytes() if LAST_PROF.is_file() else None,
            HISTORY: HISTORY.read_bytes() if HISTORY.is_file() else None,
        }
        LAST_PROF.unlink(missing_ok=True)

    def tearDown(self):
        for path, data in self._saved.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


class TestArtifacts(unittest.TestCase):
    def test_release_dll_on_default_path(self):
        print('[1/14] release DLL on build/', flush=True)
        path = _lib_path()
        self.assertTrue(path.is_file(), f'missing native library: {path}')
        self.assertTrue(cpp_available())
        self.assertEqual(path.parent, ROOT / 'build')


class TestDocumentedLocalCheck(unittest.TestCase):
    def test_do_kernel_test_api(self):
        print('[2/14] perf_takehome.do_kernel_test(10, 16, 256)', flush=True)
        cycles = do_kernel_test(10, 16, 256, seed=123)
        self.assertEqual(cycles, BASELINE)
        self.assertEqual(BASELINE / cycles, 1.0)

    def test_perf_takehome_cli(self):
        print('[3/14] python perf_takehome.py Tests.test_kernel_cycles', flush=True)
        proc = _run(
            [sys.executable, '-u', str(ROOT / 'perf_takehome.py'), 'Tests.test_kernel_cycles'],
            timeout=90,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('CYCLES:', out)
        self.assertIn(str(BASELINE), out)
        self.assertIn('Speedup over baseline:', out)


class TestSubmissionProtocol(unittest.TestCase):
    def test_eight_unseeded_runs_like_official_harness(self):
        print('[4/14] 8× unseeded 10/16/256 (frozen ref, C++ Machine)', flush=True)
        cycles = []
        for i in range(8):
            print(f'  harness {i + 1}/8', flush=True)
            n = _submission_shaped(10, 16, 256)
            self.assertEqual(n, BASELINE, f'run {i + 1} cycles={n}')
            cycles.append(n)
        self.assertEqual(len(set(cycles)), 1)
        self.assertLess(cycles[0], BASELINE * 2)

    def test_factory_is_cpp_on_real_kernel(self):
        print('[5/14] Machine() factory on a real kernel is FastMachine', flush=True)
        random.seed(123)
        forest = frozen_problem.Tree.generate(4)
        inp = frozen_problem.Input.generate(forest, 8, 2)
        mem = frozen_problem.build_mem_image(forest, inp)
        kb = _kernel(forest.height, len(forest.values), len(inp.indices), 2)
        machine = Machine(list(mem), kb.instrs, kb.debug_info(), n_cores=frozen_problem.N_CORES)
        self.assertIsInstance(machine, FastMachine)
        machine.enable_pause = False
        machine.enable_debug = False
        machine.run()
        ref = None
        for ref in frozen_problem.reference_kernel2(list(mem)):
            pass
        p = ref[6]
        self.assertEqual(
            machine.mem[p : p + len(inp.values)],
            ref[p : p + len(inp.values)],
        )


class TestHypothesisCheckCli(_RestoreCheckArtifacts):
    def test_check_prof_only_smoke(self):
        print('[6/14] python check.py --prof-only --smoke', flush=True)
        proc = _check('--prof-only', '--smoke', timeout=90)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('correct=true', out)
        self.assertIn('floor=', out)
        self.assertIn('hyp  ', out)
        self.assertIn('done', out)
        self.assertTrue(LAST_PROF.is_file(), out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], prof['cycles_run'])
        self.assertGreater(prof['floor'], 0)
        self.assertTrue(prof['hypotheses'])

    def test_check_prof_smoke_writes_history(self):
        print('[7/14] python check.py --prof --smoke -m e2e', flush=True)
        proc = _check('--prof', '--smoke', '-m', 'e2e', timeout=90)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('correct=true', out)
        self.assertTrue(HISTORY.is_file(), out)
        last = json.loads(HISTORY.read_text(encoding='utf-8').strip().splitlines()[-1])
        self.assertEqual(last['note'], 'e2e')
        self.assertTrue(last['ok'])
        self.assertTrue(last['smoke']['ok'])
        self.assertIsNone(last.get('full'))
        prof = last['profile']
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], last['smoke']['cycles'])
        self.assertEqual(prof['cycles_run'], last['smoke']['cycles'])

    def test_check_prof_only_full_matches_baseline(self):
        print('[8/14] python check.py --prof-only --full', flush=True)
        proc = _check('--prof-only', '--full', timeout=120)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('correct=true', out)
        self.assertIn(f'cycles_est={BASELINE}', out)
        self.assertIn(f'cycles_run={BASELINE}', out)
        self.assertIn('floor=', out)
        self.assertIn('hyp  ', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['correct'])
        self.assertEqual(prof['cycles_est'], BASELINE)
        self.assertEqual(prof['cycles_run'], BASELINE)
        self.assertEqual(prof['mix_imbalance'], 'scalar_alu')
        self.assertGreater(prof['gather_scalar'], 0)
        tags = {h['tag'] for h in prof['hypotheses']}
        self.assertTrue({'pipeline', 'oneslot', 'valu_unused', 'gather'} & tags)

    def test_second_profile_emits_zero_diff(self):
        print('[9/14] second --prof-only --smoke emits same-program diff', flush=True)
        first = _check('--prof-only', '--smoke', timeout=90)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = _check('--prof-only', '--smoke', timeout=90)
        out = (second.stdout or '') + (second.stderr or '')
        self.assertEqual(second.returncode, 0, out)
        self.assertIn('diff  cycles=0', out)
        self.assertIn('same=True', out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertTrue(prof['diff']['same_program'])
        self.assertEqual(prof['diff']['cycles_est'], 0)
        self.assertFalse(prof['diff']['floor_engine_changed'])

    def test_check_bat_prof_only_smoke(self):
        print('[10/14] check.bat --prof-only --smoke', flush=True)
        if sys.platform != 'win32':
            self.skipTest('check.bat is Windows')
        proc = _run(
            ['cmd', '/c', str(ROOT / 'check.bat'), '--prof-only', '--smoke'],
            timeout=90,
        )
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('correct=true', out)
        self.assertTrue(LAST_PROF.is_file(), out)
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        self.assertEqual(prof['cycles_est'], prof['cycles_run'])

    def test_check_smoke_only(self):
        print('[11/14] python check.py --smoke', flush=True)
        proc = _check('--smoke', timeout=90)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('smoke 3/2/8', out)
        self.assertIn('cycles=', out)
        self.assertNotIn('profile 3/2/8', out)
        last = json.loads(HISTORY.read_text(encoding='utf-8').strip().splitlines()[-1])
        self.assertTrue(last['ok'])
        self.assertTrue(last['smoke']['ok'])
        self.assertGreater(last['smoke']['cycles'], 0)

    def test_check_full_prints_score(self):
        print('[12/14] python check.py --full', flush=True)
        proc = _check('--full', timeout=90)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn('full 10/16/256', out)
        self.assertIn(f'score  cycles={BASELINE}', out)
        self.assertIn('1.000x', out)
        last = json.loads(HISTORY.read_text(encoding='utf-8').strip().splitlines()[-1])
        self.assertEqual(last['full']['cycles'], BASELINE)
        self.assertTrue(last['ok'])


class TestTracePath(unittest.TestCase):
    def test_write_small_trace_artifact(self):
        print('[13/14] check.write_small_trace (no Perfetto UI)', flush=True)
        dest = ROOT / '_e2e_trace.json'
        dest.unlink(missing_ok=True)
        saved = TRACE.read_bytes() if TRACE.is_file() else None
        try:
            from check import write_small_trace

            write_small_trace(dest)
            self.assertTrue(dest.is_file())
            self.assertGreater(dest.stat().st_size, 1000)
            text = dest.read_text(encoding='utf-8')
            self.assertTrue(text.lstrip().startswith('['))
            self.assertIn('"ph": "X"', text)
            self.assertIn('"cat": "op"', text)
            self.assertIn('alu-', text)
        finally:
            dest.unlink(missing_ok=True)
            if saved is None:
                TRACE.unlink(missing_ok=True)
            else:
                TRACE.write_bytes(saved)

    def test_trace_flag_uses_python_machine(self):
        print('[14/14] Machine(trace=True) falls back to PythonMachine', flush=True)
        if TRACE.is_file():
            TRACE.unlink()
        machine = Machine(
            [0] * 8,
            [{'flow': [('halt',)]}],
            DebugInfo(scratch_map={}),
            trace=True,
        )
        try:
            self.assertIsInstance(machine, PythonMachine)
            machine.run()
        finally:
            del machine
            if TRACE.is_file():
                TRACE.unlink()


def main() -> int:
    print('engine end-to-end tests', flush=True)
    ordered = (
        (TestArtifacts, 'test_release_dll_on_default_path'),
        (TestDocumentedLocalCheck, 'test_do_kernel_test_api'),
        (TestDocumentedLocalCheck, 'test_perf_takehome_cli'),
        (TestSubmissionProtocol, 'test_eight_unseeded_runs_like_official_harness'),
        (TestSubmissionProtocol, 'test_factory_is_cpp_on_real_kernel'),
        (TestHypothesisCheckCli, 'test_check_prof_only_smoke'),
        (TestHypothesisCheckCli, 'test_check_prof_smoke_writes_history'),
        (TestHypothesisCheckCli, 'test_check_prof_only_full_matches_baseline'),
        (TestHypothesisCheckCli, 'test_second_profile_emits_zero_diff'),
        (TestHypothesisCheckCli, 'test_check_bat_prof_only_smoke'),
        (TestHypothesisCheckCli, 'test_check_smoke_only'),
        (TestHypothesisCheckCli, 'test_check_full_prints_score'),
        (TestTracePath, 'test_write_small_trace_artifact'),
        (TestTracePath, 'test_trace_flag_uses_python_machine'),
    )
    suite = unittest.TestSuite()
    for cls, name in ordered:
        suite.addTest(cls(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
