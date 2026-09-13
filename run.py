"""Portable first-run installer and launcher. Python 3.10+; Node 22.13+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def load_env():
    path = ROOT / '.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.strip().replace('_', '').isalnum():
            raise ValueError('Invalid .env entry')
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build():
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not node or not npm:
        raise RuntimeError('Install Node.js 22.13+ (includes npm), then run this command again.')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if tuple(map(int, version.lstrip('v').split('.')[:3])) < (22, 13, 0):
        raise RuntimeError('Node.js 22.13+ is required; found ' + version)
    fingerprint = hashlib.sha256((ROOT / 'package-lock.json').read_bytes()).hexdigest()
    stamp = ROOT / 'node_modules/.tibo-lock'
    if not stamp.exists() or stamp.read_text() != fingerprint:
        subprocess.run([npm, 'ci'], cwd=ROOT, check=True)
        stamp.write_text(fingerprint)
    subprocess.run([npm, 'run', 'build'], cwd=ROOT, check=True)


def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10+ is required.')
    os.chdir(ROOT)
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-build', action='store_true', help='Use an existing dist/client build')
    parser.add_argument('--live', action='store_true', help='Poll public X sources; disabled by default')
    parser.add_argument('--capture', action='store_true', help='Capture new X post images (requires optional dependencies)')
    parser.add_argument('--translate', action='store_true', help='Legacy translation provider; requires --live')
    parser.add_argument('--ai', action='store_true', help='Capture public X posts and analyze with your authenticated Codex CLI (enables --live and --capture)')
    parser.add_argument('--host', default=os.getenv('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8080')))
    parser.add_argument('--state', type=Path, default=Path(os.getenv('DATA_DIR', '.data')))
    args = parser.parse_args()
    if not args.no_build:
        build()
    if not (ROOT / 'dist/client/radar/index.html').is_file():
        raise RuntimeError('No web build found. Run without --no-build first.')
    args.live = args.live or os.getenv('LIVE_COLLECTION') == '1'
    args.capture = args.capture or os.getenv('CAPTURE_POSTS') == '1'
    args.translate = args.translate or os.getenv('TRANSLATE_POSTS') == '1'
    args.ai = args.ai or os.getenv('AI_ANALYSIS') == '1'
    if args.ai:
        if args.translate:
            raise RuntimeError('--ai already translates with Codex; disable --translate / TRANSLATE_POSTS.')
        args.live = args.capture = True
    if (args.capture or args.translate) and not args.live:
        raise RuntimeError('--capture and --translate require --live.')
    if args.capture:
        import importlib.util
        if not all(importlib.util.find_spec(name) for name in ('PIL', 'playwright')):
            raise RuntimeError('Run: python -m pip install -r requirements-capture.txt; python -m playwright install chromium')
    sys.path.insert(0, str(ROOT / 'ops'))
    if args.ai:
        from ai_analysis import executable_command, AnalysisError
        from ai_config import bounded_int
        try:
            executable_command(os.getenv('CODEX_EXECUTABLE', 'codex'))
        except AnalysisError as error:
            raise RuntimeError('Codex CLI not found. Install the official CLI, log in as this system user, then retry --ai.') from error
        for name, default, low, high in [('AI_MAX_JOBS', 3, 1, 20), ('AI_TIMEOUT_SECONDS', 150, 5, 300), ('AI_BUDGET_SECONDS', 240, 5, 1800)]:
            bounded_int(name, default, low, high)
    from server import serve
    serve(ROOT, args)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped.')
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Startup failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
