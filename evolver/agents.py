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
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

from .util import (
    agent_subprocess_popen_kwargs,
    claude_meta_env,
    cursor_cli_env,
    kill_process_tree,
    wait_or_kill_process_tree,
)

if TYPE_CHECKING:
    from .config import Config

COMPLETED = 'completed'
ERROR = 'error'
TIMEOUT = 'timeout'
TURN_LIMIT = 'turn_limit'


@dataclass
class AgentContext:
    '''What an inner session is given (bounded; never the full archive).'''

    repo_root: Path
    strategy_rel: str
    prompt: str
    phi: str
    round_idx: int
    parent_id: str | None
    run_dir: Path | None = None

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
    agent_stdout: str = ''
    leak_hits: tuple[str, ...] = field(default_factory=tuple)
    scope_violations: tuple[str, ...] = field(default_factory=tuple)
    meta_invocation: dict[str, Any] | None = None
    usage_reset_at: float | None = None


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
                env=cursor_cli_env(),
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                **agent_subprocess_popen_kwargs(),
            )
        except OSError as exc:
            return AgentResult(status=ERROR, error=f'cursor-agent launch failed: {exc!r}')

        done = threading.Event()
        timed_out = threading.Event()

        def _watchdog() -> None:
            if not done.wait(self.session.wall_timeout_s):
                timed_out.set()
                kill_process_tree(proc)

        watch = threading.Thread(target=_watchdog, daemon=True)
        watch.start()

        tokens = 0
        is_error = False
        summary = ''
        stdout_parts: list[str] = []
        audit_path = (ctx.run_dir / 'agent_tools.jsonl') if ctx.run_dir else None
        audit_file = None
        if audit_path is not None:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_file = open(audit_path, 'a', encoding='utf-8')  # noqa: SIM115
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
                text = self._print_progress(event, audit_file, ctx.repo_root)
                if text:
                    stdout_parts.append(text)
                if event.get('type') == 'result':
                    is_error = bool(event.get('is_error'))
                    summary = str(event.get('result', ''))[:500]
                    tokens = self._tokens(event.get('usage'))
        finally:
            if audit_file is not None:
                audit_file.close()
            done.set()
            wait_or_kill_process_tree(proc)

        if timed_out.is_set():
            return AgentResult(status=TIMEOUT, error='wall timeout', tokens=tokens,
                               agent_stdout=''.join(stdout_parts))
        if is_error or proc.returncode not in (0, None):
            return AgentResult(
                status=ERROR, error=summary or f'exit={proc.returncode}', tokens=tokens,
                agent_stdout=''.join(stdout_parts),
            )
        agent_stdout = ''.join(stdout_parts)
        leak_hits = self._runtime_leak_hits(agent_stdout)
        return AgentResult(
            status=COMPLETED, summary=summary, tokens=tokens,
            agent_stdout=agent_stdout, leak_hits=leak_hits,
        )

    @staticmethod
    def _runtime_leak_hits(stdout: str) -> tuple[str, ...]:
        if not stdout.strip():
            return ()
        from .leak_gate import gate_scan

        return tuple(gate_scan(stdout, ''))

    @staticmethod
    def _audit_tool(event: dict[str, Any], audit_file: Any, repo_root: Path) -> None:
        if audit_file is None:
            return
        etype = event.get('type')
        if etype != 'tool_call' or event.get('subtype') != 'started':
            return
        tc = event.get('tool_call') or {}
        name = next((k for k in tc if k.endswith('ToolCall')), 'tool') if isinstance(tc, dict) else 'tool'
        payload = tc.get(name, {}) if isinstance(tc, dict) else {}
        raw_cmd = ''
        if isinstance(payload, dict):
            raw_cmd = str(payload.get('command') or payload.get('args') or payload.get('path') or '')
        record = {
            'ts': time.time(),
            'tool': name,
            'cwd': str(repo_root),
            'raw': raw_cmd[:2000],
            'parent_traversal': '../' in raw_cmd,
        }
        audit_file.write(json.dumps(record) + '\n')
        audit_file.flush()

    @staticmethod
    def _print_progress(
        event: dict[str, Any],
        audit_file: Any = None,
        repo_root: Path | None = None,
    ) -> str:
        '''Echo assistant text and tool calls; return accumulated assistant text.'''
        text_out = ''
        try:
            etype = event.get('type')
            if etype == 'assistant':
                for block in event.get('message', {}).get('content', []):
                    text = block.get('text') if isinstance(block, dict) else None
                    if block.get('type') == 'text' and text and text.strip():
                        line = f'[cursor-agent] {text.strip()}'
                        print(line, flush=True)
                        text_out += text
            elif etype == 'tool_call' and event.get('subtype') == 'started':
                tc = event.get('tool_call', {})
                name = next((k for k in tc if k.endswith('ToolCall')), 'tool') if isinstance(tc, dict) else 'tool'
                print(f'[cursor-agent] tool: {name}', flush=True)
                if repo_root is not None:
                    CursorCliAgent._audit_tool(event, audit_file, repo_root)
        except Exception:  # noqa: BLE001 - progress printing must never break a run
            pass
        return text_out

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


