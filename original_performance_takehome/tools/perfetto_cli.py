"""Install Perfetto and open a Chrome/Perfetto trace from the CLI."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import socketserver
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

VERSION = 'v57.2'
UI_URL = f'https://github.com/google/perfetto/releases/download/{VERSION}/perfetto-ui.zip'
SHELL_URL = (
    'https://commondatastorage.googleapis.com/perfetto-luci-artifacts/'
    f'{VERSION}/windows-amd64/trace_processor_shell.exe'
)
SHELL_SHA256 = '100334b6091596fbc97f872556849a5747bf47a7f7190c485ba8cea8d2409c7b'
REMOTE_UI = 'https://ui.perfetto.dev'
TRACE_PORT = 9001
UI_PORT = 10000

HOME = Path.home() / '.local' / 'share' / 'perfetto'
DOWNLOADS = HOME / 'downloads'
UI_DIR = HOME / 'ui'
SHELL_PATH = HOME / 'prebuilts' / 'trace_processor_shell.exe'
ROOT = Path(__file__).resolve().parents[1]


def _print(msg: str) -> None:
    print(msg, flush=True)


def _download(url: str, dest: Path, expected_sha256: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.tmp')
    _print(f'downloading {url}')
    last_pct = [-1]

    def hook(blocks: int, block_size: int, total: int) -> None:
        done = blocks * block_size
        if total <= 0:
            sys.stdout.write(f'\r  {done / 1e6:.1f} MB')
            sys.stdout.flush()
            return
        done = min(done, total)
        pct = int(100.0 * done / total)
        if pct == last_pct[0]:
            return
        last_pct[0] = pct
        sys.stdout.write(f'\r  {pct:5.1f}%  {done / 1e6:.1f}/{total / 1e6:.1f} MB')
        sys.stdout.flush()

    urllib.request.urlretrieve(url, tmp, hook)
    sys.stdout.write('\n')
    sys.stdout.flush()
    if expected_sha256:
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if digest != expected_sha256:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f'checksum mismatch for {dest.name}: {digest}')
    tmp.replace(dest)


def _extract_ui(zip_path: Path, dest: Path) -> None:
    if dest.exists():
        for child in sorted(dest.rglob('*'), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
    dest.mkdir(parents=True, exist_ok=True)
    _print(f'extracting {zip_path.name}')
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for i, name in enumerate(names, 1):
            zf.extract(name, dest)
            if i == 1 or i == len(names) or i % 50 == 0:
                _print(f'  {i}/{len(names)} files')
    index = dest / 'index.html'
    if index.is_file():
        return
    found = list(dest.rglob('index.html'))
    if not found:
        raise RuntimeError(f'no index.html in {zip_path}')
    root = found[0].parent
    if root == dest:
        return
    for item in root.iterdir():
        target = dest / item.name
        if not target.exists():
            item.rename(target)


def install(force: bool = False) -> None:
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    ui_zip = DOWNLOADS / 'perfetto-ui.zip'
    if force or not ui_zip.is_file():
        _download(UI_URL, ui_zip)
    else:
        _print(f'using cached {ui_zip}')
    if force or not (UI_DIR / 'index.html').is_file():
        _extract_ui(ui_zip, UI_DIR)
    else:
        _print(f'using existing UI at {UI_DIR}')

    if force or not SHELL_PATH.is_file():
        _download(SHELL_URL, SHELL_PATH, SHELL_SHA256)
    else:
        _print(f'using existing {SHELL_PATH}')
    _install_path_shim()
    _print(f'Perfetto {VERSION} ready')
    _print(f'  UI     {UI_DIR}')
    _print(f'  shell  {SHELL_PATH}')


def _install_path_shim() -> None:
    scripts = Path(sys.executable).resolve().parent / 'Scripts'
    if not scripts.is_dir():
        scripts = Path(sys.executable).resolve().parent
    shim = scripts / 'perfetto.bat'
    cli = Path(__file__).resolve()
    body = f'@echo off\r\n"{sys.executable}" -u "{cli}" %*\r\n'
    if shim.is_file() and shim.read_text(encoding='utf-8') == body:
        _print(f'PATH shim already at {shim}')
        return
    shim.write_text(body, encoding='utf-8')
    _print(f'installed CLI shim {shim}')


def _resolve_trace(path: str | None) -> Path:
    if path:
        cand = Path(path)
    else:
        cand = Path('trace.json')
        if not cand.is_file():
            cand = ROOT / 'trace.json'
    cand = cand.resolve()
    if not cand.is_file():
        raise FileNotFoundError(
            f'trace not found: {cand}\n'
            'Generate one with: python perf_takehome.py Tests.test_kernel_trace'
        )
    return cand


class _TraceHandler(http.server.BaseHTTPRequestHandler):
    expected_name = 'trace.json'
    trace_path: Path = Path('trace.json')

    def log_message(self, fmt: str, *args) -> None:
        _print(f'  [trace] {self.address_string()} {fmt % args}')

    def end_headers(self) -> None:
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_GET(self) -> None:
        name = urllib.parse.unquote(self.path.lstrip('/').split('?', 1)[0])
        if name != self.expected_name:
            self.send_error(404, 'File not found')
            return
        data = self.trace_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        self.send_error(404, 'File not found')


class _UiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        _print(f'  [ui] {self.address_string()} {fmt % args}')

    def end_headers(self) -> None:
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        rel = parsed.path.lstrip('/')
        if rel == '' or rel.endswith('/'):
            self.path = '/index.html'
        elif not (UI_DIR / rel).is_file() and '.' not in Path(rel).name:
            self.path = '/index.html'
        return super().do_GET()


def _local_ui_origin() -> str:
    versions = sorted(
        p.name
        for p in UI_DIR.iterdir()
        if p.is_dir() and (p / 'index.html').is_file()
    )
    if versions:
        return f'http://127.0.0.1:{UI_PORT}/{versions[-1]}'
    return f'http://127.0.0.1:{UI_PORT}'


def _serve(handler, host: str, port: int) -> socketserver.ThreadingTCPServer:
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def open_trace_httpd(trace: Path, *, no_browser: bool) -> int:
    if not (UI_DIR / 'index.html').is_file() or not SHELL_PATH.is_file():
        _print('Perfetto bits missing; installing')
        install()
    ui_httpd = _serve(_UiHandler, '127.0.0.1', UI_PORT)
    cmd = [
        str(SHELL_PATH),
        'server',
        'http',
        str(trace),
        '--port',
        str(TRACE_PORT),
        '--additional-cors-origins',
        f'http://127.0.0.1:{UI_PORT}',
    ]
    _print(' '.join(cmd))
    proc = subprocess.Popen(cmd)
    address = f'{_local_ui_origin()}/'
    _print(f'native TP http://127.0.0.1:{TRACE_PORT}  UI {address}')
    if not no_browser:
        webbrowser.open_new_tab(address)
    _print('serving until Ctrl+C')
    try:
        proc.wait()
    except KeyboardInterrupt:
        _print('\nstopped')
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        ui_httpd.shutdown()
    return 0


def open_trace(trace: Path, *, remote: bool, no_browser: bool, httpd: bool = False) -> int:
    if httpd and not remote:
        return open_trace_httpd(trace, no_browser=no_browser)
    if not remote and not (UI_DIR / 'index.html').is_file():
        _print('local UI missing; installing')
        install()
    fname = trace.name
    _TraceHandler.expected_name = fname
    _TraceHandler.trace_path = trace
    trace_httpd = _serve(_TraceHandler, '127.0.0.1', TRACE_PORT)
    ui_httpd = None
    trace_url = f'http://127.0.0.1:{TRACE_PORT}/{urllib.parse.quote(fname)}'
    if remote:
        origin = REMOTE_UI
    else:
        ui_httpd = _serve(_UiHandler, '127.0.0.1', UI_PORT)
        origin = _local_ui_origin()
    address = f'{origin}/#!/?url={trace_url}&referrer=open_trace_in_ui'
    _print(f'opening {trace}')
    _print(address)
    if not no_browser:
        webbrowser.open_new_tab(address)
    _print('serving until Ctrl+C')
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        _print('\nstopped')
    finally:
        trace_httpd.shutdown()
        if ui_httpd is not None:
            ui_httpd.shutdown()
    return 0


def run_sql(trace: Path, extra: list[str]) -> int:
    if not SHELL_PATH.is_file():
        install()
    commands = {
        'query',
        'interactive',
        'server',
        'summarize',
        'export',
        'metrics',
        'convert',
    }
    if not extra:
        cmd = [str(SHELL_PATH), 'interactive', str(trace)]
    elif extra[0] in commands:
        cmd = [str(SHELL_PATH), extra[0], str(trace), *extra[1:]]
    else:
        cmd = [str(SHELL_PATH), 'query', str(trace), ' '.join(extra)]
    _print(' '.join(cmd))
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='perfetto',
        description='Open a trace.json in Perfetto UI, or query it with trace_processor.',
    )
    parser.add_argument('trace', nargs='?', help='trace file (default: ./trace.json)')
    parser.add_argument('--install', action='store_true', help='download UI + trace_processor')
    parser.add_argument('--force', action='store_true', help='re-download even if cached')
    parser.add_argument('--remote', action='store_true', help='use https://ui.perfetto.dev')
    parser.add_argument(
        '--httpd',
        action='store_true',
        help='parse the trace with native trace_processor (faster than WASM)',
    )
    parser.add_argument('--sql', action='store_true', help='open trace_processor SQL shell')
    parser.add_argument('-n', '--no-open-browser', action='store_true')
    args, extra = parser.parse_known_args(argv)
    if extra and extra[0] == '--':
        extra = extra[1:]

    if args.install or args.force:
        install(force=args.force)
        if args.trace is None and not args.sql:
            return 0
    try:
        trace = _resolve_trace(args.trace)
    except FileNotFoundError as exc:
        _print(str(exc))
        return 1
    if args.sql:
        return run_sql(trace, extra)
    if extra:
        _print(f'unknown arguments: {" ".join(extra)}')
        return 2
    return open_trace(
        trace, remote=args.remote, no_browser=args.no_open_browser, httpd=args.httpd
    )


if __name__ == '__main__':
    raise SystemExit(main())
