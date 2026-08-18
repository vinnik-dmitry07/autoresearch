"""Score-integrity audit from _last_profile.json or a fresh profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from check import FULL, LAST_PROF, SMOKE, _print_audit, run_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Score integrity audit')
    parser.add_argument('--run', action='store_true', help='profile now instead of last dump')
    parser.add_argument('--smoke', action='store_true', help='3/2/8 when used with --run')
    args = parser.parse_args(argv)
    print('score audit', flush=True)
    prof = None
    if args.run:
        prof = run_profile(*(SMOKE if args.smoke else FULL))
    elif LAST_PROF.is_file():
        prof = json.loads(LAST_PROF.read_text(encoding='utf-8'))
        print(f'  loaded {LAST_PROF.name}', flush=True)
    else:
        print('  no _last_profile.json; pass --run', flush=True)
        return 2
    _print_audit(prof)
    integ = (prof or {}).get('integrity') or {}
    if integ.get('suspect_cheat') or integ.get('suspect_skip_hash'):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
