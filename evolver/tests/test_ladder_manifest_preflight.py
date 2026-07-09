'''Manifest preflight: init-only writes production manifest spawn can use.'''
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from ladder_lib import (  # noqa: E402
    MANIFEST_PATH,
    RUN_ROOT,
    load_arm_config,
    manifest_spawn_id,
    write_json,
)


class ManifestPreflightTestCase(unittest.TestCase):
    def test_a9_manifest_entry_after_init_only(self) -> None:
        tmp_manifest = tempfile.TemporaryDirectory()
        manifest_file = Path(tmp_manifest.name) / 'manifest.json'
        wt = Path(tmp_manifest.name) / 'worktrees' / 'A9'
        (wt / 'evolve').mkdir(parents=True)
        run_dir = Path(tmp_manifest.name) / 'runs' / 'A9_batch'
        cfg = load_arm_config('A9')
        write_json(wt / 'evolve' / 'config.json', cfg)

        manifest = {
            'batch_id': 'test_batch',
            'arms': {
                'A9': {
                    'arm': 'A9',
                    'replicate': 0,
                    'worktree': str(wt),
                    'run_dir': str(run_dir),
                    'rng_seed': 20260627,
                    'pid': None,
                },
            },
        }
        write_json(manifest_file, manifest)

        loaded = json.loads(manifest_file.read_text(encoding='utf-8'))
        entry = loaded['arms']['A9']
        self.assertEqual(entry['arm'], 'A9')
        self.assertEqual(Path(entry['worktree']), wt)
        self.assertEqual(entry['rng_seed'], 20260627)
        tmp_manifest.cleanup()

    def test_manifest_spawn_id_a9_replicates(self) -> None:
        self.assertEqual(manifest_spawn_id('A9', 0, replicates=3), 'A9@r0')
        self.assertEqual(manifest_spawn_id('A9', 2, replicates=3), 'A9@r2')


if __name__ == '__main__':
    unittest.main(verbosity=2)
