"""Anonymous browser votes for a verified hint; never writes announcement data."""
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import re
import sqlite3

from reset_watch import date, watch_state


class WatchClosed(ValueError):
    pass


class WatchStore:
    def __init__(self, db_path, feed_path, watch_path=None, clock=None):
        self.db_path, self.feed_path = Path(db_path), Path(feed_path)
        self.watch_path = Path(watch_path) if watch_path else self.feed_path.with_name('watch.json')
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        with closing(self.connect()) as connection:
            connection.executescript('''CREATE TABLE IF NOT EXISTS watch_votes (
                episode_id TEXT NOT NULL, voter_id TEXT NOT NULL,
                vote TEXT NOT NULL CHECK(vote IN ('yes','no')), updated_at TEXT NOT NULL,
                PRIMARY KEY(episode_id, voter_id));''')

    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute('PRAGMA journal_mode=WAL')
        return connection

    def context(self):
        now = self.clock()
        for path in (self.watch_path, self.feed_path):
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('Data is too large')
        data = json.loads(self.watch_path.read_text(encoding='utf-8'))
        feed = json.loads(self.feed_path.read_text(encoding='utf-8'))
        if data.get('schema_version') != 1 or feed.get('schema_version') != 1:
            raise ValueError('Invalid schema')
        watch = data.get('watch')
        state = watch_state(watch, feed, now)
        stale = now - date(data['checked_at']) > dt.timedelta(minutes=8)
        if watch:
            stale = stale or now - date(watch['verified_at']) > dt.timedelta(minutes=8)
        return {'schema_version': 1, 'watch': watch, 'state': state, 'stale': stale, 'checked_at': data['checked_at']}

    def counts(self, connection, context):
        ident = (context['watch'] or {}).get('episode_id', '')
        counts = dict(connection.execute('SELECT vote,COUNT(*) FROM watch_votes WHERE episode_id=? GROUP BY vote', (ident,)).fetchall())
        yes, no = counts.get('yes', 0), counts.get('no', 0)
        return dict(context, yes=yes, no=no, total=yes + no, yes_percent=(yes * 100 + (yes + no) // 2) // (yes + no) if yes + no else None)

    def current(self):
        context = self.context()
        with closing(self.connect()) as connection:
            return self.counts(connection, context)

    def vote(self, episode_id, voter_id, vote):
        if not isinstance(episode_id, str) or not re.fullmatch(r'\d{10,25}', episode_id):
            raise ValueError('Invalid episode_id')
        if not isinstance(voter_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', voter_id) or vote not in ('yes', 'no'):
            raise ValueError('Invalid vote')
        with closing(self.connect()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            context = self.context()
            if context['state'] != 'active' or context['stale'] or context['watch']['episode_id'] != episode_id:
                raise WatchClosed('Watch is closed, changed or needs a fresh source check')
            connection.execute('INSERT INTO watch_votes VALUES(?,?,?,?) ON CONFLICT(episode_id,voter_id) '
                               'DO UPDATE SET vote=excluded.vote,updated_at=excluded.updated_at',
                               (episode_id, voter_id, vote, self.clock().isoformat()))
            response = self.counts(connection, context)
            connection.commit()
            return dict(response, vote=vote)
