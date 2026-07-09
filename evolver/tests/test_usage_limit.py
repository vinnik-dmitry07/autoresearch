'''Tests for usage-limit pause/resume behavior.'''
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from evolver.agents import COMPLETED, ERROR, AgentContext, AgentResult, StubAgent
from evolver.usage_limit import (
    CURSOR_AUTO_STOP_MARKER,
    is_cursor_auto_stop_flag,
    is_session_limit_error,
    parse_billing_cycle_end_unix,
    parse_reset_unix_from_error,
    parse_threshold_from_stop_flag,
    session_limit_message,
    wait_for_cursor_auto_reset,
    wait_for_usage_reset,
    wait_until_unix,
)
from evolver.tests.test_phase0 import build_loop, behavior_valid_edit
from evolver.tests.stubs import StubEvaluator, make_fixture


class UsageLimitParseTestCase(unittest.TestCase):
    def test_session_limit_markers(self) -> None:
        self.assertTrue(is_session_limit_error('Hit session limit; resets 12:10am PT'))
        self.assertTrue(is_session_limit_error(
            "You've hit your session limit · resets 8pm (America/Los_Angeles)",
        ))
        self.assertFalse(is_session_limit_error('wall timeout'))

    def test_parse_reset_8pm_with_timezone(self) -> None:
        from zoneinfo import ZoneInfo

        now = datetime(2026, 7, 8, 15, 0, tzinfo=ZoneInfo('America/Los_Angeles'))
        ts = parse_reset_unix_from_error(
            "You've hit your session limit · resets 8pm (America/Los_Angeles)",
            now=now,
        )
        self.assertIsNotNone(ts)
        reset = datetime.fromtimestamp(ts, tz=ZoneInfo('America/Los_Angeles'))
        self.assertEqual((reset.hour, reset.minute), (20, 0))
        self.assertEqual(reset.date(), now.date())

    def test_cursor_auto_stop_flag(self) -> None:
        text = f'{CURSOR_AUTO_STOP_MARKER}\nthreshold=75.0\n'
        self.assertTrue(is_cursor_auto_stop_flag(text))
        self.assertEqual(parse_threshold_from_stop_flag(text), 75.0)

    def test_parse_reset_time(self) -> None:
        now = datetime.now().astimezone().replace(hour=15, minute=0, second=0, microsecond=0)
        ts = parse_reset_unix_from_error('session limit resets 12:10am', now=now)
        self.assertIsNotNone(ts)
        reset = datetime.fromtimestamp(ts).astimezone()
        self.assertEqual((reset.hour, reset.minute), (0, 10))


class UsageLimitWaitTestCase(unittest.TestCase):
    def test_wait_until_unix_short(self) -> None:
        with mock.patch('evolver.usage_limit.time.time', side_effect=[1000.0, 1000.0, 1100.0]), \
                mock.patch('evolver.usage_limit.time.sleep') as sleep:
            wait_until_unix(1030.0, poll_interval_s=60.0)
        self.assertGreaterEqual(sleep.call_count, 1)

    def test_wait_for_cursor_auto_reset(self) -> None:
        seq = [
            SimpleNamespace(auto_percent=85.0, api_percent=None),
            SimpleNamespace(auto_percent=79.0, api_percent=None),
        ]
        with mock.patch('evolver.usage_limit.time.sleep'), \
                mock.patch('evolver.usage_limit.log'):
            wait_for_cursor_auto_reset(
                80.0,
                poll_interval_s=1.0,
                fetch_fn=lambda: seq.pop(0),
            )
        self.assertFalse(seq)

    def test_parse_billing_cycle_end(self) -> None:
        ts = parse_billing_cycle_end_unix('2026-07-24T21:17:52.000Z')
        self.assertIsNotNone(ts)
        self.assertGreater(ts, 1_700_000_000)

    def test_session_limit_message(self) -> None:
        msg = session_limit_message('', '', "You've hit your session limit · resets 8pm")
        self.assertIn('session limit', msg.lower())

    def test_wait_for_usage_reset_parses_8pm(self) -> None:
        with mock.patch('evolver.usage_limit.wait_until_unix') as wait_unix, \
                mock.patch('evolver.usage_limit._default_fetch_usage') as fetch:
            fetch.return_value = SimpleNamespace(
                auto_percent=90.0, api_percent=100.0, billing_cycle_end=None,
            )
            wait_for_usage_reset(
                error="You've hit your session limit · resets 8pm (America/Los_Angeles)",
            )
        wait_unix.assert_called_once()


class LoopUsageWaitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.repo, self.run_dir, _base = make_fixture(tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cursor_auto_stop_does_not_terminate(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(), max_rounds=2,
        )
        stop = config.paths.run_dir / 'stop.flag'
        stop.write_text(
            f'{CURSOR_AUTO_STOP_MARKER}\nthreshold=80.0\n', encoding='utf-8',
        )
        with mock.patch('evolver.loop.pause_for_cursor_auto_stop_flag') as pause:
            loop.run()
        pause.assert_called()
        self.assertGreater(loop.state['round'], 0)
        self.assertTrue(loop.state['finished'])

    def test_operator_stop_still_terminates(self) -> None:
        agent = StubAgent(behavior_valid_edit())
        config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(), max_rounds=5,
        )
        (config.paths.run_dir / 'stop.flag').write_text('stop requested by operator\n', encoding='utf-8')
        loop.run()
        self.assertEqual(loop.state['round'], 0)


class AgentUsageRetryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.repo, self.run_dir, _base = make_fixture(tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_run_agent_with_usage_wait_retries(self) -> None:
        calls = {'n': 0}

        def behavior(ctx: AgentContext) -> AgentResult:
            calls['n'] += 1
            if calls['n'] == 1:
                return AgentResult(
                    status=ERROR,
                    error='session limit reached; resets 12:10am',
                    usage_reset_at=100.0,
                )
            return AgentResult(status=COMPLETED, summary='ok')

        agent = StubAgent(behavior)
        _config, loop = build_loop(
            self.repo, self.run_dir, agent=agent, evaluator=StubEvaluator(), max_rounds=1,
        )
        ctx = AgentContext(
            repo_root=self.repo,
            strategy_rel='durak/src/strategy_heuristic.cpp',
            prompt='x',
            phi='',
            round_idx=0,
            parent_id='candidate_0000',
            run_dir=self.run_dir,
        )
        with mock.patch('evolver.loop.wait_for_usage_reset') as wait_reset:
            result = loop._run_agent_with_usage_wait(agent, ctx)
        self.assertEqual(result.status, COMPLETED)
        self.assertEqual(calls['n'], 2)
        wait_reset.assert_called_once()


if __name__ == '__main__':
    unittest.main()
