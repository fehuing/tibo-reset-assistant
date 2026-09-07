"""Same-origin web + JSON API. Only explicit public paths are served."""
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import unquote, urlsplit

import reactions
from reactions import ReactionHandler, ReactionServer, ReactionStore, RateLimiter
from watch_votes import WatchStore
from collector import atomic_json, collect, read_json
from reset_watch import collect_watch


def initialize(root, state):
    state.mkdir(parents=True, exist_ok=True)
    # Existing data and vote counts are never reset on restart or upgrade.
    for source in (root / 'sample-data').rglob('*'):
        if source.is_file():
            dest = state / source.relative_to(root / 'sample-data')
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)


def poll(state, stop, args):
    interval = max(120, int(os.getenv('POLL_SECONDS', '120')))
    while not stop.is_set():
        try:
            collect(state / 'data.json', state / 'source-cache.json', allow_fallback=os.getenv('ALLOW_REFERENCE_FALLBACK') == '1')
            atomic_json(state / 'collection-status.json', {'ok': True})
        except Exception as error:
            # Do not overwrite the last successful collection timestamp.
            print('Feed collection failed: ' + type(error).__name__, flush=True)
            atomic_json(state / 'collection-status.json', {'ok': False, 'error': type(error).__name__})
        try:
            collect_watch(state)
        except Exception as error:
            print('Watch collection failed: ' + type(error).__name__, flush=True)
        try:
            if args.capture:
                from capture_posts import main as capture
                capture(3, state)
            if args.translate:
                from translate_posts import ConfiguredTranslator, translate_pending
                translate_pending(state, translator_factory=lambda: ConfiguredTranslator(state / 'translation.json'))
            if args.capture or args.translate:
                # Enrich the existing feed without implying a fresh X timeline check.
                from collector import attach_post_content
                from post_briefs import attach_briefs
                feed = attach_post_content(read_json(state / 'data.json'), {}, read_json(state / 'post-content.json'), read_json(state / 'post-translations.zh.json'))
                atomic_json(state / 'data.json', attach_briefs(feed))
        except Exception as error:
            print('Optional content processing failed: ' + type(error).__name__, flush=True)
        stop.wait(interval)


def handler(root, state, port):
    static = (root / 'dist/client/radar').resolve()

    class Handler(ReactionHandler):
        store = ReactionStore(state / 'reactions.sqlite3', state / 'data.json')
        watch_store = WatchStore(state / 'reactions.sqlite3', state / 'data.json')
        limiter = RateLimiter()

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def route(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/radar':
                return '/'
            return path[6:] if path.startswith('/radar/') else path

        def do_GET(self):
            path = self.route()
            if path in ('/api/reactions', '/api/watch', '/health'):
                self.path = path.removeprefix('/api')
                return super().do_GET()
            if path == '/data.json':
                return self.file(state / 'data.json', no_cache=True)
            if path.startswith('/post-images/'):
                name = path.removeprefix('/post-images/')
                if not re.fullmatch(r'\d+-[a-f0-9]{16}\.jpg', name):
                    return self.send_json(404, {'error': 'not found'})
                return self.file(state / 'post-images' / name)
            if '\\' in path or '\x00' in path or any(part.startswith('.') for part in path.split('/') if part):
                return self.send_json(404, {'error': 'not found'})
            target = (static / path.lstrip('/')).resolve()
            if not target.is_relative_to(static):
                return self.send_json(404, {'error': 'not found'})
            if target.is_dir():
                target = target / 'index.html'
            return self.file(target, no_cache=target.suffix == '.html')

        def file(self, target, no_cache=False):
            if not target.is_file():
                return self.send_json(404, {'error': 'not found'})
            mime = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            if target.suffix in ('.js', '.mjs'):
                mime = 'text/javascript'
            if target.suffix == '.css':
                mime = 'text/css'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(target.stat().st_size))
            self.send_header('Cache-Control', 'no-store' if no_cache else 'public, max-age=3600')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
            self.end_headers()
            with target.open('rb') as stream:
                shutil.copyfileobj(stream, self.wfile)

        def do_POST(self):
            path = self.route()
            if path not in ('/api/watch', '/api/reactions'):
                self.close_connection = True
                return self.send_json(404, {'error': 'not found'})
            self.path = path.removeprefix('/api')
            return super().do_POST()

    return Handler


def serve(root, args):
    state = args.state.resolve()
    initialize(root, state)
    origins = {f'http://localhost:{args.port}', f'http://127.0.0.1:{args.port}', 'http://localhost:4175', 'http://127.0.0.1:4175'}
    origins.update(value.strip().rstrip('/') for value in os.getenv('ALLOWED_ORIGINS', '').split(',') if value.strip())
    reactions.ALLOWED_ORIGINS = origins
    server = ReactionServer((args.host, args.port), handler(root, state, args.port))
    stop = threading.Event()
    worker = None
    if args.live:
        worker = threading.Thread(target=poll, args=(state, stop, args), daemon=True)
        worker.start()
    print(f'Tibo: http://localhost:{args.port}/ | live={args.live} | data={state}', flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
