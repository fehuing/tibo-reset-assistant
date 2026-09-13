"""Exercise the built app through HTTP in an isolated, disposable instance."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, body=None, origin=None):
        headers = {'Content-Type': 'application/json'} if body is not None else {}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None, headers)
        try:
            response = opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    with tempfile.TemporaryDirectory(prefix='tibo-smoke-') as temp:
        state = Path(temp) / 'state'
        env = dict(os.environ, LIVE_COLLECTION='0', AI_ANALYSIS='0', CAPTURE_POSTS='0', TRANSLATE_POSTS='0', ALLOWED_ORIGINS=base)
        process = None
        log = (Path(temp) / 'server.log').open('w+', encoding='utf-8')

        def start():
            proc = subprocess.Popen([sys.executable, str(ROOT / 'run.py'), '--no-build', '--host', '127.0.0.1', '--port', str(port), '--state', str(state)],
                                    cwd=ROOT, env=env, stdout=log, stderr=log)
            for _ in range(100):
                if proc.poll() is not None:
                    log.seek(0)
                    raise AssertionError('Server exited: ' + log.read()[-4000:])
                try:
                    if request('/health')[0] == 200:
                        return proc
                except OSError:
                    pass
                time.sleep(.1)
            proc.terminate(); proc.wait(timeout=10)
            raise AssertionError('Server did not become ready')

        try:
            process = start()
            status, html, _ = request('/')
            assert status == 200 and b'<!DOCTYPE html>' in html, 'Homepage must be real HTML'
            assert request('/radar/')[1] == html, 'Root and legacy prefix must match'
            files = list((ROOT / 'dist/client/radar').rglob('*'))
            assets = [p for p in files if p.is_file() and p.suffix in ('.js', '.css', '.png', '.jpg', '.svg')]
            for file in assets:
                url = '/radar/' + file.relative_to(ROOT / 'dist/client/radar').as_posix()
                status, body, headers = request(url)
                assert status == 200 and body == file.read_bytes(), url
                if file.suffix == '.js':
                    assert headers['Content-Type'] == 'text/javascript', url
            feed = json.loads(request('/data.json')[1])
            seed = json.loads((ROOT / 'sample-data/data.json').read_text(encoding='utf-8'))
            assert feed['mode'] == 'snapshot' and feed['records'] == seed['records']
            assert feed.get('announcements') == seed.get('announcements') and len(feed['announcements']) >= 3
            assert feed['collection_status']['state'] == 'disabled'
            assert json.loads(request('/api/collection-status')[1])['state'] == 'disabled'
            assert json.loads(request('/radar/data.json')[1]) == feed
            image_count = 0
            for row in feed['records'] + feed.get('announcements', []):
                for shot in (row.get('screenshot'), row.get('screenshot', {}).get('thumbnail')):
                    if shot:
                        status, body, _ = request('/radar/post-images/' + shot['file'])
                        assert status == 200 and hashlib.sha256(body).hexdigest() == shot['sha256']
                        image_count += 1
            for path in ('/.env', '/.data/reactions.sqlite3', '/ops/server.py', '/radar/../.env', '/radar/%2e%2e/.env', '/radar/post-images/../../run.py',
                         '/auth.json', '/.codex/auth.json', '/ai-input/manifest.json', '/ai-analysis/state.json', '/private-reports/reports.sqlite3'):
                assert request(path)[0] == 404, path
            current = json.loads(request('/api/reactions')[1])
            assert current['count'] == 0, 'No production counter may be imported'
            payload = {'request_id': 'smoke_request_0001', 'n': 2}
            assert request('/api/reactions', payload, 'https://untrusted.example')[0] == 403
            assert request('/api/reactions', payload, base)[0] == 200
            assert json.loads(request('/radar/api/reactions', payload, base)[1])['count'] == 2
            watch = json.loads(request('/api/watch')[1])
            assert watch['total'] == 0 and watch['yes_percent'] is None, 'No production votes may be imported'
            # Force a stale source in this disposable test instance only.
            archived_watch = json.loads((state / 'watch.json').read_text(encoding='utf-8'))
            archived_watch['checked_at'] = '2000-01-01T00:00:00Z'
            (state / 'watch.json').write_text(json.dumps(archived_watch), encoding='utf-8')
            payload = {'episode_id': '2096692394435752258', 'voter_id': 'smoke_browser_0001', 'vote': 'yes'}
            assert request('/api/watch', payload, base)[0] == 409, 'Stale watches must reject votes'
            process.terminate(); process.wait(timeout=10)
            process = start()
            assert json.loads(request('/api/reactions')[1])['count'] == 2, 'Restart must preserve counters'
            assert json.loads(request('/data.json')[1]) == feed, 'Interactions must not mutate feed'
            print(json.dumps({'ok': True, 'records': len(feed['records']), 'verified_images': image_count,
                              'built_assets': len(assets), 'api': 'passed', 'restart_persistence': 'passed',
                              'path_and_origin_checks': 'passed'}))
        finally:
            if process and process.poll() is None:
                process.terminate(); process.wait(timeout=10)
            log.close()


if __name__ == '__main__':
    main()
