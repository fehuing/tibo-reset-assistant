import unittest
from announcement_semantics import assess, annotate_records, build_events


class AnnouncementStateTests(unittest.TestCase):
    def test_status_describes_source_not_account(self):
        self.assertEqual(assess('We have now reset usage for all paid Codex users.')['status'], 'announced')
        self.assertEqual(assess('The limits have been reset.')['status'], 'announced')
        self.assertEqual(assess('Reset has been propagated to accounts.')['status'], 'announced')

    def test_future_does_not_become_completed_when_clock_passes(self):
        self.assertEqual(assess('We will do the full banked reset today for all Plus users. Lands end of day.')['status'], 'planned')
        self.assertEqual(assess("We are resetting usage for all paid Codex users.")['status'], 'planned')
        self.assertEqual(assess("We've got you covered with a banked reset. Lands by end of day.")['status'], 'planned')

    def test_negated_conditional_and_metaphorical_are_not_confirmed(self):
        for body in ['We have not reset Codex usage.', 'We will not reset Codex usage.',
                     'If we reset Codex usage, would that help?', 'Codex users, feeling reset and reborn today!',
                     'Maybe we reset your Codex limits tomorrow?']:
            with self.subTest(body=body):
                self.assertEqual(assess(body)['status'], 'uncertain')

    def test_observed_records_are_not_confirmations(self):
        self.assertEqual(assess('We reset Codex usage.', 'observed')['status'], 'uncertain')

    def test_quote_and_hash_are_reproducible(self):
        result = assess('An update. We have reset Codex usage.')
        self.assertEqual(result['assessment']['quote'], 'We have reset Codex usage.')
        self.assertEqual(len(result['assessment']['source_sha256']), 64)


if __name__ == '__main__':
    unittest.main()


class EventLedgerTests(unittest.TestCase):
    def row(self, ident, body, day):
        return {'id': ident, 'source_text': body, 'source_type': 'x_post', 'reset_type': 'regular',
                'announced_at': '2026-09-0' + str(day) + 'T00:00:00Z', 'source_url': 'https://x.com/thsottiaux/status/' + ident}

    def test_explicit_followup_counts_as_one_event_and_preserves_posts(self):
        feed = {'records': [self.row('101', 'We will reset Codex usage.', 1),
                            self.row('102', 'Update: we have reset Codex usage. https://x.com/thsottiaux/status/101', 2)]}
        result = build_events(annotate_records(feed))
        self.assertEqual(result['event_stats']['total'], 1)
        self.assertEqual(result['event_stats']['announcement_total'], 2)
        self.assertEqual(result['events'][0]['record_ids'], ['101', '102'])
        self.assertEqual(result['events'][0]['record_id'], '102')
        self.assertEqual(result['event_stats']['avg_interval_days'], None)

    def test_close_timestamps_are_not_evidence_of_same_event(self):
        feed = {'records': [self.row('101', 'We have reset Codex usage.', 1), self.row('102', 'We reset Codex usage.', 1)]}
        self.assertEqual(build_events(annotate_records(feed))['event_stats']['total'], 2)

    def test_pending_and_observations_do_not_enter_completed_statistics(self):
        feed = {'records': [self.row('101', 'We will reset Codex usage.', 1), self.row('102', 'Feeling reset, Codex users!', 2), self.row('103', 'We reset Codex usage.', 3)]}
        result = build_events(annotate_records(feed))
        self.assertEqual(result['event_stats']['total'], 1)
        self.assertEqual(result['event_stats']['planned'], 1)
        self.assertEqual(result['event_stats']['uncertain'], 1)
