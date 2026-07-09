'''Process-tree teardown for agent subprocess wrappers.'''
from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from evolver.util import agent_subprocess_popen_kwargs, cursor_cli_env, kill_process_tree, wait_or_kill_process_tree


class ProcessTreeTestCase(unittest.TestCase):
    @patch('evolver.util.subprocess.run')
    @patch('evolver.util.os.name', 'nt')
    def test_kill_process_tree_windows_uses_taskkill(self, mock_run) -> None:
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 4242
        kill_process_tree(proc)
        mock_run.assert_called_once_with(
            ['taskkill', '/T', '/F', '/PID', '4242'],
            capture_output=True,
            check=False,
        )

    @patch('evolver.util.os.killpg', create=True)
    @patch('evolver.util.os.getpgid', return_value=99, create=True)
    def test_kill_process_tree_unix_uses_process_group(self, _pgid, mock_killpg) -> None:
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 4242
        with patch('evolver.util.os.name', 'posix'):
            kill_process_tree(proc)
        mock_killpg.assert_called_once()

    def test_kill_process_tree_noop_when_already_exited(self) -> None:
        proc = MagicMock()
        proc.poll.return_value = 0
        with patch('evolver.util.subprocess.run') as mock_run:
            kill_process_tree(proc)
        mock_run.assert_not_called()

    @patch('evolver.util.kill_process_tree')
    def test_wait_or_kill_process_tree_on_hang(self, mock_kill) -> None:
        proc = MagicMock()
        proc.wait.side_effect = [subprocess.TimeoutExpired('cmd', 10), None]
        wait_or_kill_process_tree(proc, timeout=10)
        mock_kill.assert_called_once_with(proc)

    def test_agent_popen_kwargs_unix_starts_new_session(self) -> None:
        if os.name == 'nt':
            self.assertEqual(agent_subprocess_popen_kwargs(), {})
        else:
            self.assertEqual(agent_subprocess_popen_kwargs(), {'start_new_session': True})

    def test_cursor_cli_env_strips_api_key_injects_ide_token(self) -> None:
        base = {'CURSOR_API_KEY': 'crsr_x', 'CURSOR_AUTH_TOKEN': 'stale', 'PATH': '/bin'}
        with patch('evolver.util.load_cursor_ide_access_token', return_value='jwt_bobyard'):
            env = cursor_cli_env(base)
        self.assertNotIn('CURSOR_API_KEY', env)
        self.assertEqual(env['CURSOR_AUTH_TOKEN'], 'jwt_bobyard')
        self.assertEqual(env['PATH'], '/bin')


if __name__ == '__main__':
    unittest.main(verbosity=2)
