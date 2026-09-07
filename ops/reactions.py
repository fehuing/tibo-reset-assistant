"""Small same-origin public reaction counter for Reset Radar.

The standalone server exposes same-origin endpoints and uses the actual socket
peer for basic rate limiting. Counts are scoped to each announcement.
"""
from collections import defaultdict, deque
from contextlib import closing
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.parse import urlsplit
from watch_votes import WatchStore, WatchClosed


DATA_PATH = Path(os.environ.get('RESET_RADAR_DATA', '.data/data.json'))
DB_PATH = Path(os.environ.get('RESET_RADAR_REACTIONS_DB', '.data/reactions.sqlite3'))
PORT = int(os.environ.get('RESET_RADAR_REACTIONS_PORT', '18765'))
ALLOWED_ORIGINS = {'http://localhost:8080', 'http://127.0.0.1:8080'}
REQUEST_ID = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_current_cycle(path=DATA_PATH):
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('feed is unexpectedly large')
    feed = json.loads(raw)
    records = feed.get('records') if isinstance(feed, dict) else None
    if feed.get('schema_version') != 1 or not isinstance(records, list) or not records:
        raise ValueError('feed has no current reset')
    latest = records[0]
    cycle_id, since = latest.get('id'), latest.get('announced_at')
    if not isinstance(cycle_id, str) or not 1 <= len(cycle_id) <= 64:
        raise ValueError('invalid reset ID')
    if not isinstance(since, str):
        raise ValueError('invalid reset timestamp')
    parsed = dt.datetime.fromisoformat(since.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('reset timestamp needs a timezone')
    return cycle_id, since


class ReactionStore:
    def __init__(self, db_path=DB_PATH, feed_path=DATA_PATH):
        self.db_path = Path(db_path)
        self.feed_path = Path(feed_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS cycles (
                    cycle_id TEXT PRIMARY KEY,
                    since TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount BETWEEN 1 AND 10),
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS requests_created_at ON requests(created_at);
            ''')

    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=NORMAL')
        return connection

    def current(self):
        cycle_id, since = read_current_cycle(self.feed_path)
        with closing(self.connect()) as connection:
            connection.execute(
                'INSERT INTO cycles(cycle_id, since, count, updated_at) VALUES(?, ?, 0, ?) '
                'ON CONFLICT(cycle_id) DO UPDATE SET since=excluded.since',
                (cycle_id, since, utc_now()),
            )
            count = connection.execute('SELECT count FROM cycles WHERE cycle_id=?', (cycle_id,)).fetchone()[0]
        return {'schema_version': 1, 'cycle_id': cycle_id, 'since': since, 'count': count}

    def increment(self, request_id, amount):
        cycle_id, since = read_current_cycle(self.feed_path)
        now = int(time.time())
        with closing(self.connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute(
                'INSERT INTO cycles(cycle_id, since, count, updated_at) VALUES(?, ?, 0, ?) '
                'ON CONFLICT(cycle_id) DO UPDATE SET since=excluded.since',
                (cycle_id, since, utc_now()),
            )
            duplicate = connection.execute('SELECT 1 FROM requests WHERE request_id=?', (request_id,)).fetchone()
            if not duplicate:
                connection.execute(
                    'INSERT INTO requests(request_id, cycle_id, amount, created_at) VALUES(?, ?, ?, ?)',
                    (request_id, cycle_id, amount, now),
                )
                connection.execute(
                    'UPDATE cycles SET count=count+?, updated_at=? WHERE cycle_id=?',
                    (amount, utc_now(), cycle_id),
                )
                connection.execute('DELETE FROM requests WHERE created_at < ?', (now - 7 * 86400,))
            count = connection.execute('SELECT count FROM cycles WHERE cycle_id=?', (cycle_id,)).fetchone()[0]
            connection.commit()
        return {'schema_version': 1, 'cycle_id': cycle_id, 'since': since, 'count': count}


class RateLimiter:
    """Per-process rate limit without retaining visitor addresses on disk."""
    def __init__(self):
        self.events = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, address, amount, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            queue = self.events[address]
            while queue and queue[0][0] <= now - 3600:
                queue.popleft()
            minute_total = sum(value for stamp, value in queue if stamp > now - 60)
            hour_total = sum(value for _, value in queue)
            if minute_total + amount > 60 or hour_total + amount > 240:
                return False
            queue.append((now, amount))
            return True


class ReactionHandler(BaseHTTPRequestHandler):
    server_version = 'ResetRadar'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    store = None
    limiter = None
    watch_store = None

    def log_message(self, fmt, *args):
        print('%s - %s' % (self.client_address[0], fmt % args), flush=True)

    def send_json(self, status, value, extra_headers=None):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for name, content in (extra_headers or {}).items():
            self.send_header(name, content)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if urlsplit(self.path).path == '/watch':
            try:
                self.send_json(200, self.watch_store.current())
            except Exception as error:
                print('watch read failed: %s' % error, flush=True)
                self.send_json(503, {'error': 'watch unavailable'})
            return
        if urlsplit(self.path).path == '/health':
            self.send_json(200, {'ok': True})
            return
        if urlsplit(self.path).path != '/reactions':
            self.send_json(404, {'error': 'not found'})
            return
        try:
            self.send_json(200, self.store.current())
        except Exception as error:
            print('reaction read failed: %s' % error, flush=True)
            self.send_json(503, {'error': 'reaction count unavailable'})

    def do_POST(self):
        is_watch = urlsplit(self.path).path == '/watch'
        if urlsplit(self.path).path not in ('/reactions', '/watch'):
            self.send_json(404, {'error': 'not found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 1 <= length <= 1024:
            self.close_connection = True
            self.send_json(400, {'error': 'invalid request body'})
            return
        raw = self.rfile.read(length)
        origin = self.headers.get('Origin')
        if origin and origin not in ALLOWED_ORIGINS:
            self.send_json(403, {'error': 'origin not allowed'})
            return
        if not self.headers.get('Content-Type', '').lower().startswith('application/json'):
            self.send_json(415, {'error': 'application/json required'})
            return
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {'error': 'invalid JSON'})
            return
        request_id = value.get('voter_id' if is_watch else 'request_id') if isinstance(value, dict) else None
        amount = 1 if is_watch else value.get('n') if isinstance(value, dict) else None
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            self.send_json(400, {'error': 'invalid request_id'})
            return
        if type(amount) is not int or not 1 <= amount <= 10:
            self.send_json(400, {'error': 'n must be an integer from 1 to 10'})
            return
        # Do not trust client-supplied forwarding headers.
        forwarded = self.client_address[0]
        try:
            address = str(ipaddress.ip_address(forwarded))
        except ValueError:
            address = self.client_address[0]
        if not self.limiter.allow(address, amount):
            self.send_json(429, {'error': 'too many reactions'}, {'Retry-After': '60'})
            return
        try:
            if is_watch:
                self.send_json(200, self.watch_store.vote(value.get('episode_id'), request_id, value.get('vote')))
            else:
                self.send_json(200, self.store.increment(request_id, amount))
        except WatchClosed:
            self.send_json(409, {'error': 'watch is closed or changed; refresh'})
        except ValueError:
            self.send_json(400, {'error': 'invalid vote'})
        except Exception as error:
            print('reaction update failed: %s' % error, flush=True)
            self.send_json(503, {'error': 'reaction count unavailable'})


class ReactionServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ReactionHandler.store = ReactionStore()
    ReactionHandler.watch_store = WatchStore(DB_PATH, DATA_PATH)
    ReactionHandler.limiter = RateLimiter()
    server = ReactionServer(('127.0.0.1', PORT), ReactionHandler)
    print('reaction service listening on 127.0.0.1:%d' % PORT, flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
