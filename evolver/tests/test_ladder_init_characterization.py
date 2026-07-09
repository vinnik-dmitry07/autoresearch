'''Golden characterization for A8/A8s Claude-meta init and refresh (regression gate).'''
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from evolver.config import load_config, overlay_claude_meta_session  # noqa: E402
from ladder_lib import (  # noqa: E402
    REPO_ROOT,
    apply_scratch_files,
    arm_uses_claude_meta,
    load_arm_config,
    materialize_claude_meta_mechanism,
    read_worktree_config,
    refresh_claude_meta_config,
    resolve_template_arm,
    write_json,
    _is_strict_claude_meta,
    _purge_family_map_for_arm,
)

A8_CFG = ROOT / 'scripts' / 'ladder_configs' / 'A8.json'
A8S_CFG = ROOT / 'scripts' / 'ladder_configs' / 'A8s.json'
A8S_SEED = ROOT / 'evolve' / 'mechanism' / 'evolve_skill_a8s.md'

STRICT_SEED_POSITIVE = (
    '## Heuristic families (self-contained)',
    'do not rely on any external family file',
)
STRICT_SEED_NEGATIVE = ('family_map.md', 'Maintain `family_map.md`')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_markers(skill_text: str) -> tuple[bool, bool]:
    pos = all(m in skill_text for m in STRICT_SEED_POSITIVE)
    neg = not any(m in skill_text for m in STRICT_SEED_NEGATIVE)
    return pos, neg


def _meta_session_dict(cfg: dict) -> dict:
    return (cfg.get('meta') or {}).get('session') or {}


def _setup_claude_worktree(tmp: Path, arm: str) -> Path:
    wt = tmp / arm
    wt.mkdir(parents=True)
    apply_scratch_files(wt, REPO_ROOT)
    arm_cfg = load_arm_config(arm)
    if arm_uses_claude_meta(arm):
        materialize_claude_meta_mechanism(
            wt, REPO_ROOT, strict=_is_strict_claude_meta(arm_cfg),
        )
    _purge_family_map_for_arm(arm, wt)
    write_json(wt / 'evolve' / 'config.json', arm_cfg)
    return wt


class GoldenA9InitTestCase(unittest.TestCase):
    def test_a9_family_map_absent(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A9')
        self.assertFalse((wt / 'evolve' / 'mechanism' / 'family_map.md').is_file())
        tmp.cleanup()

    def test_a9_evolve_skill_strict_seed(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A9')
        skill = wt / 'evolve' / 'mechanism' / 'evolve_skill.md'
        self.assertEqual(_sha256(skill), _sha256(A8S_SEED))
        text = skill.read_text(encoding='utf-8')
        pos, neg = _skill_markers(text)
        self.assertTrue(pos)
        self.assertTrue(neg)
        tmp.cleanup()


class GoldenInitCharacterizationTestCase(unittest.TestCase):
    def test_a8_mechanism_files(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8')
        mech = wt / 'evolve' / 'mechanism'
        self.assertTrue((mech / 'a8_meta_constitution.md').is_file())
        self.assertTrue((mech / 'a8_meta_claude_settings.json').is_file())
        self.assertFalse((mech / 'a8s_meta_constitution.md').is_file())
        self.assertFalse((mech / 'a8s_meta_skill.md').is_file())
        tmp.cleanup()

    def test_a8s_mechanism_files(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8s')
        mech = wt / 'evolve' / 'mechanism'
        self.assertTrue((mech / 'a8s_meta_constitution.md').is_file())
        self.assertTrue((mech / 'a8s_meta_skill.md').is_file())
        self.assertTrue((mech / 'a8_meta_claude_settings.json').is_file())
        tmp.cleanup()

    def test_a8_evolve_skill_not_a8s_seed(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8')
        skill = wt / 'evolve' / 'mechanism' / 'evolve_skill.md'
        self.assertNotEqual(_sha256(skill), _sha256(A8S_SEED))
        text = skill.read_text(encoding='utf-8')
        pos, neg = _skill_markers(text)
        self.assertFalse(pos, 'A8 scratch seed must not satisfy strict self-contained markers')
        tmp.cleanup()

    def test_a8s_evolve_skill_matches_a8s_seed(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8s')
        skill = wt / 'evolve' / 'mechanism' / 'evolve_skill.md'
        self.assertEqual(_sha256(skill), _sha256(A8S_SEED))
        text = skill.read_text(encoding='utf-8')
        pos, neg = _skill_markers(text)
        self.assertTrue(pos)
        self.assertTrue(neg)
        tmp.cleanup()

    def test_a8s_family_map_present_on_disk(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8s')
        self.assertTrue((wt / 'evolve' / 'mechanism' / 'family_map.md').is_file())
        tmp.cleanup()

    def test_refresh_a8_meta_block(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8')
        cfg_path = wt / 'evolve' / 'config.json'
        existing = json.loads(cfg_path.read_text(encoding='utf-8'))
        existing['baseline'] = {'best_search': 0.7, 'best_b4': 0.5, 'best_lower_ci': 0.5}
        existing['max_rounds'] = 99
        write_json(cfg_path, existing)
        refresh_claude_meta_config(wt)
        refreshed = read_worktree_config(wt)
        tpl = load_arm_config('A8')
        self.assertEqual(refreshed['meta'], tpl['meta'])
        self.assertEqual(refreshed['baseline']['best_search'], 0.7)
        self.assertEqual(refreshed['max_rounds'], 99)
        tmp.cleanup()

    def test_refresh_a8s_meta_block(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8s')
        refresh_claude_meta_config(wt)
        refreshed = read_worktree_config(wt)
        tpl = load_arm_config('A8s')
        self.assertEqual(refreshed['meta'], tpl['meta'])
        tmp.cleanup()

    def test_overlay_a8_session_deep_equals_template(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8')
        config = load_config(wt)
        arm = overlay_claude_meta_session(config, harness_root=ROOT)
        self.assertEqual(arm, 'A8')
        tpl_session = _meta_session_dict(json.loads(A8_CFG.read_text(encoding='utf-8')))
        self.assertEqual(config.meta_session.allowed_tools, tuple(tpl_session['allowed_tools']))
        self.assertEqual(
            config.meta_session.append_system_prompt_file,
            tpl_session['append_system_prompt_file'],
        )
        tmp.cleanup()

    def test_overlay_a8s_session_deep_equals_template(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        wt = _setup_claude_worktree(Path(tmp.name), 'A8s')
        config = load_config(wt)
        arm = overlay_claude_meta_session(config, harness_root=ROOT)
        self.assertEqual(arm, 'A8s')
        tpl_session = _meta_session_dict(json.loads(A8S_CFG.read_text(encoding='utf-8')))
        self.assertEqual(config.meta_session.allowed_tools, tuple(tpl_session['allowed_tools']))
        self.assertIn('a8s_meta_constitution.md', config.meta_session.append_system_prompt_file)
        tmp.cleanup()

    def test_resolve_template_arm_from_ladder_template(self) -> None:
        cfg = {'meta': {'agent': 'claude_cli', 'ladder_template': 'A9', 'strict_self_contained': True}}
        self.assertEqual(resolve_template_arm(cfg, wt_name='A8s'), 'A9')

    def test_resolve_template_arm_from_arm_field(self) -> None:
        cfg = {'arm': 'A9', 'meta': {'agent': 'claude_cli', 'strict_self_contained': True}}
        self.assertEqual(resolve_template_arm(cfg, wt_name='wrong'), 'A9')


if __name__ == '__main__':
    unittest.main(verbosity=2)