class ClaudeCliAgent:
    '''Bounded session via local Claude Code CLI (`claude -p`, non-bare).

    Subscription/session auth only — never uses `--bare`. Meta sessions for A8
    use path-scoped dontAsk + allowedTools; cwd is the isolated worktree root.
    '''

    _TURN_LIMIT_MARKERS = (
        'max turns',
        'turn limit',
        'maximum number of turns',
    )

    def __init__(self, config: 'Config', *, session: 'SessionConfig | None' = None) -> None:
        from .config import SessionConfig as _SC

        self.config = config
        self.session = session if session is not None else config.session
        self.model = (self.session.model or 'claude-opus-4-8').strip()
        self.exe = self._resolve_exe()

    @staticmethod
    def _resolve_exe() -> str:
        found = shutil.which('claude')
        if found:
            return found
        return 'claude'

    def _harness_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def _allowed_tools_arg(self, ctx: AgentContext) -> str:
        from .meta_delivery import expand_meta_allowed_tools

        tools = expand_meta_allowed_tools(
            self.session.allowed_tools, ctx.repo_root, ctx.strategy_rel,
        )
        if not tools:
            return ''
        return ','.join(tools)

    def _disallowed_tools_arg(self) -> str:
        from .meta_delivery import expand_meta_disallowed_tools

        tools = expand_meta_disallowed_tools(self.session.disallowed_tools)
        if not tools:
            return ''
        return ','.join(tools)

    def _resolve_settings_path(self, ctx: AgentContext) -> Path | None:
        from .meta_delivery import materialize_meta_settings

        if not self.session.settings_file:
            return None
        return materialize_meta_settings(
            ctx.repo_root, self.session.settings_file, self._harness_root(),
        )

    def _command(self, ctx: AgentContext) -> list[str]:
        base: list[str] = [
            self.exe, '-p',
            '--model', self.model,
            '--output-format', 'stream-json',
            '--verbose',
            '--permission-mode', 'dontAsk',
            '--no-session-persistence',
        ]
        if self.session.effort:
            base += ['--effort', self.session.effort]
        if self.session.max_turns > 0:
            base += ['--max-turns', str(self.session.max_turns)]
        if self.session.max_budget_usd > 0:
            base += ['--max-budget-usd', f'{self.session.max_budget_usd:.2f}']
        tools = self._allowed_tools_arg(ctx)
        if tools:
            base += ['--allowedTools', tools]
        disallowed = self._disallowed_tools_arg()
        if disallowed:
            base += ['--disallowedTools', disallowed]
        settings_path = self._resolve_settings_path(ctx)
        if settings_path is not None:
            base += ['--settings', str(settings_path)]
        elif self.session.settings_file:
            from .util import log
            log(f'  WARN meta settings missing: {self.session.settings_file}')
        if self.session.append_system_prompt_file:
            prompt_path = Path(self.session.append_system_prompt_file)
            if not prompt_path.is_absolute():
                prompt_path = ctx.repo_root / prompt_path
            if prompt_path.exists():
                base += ['--append-system-prompt-file', str(prompt_path)]
        if os.name == 'nt':
            return ['cmd', '/c', *base]
        return base

    @staticmethod
    def _log_meta_command(cmd: list[str]) -> None:
        from .util import log

        if len(cmd) >= 3 and cmd[0] == 'cmd' and cmd[1] == '/c':
            display = cmd[2:]
            wrapper = 'cmd /c'
        else:
            display = cmd
            wrapper = ''
        log('  META command argv:')
        if wrapper:
            log(f'    {wrapper}')
        i = 0
        while i < len(display):
            token = display[i]
            if token.startswith('-') and i + 1 < len(display) and not display[i + 1].startswith('-'):
                log(f'    {token} {display[i + 1]}')
                i += 2
            else:
                log(f'    {token}')
                i += 1
        log(f'  META command (joined): {" ".join(display)}')

    def run(self, ctx: AgentContext) -> AgentResult:
        cmd = self._command(ctx)
        if '--bare' in cmd:
            return AgentResult(status=ERROR, error='ClaudeCliAgent must not use --bare')
        if ctx.parent_id is None:
            self._log_meta_command(cmd)

        meta_invocation = None
        if ctx.parent_id is None:
            from .meta_delivery import meta_command_fingerprint
            meta_invocation = meta_command_fingerprint(cmd)

        popen_kwargs = agent_subprocess_popen_kwargs()
        if ctx.parent_id is None:
            popen_kwargs = {**popen_kwargs, 'env': claude_meta_env()}

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(ctx.repo_root),
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                **popen_kwargs,
            )
        except OSError as exc:
            return AgentResult(status=ERROR, error=f'claude launch failed: {exc!r}')

        done = threading.Event()
        timed_out = threading.Event()

        def _watchdog() -> None:
            if not done.wait(self.session.wall_timeout_s):
                timed_out.set()
                kill_process_tree(proc)

        watch = threading.Thread(target=_watchdog, daemon=True)
        watch.start()

        tokens = 0
        cost = 0.0
        cost_estimated = False
        is_error = False
        summary = ''
        usage_reset_at: float | None = None
        stdout_parts: list[str] = []
        seen_tool_ids: set[str] = set()
        scope_hits: list[str] = []
        strict_meta = ctx.parent_id is None
        audit_name = 'meta_tools.jsonl' if strict_meta else 'agent_tools.jsonl'
        audit_path = (ctx.run_dir / audit_name) if ctx.run_dir else None
        audit_file = None
        if audit_path is not None:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_file = open(audit_path, 'a', encoding='utf-8')  # noqa: SIM115
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
                text = self._print_progress(
                    event, audit_file, ctx.repo_root, seen_tool_ids, scope_hits,
                    strict_meta=strict_meta,
                )
                if text:
                    stdout_parts.append(text)
                if event.get('type') == 'rate_limit_event':
                    info = event.get('rate_limit_info') or {}
                    resets_at = info.get('resetsAt')
                    if isinstance(resets_at, (int, float)) and float(resets_at) > 0:
                        ts = float(resets_at)
                        usage_reset_at = ts if usage_reset_at is None else max(usage_reset_at, ts)
                if event.get('type') == 'result':
                    is_error = bool(event.get('is_error'))
                    summary = str(event.get('result', ''))[:500]
                    tokens = self._tokens(event.get('usage'))
                    parsed_cost = self._cost_usd(event)
                    if parsed_cost is not None:
                        cost = parsed_cost
                    elif self.session.max_budget_usd > 0:
                        cost = self.session.max_budget_usd
                        cost_estimated = True
        finally:
            if audit_file is not None:
                audit_file.close()
            done.set()
            wait_or_kill_process_tree(proc)

        agent_stdout = ''.join(stdout_parts)
        limit_kw = dict(
            tokens=tokens, cost_usd=cost, agent_stdout=agent_stdout,
            meta_invocation=meta_invocation, usage_reset_at=usage_reset_at,
        )
        if timed_out.is_set():
            return AgentResult(status=TIMEOUT, error='wall timeout', **limit_kw)
        if self._is_turn_limit(summary, proc.returncode, is_error):
            return AgentResult(
                status=TURN_LIMIT, error=summary or 'max turns reached', **limit_kw,
            )
        if is_error or proc.returncode not in (0, None):
            return AgentResult(
                status=ERROR, error=summary or f'exit={proc.returncode}', **limit_kw,
            )
        if cost_estimated and cost > 0:
            print(f'[claude] cost estimated from max_budget_usd={cost:.4f}', flush=True)
        leak_hits = self._runtime_leak_hits(agent_stdout)
        return AgentResult(
            status=COMPLETED, summary=summary, tokens=tokens, cost_usd=cost,
            agent_stdout=agent_stdout, leak_hits=leak_hits,
            scope_violations=tuple(scope_hits),
            meta_invocation=meta_invocation, usage_reset_at=usage_reset_at,
        )

    def _is_turn_limit(self, summary: str, returncode: int | None, is_error: bool) -> bool:
        if not is_error and returncode in (0, None):
            return False
        low = summary.lower()
        return any(m in low for m in self._TURN_LIMIT_MARKERS)

    @staticmethod
    def _runtime_leak_hits(stdout: str) -> tuple[str, ...]:
        if not stdout.strip():
            return ()
        from .leak_gate import gate_scan

        return tuple(gate_scan(stdout, ''))

    @staticmethod
    def _cost_usd(event: dict[str, Any]) -> float | None:
        usage = event.get('usage')
        if isinstance(usage, dict):
            for key in ('total_cost_usd', 'cost_usd', 'costUSD'):
                if key in usage and usage[key] is not None:
                    return float(usage[key])
        for key in ('total_cost_usd', 'cost_usd'):
            if key in event and event[key] is not None:
                return float(event[key])
        return None

    @staticmethod
    def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
        if event.get('type') != 'assistant':
            return []
        content = event.get('message', {}).get('content', [])
        if not isinstance(content, list):
            return []
        return [block for block in content if isinstance(block, dict)]

    @staticmethod
    def _tool_raw(tool_name: str, tool_input: Any) -> str:
        if not isinstance(tool_input, dict):
            return str(tool_input)
        for key in (
            'command', 'file_path', 'path', 'pattern', 'query',
            'glob_pattern', 'notebook_path', 'url', 'prompt',
        ):
            val = tool_input.get(key)
            if val:
                return str(val)
        try:
            return json.dumps(tool_input, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(tool_input)

    @staticmethod
    def _audit_tool_use(
        tool_name: str,
        tool_input: Any,
        audit_file: Any,
        repo_root: Path,
        scope_hits: list[str] | None = None,
        *,
        tool_id: str = '',
        strict_meta: bool = False,
    ) -> None:
        if audit_file is None:
            return
        from .meta_delivery import tool_access_violation

        raw = ClaudeCliAgent._tool_raw(tool_name, tool_input)
        parent_traversal = '../' in raw or '/..' in raw or raw.strip().startswith('..')
        violation = tool_access_violation(
            tool_name, raw, repo_root, strict_meta=strict_meta,
        )
        if parent_traversal and violation is None:
            violation = f'parent traversal in {tool_name}: {raw[:120]}'
        if violation and scope_hits is not None:
            scope_hits.append(violation)
        record = {
            'ts': time.time(),
            'tool': tool_name,
            'tool_use_id': tool_id,
            'cwd': str(repo_root.resolve()),
            'raw': raw[:2000],
            'parent_traversal': parent_traversal,
            'scope_violation': violation or '',
        }
        audit_file.write(json.dumps(record) + '\n')
        audit_file.flush()

    @staticmethod
    def _print_progress(
        event: dict[str, Any],
        audit_file: Any = None,
        repo_root: Path | None = None,
        seen_tool_ids: set[str] | None = None,
        scope_hits: list[str] | None = None,
        strict_meta: bool = False,
    ) -> str:
        text_out = ''
        if seen_tool_ids is None:
            seen_tool_ids = set()
        try:
            for block in ClaudeCliAgent._content_blocks(event):
                btype = block.get('type')
                if btype == 'text':
                    text = block.get('text')
                    if text and str(text).strip():
                        line = f'[claude] {str(text).strip()}'
                        print(line, flush=True)
                        text_out += str(text)
                elif btype == 'tool_use':
                    tool_id = str(block.get('id') or '')
                    if tool_id and tool_id in seen_tool_ids:
                        continue
                    if tool_id:
                        seen_tool_ids.add(tool_id)
                    name = str(block.get('name') or 'tool')
                    print(f'[claude] tool: {name}', flush=True)
                    if repo_root is not None:
                        ClaudeCliAgent._audit_tool_use(
                            name,
                            block.get('input') or {},
                            audit_file,
                            repo_root,
                            scope_hits,
                            tool_id=tool_id,
                            strict_meta=strict_meta,
                        )
        except Exception:  # noqa: BLE001
            pass
        return text_out

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
        return int(usage.get('input_tokens', 0) or usage.get('inputTokens', 0) or 0) + \
            int(usage.get('output_tokens', 0) or usage.get('outputTokens', 0) or 0)


def make_cursor_agent(config: 'Config') -> Agent:
    '''Factory for the SDK-based agent (legacy / opt-in via agent="sdk").'''
    return CursorAgent(config)


def make_agent(config: 'Config', *, role: str = 'inner') -> Agent:
    '''Select agent runner from config.agent_kind (inner) or config.meta_agent_kind (meta).

    `cursor_cli` uses LOCAL cursor-agent CLI; `claude_cli` uses `claude -p` (non-bare);
    `sdk` uses cursor_sdk Agent.
    '''
    if role == 'meta':
        kind = (config.meta_agent_kind or config.agent_kind).strip()
        session = config.meta_session
    else:
        kind = config.agent_kind
        session = config.session
    if kind == 'sdk':
        return CursorAgent(config)
    if kind == 'claude_cli':
        return ClaudeCliAgent(config, session=session)
    return CursorCliAgent(config)


def make_meta_agent(config: 'Config') -> Agent:
    return make_agent(config, role='meta')
