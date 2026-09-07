from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import threading
import http.client
import unittest

from reset_watch import public_posts, hint_from_post, collect_watch, watch_state, PROFILE
from watch_votes import WatchStore, WatchClosed
from reactions import ReactionHandler, ReactionServer, ReactionStore, RateLimiter

NOW = dt.datetime(2026, 9, 7, 7, tzinfo=dt.timezone.utc)
POST = {'id': '2096692394435752258', 'author': 'thsottiaux',
        'source_url': 'https://x.com/thsottiaux/status/2096692394435752258',
        'text': "Who says it won't reset in a while 👀", 'announced_at': '2026-09-06T20:09:56Z',
        'reply_context': {'text': "My usage has expired and won't reset for a while.", 'author': 'Gelassoldat',
                          'source_url': 'https://x.com/Gelassoldat/status/2096690263561306468'}}


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.hint = hint_from_post(POST, NOW, 'user_reference')
        self.hint['verified_at'] = NOW.isoformat()
        self.feed = {'schema_version': 1, 'records': [{'id': 'previous'}], 'events': [], 'event_stats': {'total': 17}}
        (self.root / 'data.json').write_text(json.dumps(self.feed), encoding='utf-8')
        self.write_watch(self.hint)
        self.store = WatchStore(self.root / 'votes.sqlite3', self.root / 'data.json', clock=lambda: NOW)

    def tearDown(self):
        self.temp.cleanup()

    def write_watch(self, hint):
        (self.root / 'watch.json').write_text(json.dumps({'schema_version': 1, 'checked_at': NOW.isoformat(), 'watch': hint}), encoding='utf-8')

    def test_current_reply_is_hint_not_delivery_and_has_fixed_window(self):
        self.assertEqual(self.hint['episode_id'], POST['id'])
        self.assertEqual(self.hint['expires_at'], '2026-09-07T20:09:56+00:00')
        self.assertEqual(watch_state(self.hint, self.feed, NOW), 'active')
        self.assertEqual(watch_state(self.hint, self.feed, NOW + dt.timedelta(days=1)), 'expired')
        self.assertEqual(self.feed['event_stats']['total'], 17)

    def test_unrelated_negative_other_author_and_delivered_posts_are_not_hints(self):
        for changes in ({'author': 'someone_else'}, {'text': 'Astra is fast 👀'},
                        {'text': "We won't reset Codex usage today."}, {'text': 'We have reset Codex usage. More news soon!'},
                        {'reply_context': None}, {'announced_at': '2026-09-05T12:00:00Z'}):
            row = dict(POST, **changes)
            if row.get('reply_context') is None: row.pop('reply_context', None)
            self.assertIsNone(hint_from_post(row, NOW, 'x_public_timeline'))

    def test_synthetic_document_resolves_reply_authors_and_context(self):
        fixture = Path(__file__).resolve().parents[1] / 'tests/fixtures/hint.html'
        self.assertTrue(fixture.exists(), 'Retain the synthetic parser fixture for reproduction')
        posts = public_posts(fixture.read_text(encoding='utf-8'))
        own = [post for post in posts if post['author'] == 'thsottiaux']
        self.assertEqual([post['id'] for post in own], [POST['id']])
        self.assertEqual(own[0]['reply_context']['author'], 'Gelassoldat')
        self.assertTrue(all('/' + post['author'] + '/status/' in post['source_url'] for post in posts))

    def test_no_votes_is_null_percentage_then_unique_browser_can_change_vote(self):
        self.assertIsNone(self.store.current()['yes_percent'])
        self.assertEqual(self.store.vote(POST['id'], 'browser_0000000001', 'yes')['total'], 1)
        self.assertEqual(self.store.vote(POST['id'], 'browser_0000000001', 'yes')['total'], 1)
        result = self.store.vote(POST['id'], 'browser_0000000001', 'no')
        self.assertEqual((result['yes'], result['no'], result['total']), (0, 1, 1))
        self.assertEqual(self.store.vote(POST['id'], 'browser_0000000002', 'yes')['yes_percent'], 50)

    def test_concurrent_duplicate_votes_do_not_inflate_count(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.store.vote(POST['id'], 'same_browser_0001', 'yes'), range(15)))
        self.assertEqual(self.store.current()['total'], 1)

    def test_expired_stale_new_announcement_and_wrong_episode_reject_votes(self):
        with self.assertRaises(WatchClosed): self.store.vote('2096692394435752259', 'browser_0000000001', 'yes')
        self.hint['verified_at'] = (NOW - dt.timedelta(minutes=9)).isoformat(); self.write_watch(self.hint)
        with self.assertRaises(WatchClosed): self.store.vote(POST['id'], 'browser_0000000001', 'yes')
        self.hint['verified_at'] = NOW.isoformat(); self.hint['expires_at'] = NOW.isoformat(); self.write_watch(self.hint)
        with self.assertRaises(WatchClosed): self.store.vote(POST['id'], 'browser_0000000001', 'yes')
        self.assertEqual(self.store.current()['total'], 0)

    def test_new_explicit_announcement_closes_watch_without_reclassifying_hint(self):
        self.feed['events'] = [{'status': 'announced', 'announced_at': NOW.isoformat()}]
        (self.root / 'data.json').write_text(json.dumps(self.feed))
        self.assertEqual(self.store.current()['state'], 'new_announcement')
        with self.assertRaises(WatchClosed): self.store.vote(POST['id'], 'browser_0000000001', 'yes')
        self.assertNotIn('status', self.store.current()['watch'])

    def test_new_episode_does_not_inherit_votes(self):
        self.store.vote(POST['id'], 'browser_0000000001', 'yes')
        self.hint['episode_id'] = '2096692394435752259'; self.write_watch(self.hint)
        self.assertEqual(self.store.current()['total'], 0)

    def test_collector_failure_retains_original_expiry_and_stops_voting_when_stale(self):
        def fail(_): raise OSError('offline')
        before = (self.root / 'data.json').read_bytes()
        result = collect_watch(self.root, get=fail, now=NOW + dt.timedelta(minutes=9))
        self.assertEqual(result['watch'], self.hint)
        self.assertEqual((self.root / 'data.json').read_bytes(), before)
        self.store.clock = lambda: NOW + dt.timedelta(minutes=9)
        self.assertTrue(self.store.current()['stale'])

    def test_reference_pointer_does_not_supply_body_probability_or_counts(self):
        (self.root / 'watch-config.json').write_text(json.dumps({'reference_discovery': True}))
        document = (Path(__file__).resolve().parents[1] / 'tests/fixtures/hint.html').read_text(encoding='utf-8')
        def get(url):
            if url == POST['source_url']: return document
            if 'codex-resets.com' in url: return json.dumps({'data': {'active_watch': {'source': {'url': POST['source_url']}, 'text': 'FAKE', 'reset_chance_percent': 99}}})
            raise OSError('Public timeline absent')
        result = collect_watch(self.root, get=get, now=NOW)
        self.assertIn('Who says', result['watch']['text'])
        self.assertEqual(result['watch']['discovered_via'], 'reference_pointer')
        self.assertNotIn('reset_chance_percent', result['watch'])
        self.assertEqual(self.store.current()['total'], 0)

    def test_http_votes_origin_validation_and_stale_episode(self):
        class Handler(ReactionHandler):
            watch_store = self.store
            store = ReactionStore(self.root / 'votes.sqlite3', self.root / 'data.json')
            limiter = RateLimiter()
            def log_message(self, *args): pass
        server = ReactionServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with closing(http.client.HTTPConnection(*server.server_address, timeout=3)) as connection:
                def request(body, origin='http://localhost:8080'):
                    connection.request('POST', '/watch', json.dumps(body), {'Content-Type': 'application/json', 'Origin': origin})
                    response = connection.getresponse(); result = json.loads(response.read()); return response.status, result
                body = {'episode_id': POST['id'], 'voter_id': 'http_browser_00001', 'vote': 'yes'}
                self.assertEqual(request(body, 'https://other.example')[0], 403)
                self.assertEqual(request(dict(body, vote='maybe'))[0], 400)
                self.assertEqual(request(dict(body, episode_id='2096692394435752259'))[0], 409)
                status, result = request(body)
                self.assertEqual((status, result['total'], result['yes']), (200, 1, 1))
                self.assertEqual(request(body)[1]['total'], 1)
                self.assertEqual(request(dict(body, vote='no'))[1]['yes'], 0)
                connection.request('GET', '/watch'); response = connection.getresponse()
                self.assertEqual(json.loads(response.read())['no'], 1)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__': unittest.main()
