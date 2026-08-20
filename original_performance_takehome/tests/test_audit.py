"""Unit tests for check.py tamper audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from check import PINNED_SHA256, _audit_report, _file_digest, _spec_drift


class TestAuditGuard(unittest.TestCase):
    def test_pinned_official_files_match(self):
        print('[1/3] pinned submission_tests + frozen_problem', flush=True)
        for rel, want in PINNED_SHA256.items():
            digest = _file_digest(ROOT / rel)
            self.assertEqual(digest, want, rel)

    def test_report_same_and_ok(self):
        print('[2/3] audit report is clean', flush=True)
        report = _audit_report()
        self.assertEqual(report['missing'], [])
        self.assertTrue(report['digest_ok'])
        self.assertEqual(report['drift'], [])
        self.assertEqual(report['frozen_vs_problem'], 'same')
        self.assertTrue(report['ok'])
        by_rel = {row['rel']: row for row in report['files']}
        self.assertEqual(by_rel['tests/frozen_problem.py']['status'], 'ok')
        self.assertEqual(by_rel['tests/submission_tests.py']['status'], 'ok')
        self.assertEqual(by_rel['tests/test_engine.py']['status'], 'local')

    def test_spec_drift_empty(self):
        print('[3/3] problem.py spec matches frozen_problem.py', flush=True)
        self.assertEqual(_spec_drift(), [])


def main() -> int:
    print('audit guard tests', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
