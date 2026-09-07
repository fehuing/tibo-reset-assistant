import json
from pathlib import Path
import tempfile
import unittest

from reactions import RateLimiter, ReactionStore


class ReactionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.feed = root / 'data.json'
        self.database = root / 'reactions.sqlite3'
        self.write_feed('reset-a', '2026-09-03T23:12:09.000Z')
        self.store = ReactionStore(self.database, self.feed)

    def tearDown(self):
        self.temp.cleanup()

    def write_feed(self, cycle_id, announced_at):
        self.feed.write_text(json.dumps({
            'schema_version': 1,
            'records': [{'id': cycle_id, 'announced_at': announced_at}],
        }), encoding='utf-8')

    def test_counts_are_idempotent_and_scoped_to_the_latest_reset(self):
        self.assertEqual(self.store.current()['count'], 0)
        self.assertEqual(self.store.increment('request_0001', 3)['count'], 3)
        self.assertEqual(self.store.increment('request_0001', 3)['count'], 3)
        self.assertEqual(self.store.increment('request_0002', 2)['count'], 5)
        self.write_feed('reset-b', '2026-09-05T01:00:00.000Z')
        self.assertEqual(self.store.current(), {
            'schema_version': 1,
            'cycle_id': 'reset-b',
            'since': '2026-09-05T01:00:00.000Z',
            'count': 0,
        })

    def test_rate_limit_caps_minute_and_hour_totals(self):
        limiter = RateLimiter()
        self.assertTrue(limiter.allow('127.0.0.1', 10, now=1000))
        for index in range(5):
            self.assertTrue(limiter.allow('127.0.0.1', 10, now=1001 + index))
        self.assertFalse(limiter.allow('127.0.0.1', 1, now=1010))
        self.assertTrue(limiter.allow('127.0.0.1', 10, now=1061))
        for index in range(17):
            self.assertTrue(limiter.allow('127.0.0.1', 10, now=1122 + index * 61))
        self.assertFalse(limiter.allow('127.0.0.1', 1, now=2200))


if __name__ == '__main__':
    unittest.main()
