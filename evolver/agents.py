'''Agent interface + StubAgent (Phase 0). The real CursorAgent is added in Phase 1.

The agent is a bounded, STATELESS patch generator: it edits the allowlist file in a
restored sandbox and returns. It has zero loop/stop/score authority. A `done` flag
(DONE/PLATEAU) ends only its own session; the harness ignores it for outer control.
'''
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from .config import Config

COMPLETED = 'completed'
ERROR = 'error'
TIMEOUT = 'timeout'


@dataclass
class AgentContext:
    '''What an inner session is given (bounded; never the full archive).'''

    repo_root: Path
    strategy_rel: str
    prompt: str
    phi: str
    round_idx: int
    parent_id: str | None

    @property
    def strategy_path(self) -> Path:
        return self.repo_root / self.strategy_rel


@dataclass
class AgentResult:
    '''Outcome of one bounded inner session.'''

    status: str = COMPLETED
    summary: str = ''
    error: str = ''
    tokens: int = 0
    cost_usd: float = 0.0
    done: bool = False


class Agent(Protocol):
    '''Interface the loop depends on.'''

    def run(self, ctx: AgentContext) -> AgentResult:
        ...


class StubAgent:
    '''Scriptable agent for Phase-0 proofs (no Cursor/API calls).

    `behavior(ctx) -> AgentResult` performs on-disk edits and returns a result. A
    behavior may raise to simulate a crash; the loop must catch it and mark the
    candidate invalid without dying.
    '''

    def __init__(self, behavior: Callable[[AgentContext], AgentResult]) -> None:
        self.behavior = behavior
        self.calls = 0

    def run(self, ctx: AgentContext) -> AgentResult:
        self.calls += 1
        return self.behavior(ctx)


# --- behavior helpers (used by tests / dry runs) ----------------------------------

def append_line(ctx: AgentContext, line: str) -> None:
    '''Append a comment line to the strategy file (a minimal legal edit).'''
    path = ctx.strategy_path
    text = path.read_text(encoding='utf-8')
    path.write_text(text + f'\n// {line}\n', encoding='utf-8')


def behavior_valid_edit(tag: str = 'edit') -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        append_line(ctx, f'stub {tag} round={ctx.round_idx} parent={ctx.parent_id}')
        return AgentResult(status=COMPLETED, summary=f'valid {tag}')
    return _b


def behavior_done_text() -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        append_line(ctx, 'stub says PLATEAU / DONE but still submits a candidate')
        return AgentResult(status=COMPLETED, summary='DONE/PLATEAU', done=True)
    return _b


def behavior_illegal_edit(locked_rel: str) -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        append_line(ctx, 'stub legal edit')
        locked = ctx.repo_root / locked_rel
        locked.parent.mkdir(parents=True, exist_ok=True)
        locked.write_text((locked.read_text(encoding='utf-8') if locked.exists() else '') + '\n// HACKED\n', encoding='utf-8')
        return AgentResult(status=COMPLETED, summary='also tried an illegal edit')
    return _b


def behavior_write_scores() -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        append_line(ctx, 'stub legal edit')
        (ctx.repo_root / 'scores.json').write_text('{"search_score": 0.999}', encoding='utf-8')
        (ctx.repo_root / 'results.tsv').write_text('FAKE\tBEST\t9.99999\n', encoding='utf-8')
        return AgentResult(status=COMPLETED, summary='tried to self-score')
    return _b


def behavior_crash() -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        append_line(ctx, 'stub partial edit before crash')
        raise RuntimeError('stub crash')
    return _b


def behavior_timeout() -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        return AgentResult(status=TIMEOUT, error='stub timeout')
    return _b


def behavior_empty() -> Callable[[AgentContext], AgentResult]:
    def _b(ctx: AgentContext) -> AgentResult:
        return AgentResult(status=COMPLETED, summary='no edit made')
    return _b


# --- real Cursor agent (Phase 1) --------------------------------------------------

