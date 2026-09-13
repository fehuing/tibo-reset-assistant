import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from announcement_semantics import annotate_records, build_events
from historical_baseline import apply_baseline, create_baseline, load_baseline, retain_history
from collector import _feed

NOW = dt.datetime(2026, 9, 13, tzinfo=dt.timezone.utc)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        rows = [{'id': str(10000000001 + index), 'source_url': 'https://x.com/thsottiaux/status/' + str(10000000001 + index),
                 'source_type': 'x_post', 'announced_at': f'2026-09-0{index + 1}T00:00:00+00:00',
                 'reset_type': 'banked' if index == 1 else 'regular', 'status': 'planned',
                 'source_text': 'We will reset Codex usage tomorrow.', 'excerpt': 'A planned reset.'}
                for index in range(3)]
        self.feed = _feed(rows, NOW, {'active': 'snapshot'})
        self.baseline = create_baseline(self.feed, NOW.isoformat())

    def initialize(self, feed):
        return build_events(apply_baseline(annotate_records(feed), self.baseline))

    def test_verified_seed_keeps_original_posts_and_categories(self):
        result = self.initialize(copy.deepcopy(self.feed))
        self.assertEqual(result['event_stats']['total'], 3)
        self.assertEqual(result['event_stats']['banked'], 1)
        for before, after in zip(self.feed['records'], result['records']):
            for key in ('id', 'source_url', 'source_text', 'announced_at', 'reset_type'):
                self.assertEqual(before[key], after[key])
            self.assertEqual(after['status'], 'announced')

    def test_old_date_or_forged_marker_does_not_approve_new_id(self):
        row = dict(self.feed['records'][0], id='99999999999', source_url='https://x.com/thsottiaux/status/99999999999',
                   historical_verification={'method': 'site_owner_verified_history'})
        self.feed['records'].append(row)
        self.initialize(self.feed)
        self.assertEqual(row['status'], 'planned')
        self.assertNotIn('historical_verification', row)
        self.assertEqual(self.feed['event_stats']['total'], 3)

    def test_corrupted_seal_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'historical-baseline.json'
            path.write_text(json.dumps(self.baseline), encoding='utf-8')
            self.assertEqual(len(load_baseline(path)['records']), 3)
            self.baseline['records'][0]['id'] = 'tampered'
            path.write_text(json.dumps(self.baseline), encoding='utf-8')
            with self.assertRaises(AssertionError):
                load_baseline(path)

    def test_partial_feed_cannot_drop_verified_history(self):
        partial = copy.deepcopy(self.feed)
        partial['records'] = [dict(partial['records'][0], reset_type='banked')]
        result = self.initialize(retain_history(partial, {}, self.baseline))
        self.assertEqual(result['event_stats']['total'], 3)
        self.assertEqual(result['event_stats']['banked'], 1)

    def test_repeated_reads_cannot_downgrade_verified_history(self):
        result = self.initialize(copy.deepcopy(self.feed))
        for _ in range(2):
            result = self.initialize(result)
            self.assertEqual(result['event_stats']['total'], 3)
            self.assertTrue(all(row['status'] == 'announced' for row in result['records']))

    def test_sealed_public_actual_time_survives_publication_without_private_ledger(self):
        from publication_state import apply_private_reports
        original = self.feed['records'][0]
        original['reset_confirmation'] = {
            'method': 'historical_public_snapshot', 'kind': 'official',
            'reset_at': '2026-09-12T08:31:00+00:00', 'verified_at': '2026-09-12T09:05:25+00:00',
            'private_field': 'must not be copied'}
        baseline = create_baseline(self.feed, NOW.isoformat())
        candidate = copy.deepcopy(self.feed)
        candidate['records'][0]['reset_confirmation']['reset_at'] = '2026-01-01T00:00:00Z'
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                candidate = apply_private_reports(apply_baseline(candidate, baseline), Path(folder))
                candidate = build_events(candidate)
        confirmed = candidate['records'][0]['reset_confirmation']
        self.assertEqual(confirmed['reset_at'], '2026-09-12T08:31:00+00:00')
        self.assertEqual(set(confirmed), {'method', 'kind', 'reset_at', 'verified_at'})
        event = next(event for event in candidate['events'] if original['id'] in event['record_ids'])
        self.assertEqual(event['reset_at'], confirmed['reset_at'])
        self.assertEqual(event['confirmation_method'], 'historical_public_snapshot')
        self.assertNotIn('watch_episode_id', event)
