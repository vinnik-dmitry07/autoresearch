'''Per-arm A3 sweep template tokenization.'''
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from ladder_lib import (  # noqa: E402
    prepare_per_arm_sweep_template,
    sweep_variant_count,
)


class PerArmSweepTestCase(unittest.TestCase):
    def test_kdelta_tokenized(self) -> None:
        snap = 'constexpr int kDelta = 2;\nif (x >= kDelta) {}\n'
        tpl, axes = prepare_per_arm_sweep_template(snap)
        self.assertIn('__SWEEP_KDELTA__', tpl)
        self.assertNotIn('constexpr int kDelta = 2;', tpl)
        self.assertEqual(axes['__SWEEP_KDELTA__'], ['1', '2', '3'])
        self.assertEqual(sweep_variant_count(axes), 3)

    def test_threshold_literals_when_no_kdelta(self) -> None:
        snap = (
            'if (L.deck_count >= 5 && rank_of(c) >= 7) {}\n'
            'if (L.opponent_hand_count <= 2) {}\n'
        )
        tpl, axes = prepare_per_arm_sweep_template(snap)
        self.assertIn('__SWEEP_0__', tpl)
        self.assertIn('__SWEEP_1__', tpl)
        self.assertIn('__SWEEP_2__', tpl)
        self.assertEqual(len(axes), 3)
        self.assertEqual(sweep_variant_count(axes), 27)


if __name__ == '__main__':
    unittest.main()