class CursorAgent:
    '''Bounded inner session via the Cursor SDK (local runtime, cwd = repo).

    The agent edits the allowlist file only via the prompt contract; ANY out-of-scope
    edit is mechanically discarded by the harness reset afterwards, so tool safety is
    defense-in-depth, not the primary guard. A wall-timeout watchdog cancels a hung
    run; a single bare-text nudge is sent if the first turn changed nothing. The agent
    has ZERO stop/score authority: a DONE/PLATEAU only ends its own session.
    '''

    def __init__(self, config: 'Config') -> None:
        self.config = config
        self.session = config.session
        self.api_key = os.environ.get('CURSOR_API_KEY')
        if not self.api_key:
            raise RuntimeError('CURSOR_API_KEY is not set; required for the real CursorAgent.')

    def _import_sdk(self) -> tuple[Any, Any, Any]:
        from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions  # type: ignore
        return Agent, CursorAgentError, LocalAgentOptions

    def _local_options(self, LocalAgentOptions: Any) -> Any:
        import inspect

        kwargs: dict[str, Any] = {'cwd': str(self.config.repo_root)}
        params = inspect.signature(LocalAgentOptions).parameters
        if 'setting_sources' in params:
            kwargs['setting_sources'] = []  # inline-only config; no ambient settings
        return LocalAgentOptions(**{k: v for k, v in kwargs.items() if k in params})

    def run(self, ctx: AgentContext) -> AgentResult:
        try:
            Agent, CursorAgentError, LocalAgentOptions = self._import_sdk()
        except ImportError as exc:
            return AgentResult(status=ERROR, error=f'cursor-sdk not installed: {exc!r}')

        before = ctx.strategy_path.read_text(encoding='utf-8') if ctx.strategy_path.exists() else ''
        local = self._local_options(LocalAgentOptions)
        tokens = 0
        cost = 0.0
        try:
            with Agent.create(model=self.session.model, api_key=self.api_key, local=local) as agent:
                result, tokens, cost = self._send_with_timeout(agent, ctx.prompt)
                after = ctx.strategy_path.read_text(encoding='utf-8') if ctx.strategy_path.exists() else ''
                if result == TIMEOUT:
                    return AgentResult(status=TIMEOUT, error='wall timeout', tokens=tokens, cost_usd=cost)
                if result == ERROR:
                    return AgentResult(status=ERROR, error='run status=error', tokens=tokens, cost_usd=cost)
                if after == before:  # one bare-text nudge, then accept whatever happens
                    nudge = (
                        'You have not edited the strategy file yet. Make ONE concrete change to '
                        f'{ctx.strategy_rel} now, or explain in a comment why no change is safe.'
                    )
                    result, t2, c2 = self._send_with_timeout(agent, nudge)
                    tokens += t2
                    cost += c2
                return AgentResult(status=COMPLETED, summary='cursor session complete', tokens=tokens, cost_usd=cost)
        except CursorAgentError as exc:  # never started: auth/config/network
            return AgentResult(status=ERROR, error=f'CursorAgentError: {exc!r}', tokens=tokens, cost_usd=cost)
        except Exception as exc:  # noqa: BLE001 - any session failure -> invalid candidate
            return AgentResult(status=ERROR, error=f'session error: {exc!r}', tokens=tokens, cost_usd=cost)

    def _send_with_timeout(self, agent: Any, prompt: str) -> tuple[str, int, float]:
        '''Send one prompt with a wall-timeout watchdog. Returns (outcome, tokens, cost).'''
        run = agent.send(prompt)
        cancelled = threading.Event()

        def _watchdog() -> None:
            if not cancelled.wait(self.session.wall_timeout_s):
                try:
                    if run.supports('cancel'):
                        run.cancel()
                except Exception:  # noqa: BLE001
                    pass

        watch = threading.Thread(target=_watchdog, daemon=True)
        watch.start()
        timed_out = False
        deadline = time.monotonic() + self.session.wall_timeout_s
        try:
            for message in run.messages():
                self._print_text(message)
                if time.monotonic() > deadline:
                    timed_out = True
                    try:
                        if run.supports('cancel'):
                            run.cancel()
                    except Exception:  # noqa: BLE001
                        pass
                    break
        finally:
            cancelled.set()
        result = run.wait()
        tokens, cost = self._usage(result)
        status = getattr(result, 'status', 'finished')
        if timed_out:
            return TIMEOUT, tokens, cost
        if status == 'error':
            return ERROR, tokens, cost
        return COMPLETED, tokens, cost

    @staticmethod
    def _print_text(message: Any) -> None:
        try:
            if getattr(message, 'type', None) == 'assistant':
                for block in message.message.content:
                    if getattr(block, 'type', None) == 'text':
                        print(block.text, end='', flush=True)
        except Exception:  # noqa: BLE001 - progress printing must never break a run
            pass

    @staticmethod
    def _usage(result: Any) -> tuple[int, float]:
        usage = getattr(result, 'usage', None)
        tokens = 0
        cost = 0.0
        if usage is not None:
            tokens = int(getattr(usage, 'total_tokens', 0) or 0)
            cost = float(getattr(usage, 'cost_usd', 0.0) or 0.0)
        return tokens, cost


class CursorCliAgent:
    '''Bounded inner session via the LOCAL Cursor Agent CLI (`cursor-agent`).

    The no-SDK runner: it shells out to the locally-installed `cursor-agent` in
    headless print mode (`-p --force --trust`), model `auto` by default, feeding the
    bounded prompt on stdin and editing the allowlist file in cwd=repo_root. Any
    out-of-scope edit is mechanically discarded by the harness reset afterwards, so
    tool access is defense-in-depth, not the primary guard. A wall-timeout watchdog
    kills a hung run. The agent has ZERO stop/score authority: a DONE/PLATEAU only
    ends its own session; the harness owns termination.
    '''

    def __init__(self, config: 'Config') -> None:
        self.config = config
        self.session = config.session
        self.model = (self.session.model or 'auto').strip() or 'auto'
        self.exe = self._resolve_exe()

    @staticmethod
    def _resolve_exe() -> str:
        '''Find cursor-agent on PATH, else the default Windows install location.'''
        found = shutil.which('cursor-agent')
        if found:
            return found
        local = os.environ.get('LOCALAPPDATA')
        if local:
            candidate = Path(local) / 'cursor-agent' / 'cursor-agent.cmd'
            if candidate.exists():
                return str(candidate)
        return 'cursor-agent'

    def _command(self, ctx: AgentContext) -> list[str]:
        base = [
            self.exe, '-p', '--force', '--trust',
            '--output-format', 'stream-json',
            '--model', self.model,
            '--workspace', str(ctx.repo_root),
        ]
        # A .cmd/.bat launcher must be run through cmd.exe on Windows.
        if os.name == 'nt':
            return ['cmd', '/c', *base]
        return base

    def run(self, ctx: AgentContext) -> AgentResult:
        try:
            proc = subprocess.Popen(
                self._command(ctx),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ctx.repo_root),
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
            )
        except OSError as exc:
            return AgentResult(status=ERROR, error=f'cursor-agent launch failed: {exc!r}')

        done = threading.Event()
        timed_out = threading.Event()

        def _watchdog() -> None:
            if not done.wait(self.session.wall_timeout_s):
                timed_out.set()
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass

        watch = threading.Thread(target=_watchdog, daemon=True)
        watch.start()

        tokens = 0
        is_error = False
        summary = ''
        try:
            if proc.stdin is not None:
                try:
                    proc.stdin.write(ctx.prompt)
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            assert proc.stdout is not None
            for line in proc.stdout:
                event = self._parse(line)
                if event is None:
                    continue
                self._print_progress(event)
                if event.get('type') == 'result':
                    is_error = bool(event.get('is_error'))
                    summary = str(event.get('result', ''))[:500]
                    tokens = self._tokens(event.get('usage'))
        finally:
            done.set()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass

        if timed_out.is_set():
            return AgentResult(status=TIMEOUT, error='wall timeout', tokens=tokens)
        if is_error or proc.returncode not in (0, None):
            return AgentResult(
                status=ERROR, error=summary or f'exit={proc.returncode}', tokens=tokens,
            )
        return AgentResult(status=COMPLETED, summary=summary, tokens=tokens)

    @staticmethod
    def _parse(line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line or line[0] != '{':
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None

    @staticmethod
    def _tokens(usage: Any) -> int:
        if not isinstance(usage, dict):
            return 0
        return int(usage.get('inputTokens', 0) or 0) + int(usage.get('outputTokens', 0) or 0)

    @staticmethod
    def _print_progress(event: dict[str, Any]) -> None:
        '''Echo assistant text and tool calls so the long session shows progress.'''
        try:
            etype = event.get('type')
            if etype == 'assistant':
                for block in event.get('message', {}).get('content', []):
                    text = block.get('text') if isinstance(block, dict) else None
                    if block.get('type') == 'text' and text and text.strip():
                        print(f'[cursor-agent] {text.strip()}', flush=True)
            elif etype == 'tool_call' and event.get('subtype') == 'started':
                tc = event.get('tool_call', {})
                name = next((k for k in tc if k.endswith('ToolCall')), 'tool') if isinstance(tc, dict) else 'tool'
                print(f'[cursor-agent] tool: {name}', flush=True)
        except Exception:  # noqa: BLE001 - progress printing must never break a run
            pass


def make_cursor_agent(config: 'Config') -> Agent:
    '''Factory for the SDK-based agent (legacy / opt-in via agent="sdk").'''
    return CursorAgent(config)


def make_agent(config: 'Config') -> Agent:
    '''Select the inner agent runner from config.agent_kind (default: cursor_cli).

    `cursor_cli` uses the LOCAL cursor-agent CLI (no cursor-sdk dependency); `sdk`
    uses the cursor_sdk Agent. The CLI is the default so a run never imports the SDK.
    '''
    kind = getattr(config, 'agent_kind', 'cursor_cli')
    if kind == 'sdk':
        return CursorAgent(config)
    return CursorCliAgent(config)
