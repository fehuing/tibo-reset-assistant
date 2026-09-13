import copy
import datetime as dt
import hashlib
import unittest
from ai_publication import apply_decisions, make_watch
from announcement_semantics import build_events
from reset_watch import watch_state

NOW = dt.datetime(2026, 9, 13, 1, tzinfo=dt.timezone.utc)
ID = '2098685367058612394'
OLD = '2098612714704891959'

def post(ident=ID, when='2026-09-13T00:00:00+00:00'):
    return {'id': ident, 'author': 'thsottiaux', 'source_url': 'https://x.com/thsottiaux/status/' + ident,
            'announced_at': when, 'text': 'A global Codex reset is complete.', 'first_seen_at': when,
            'last_seen_at': NOW.isoformat(), 'source_text_sha256': hashlib.sha256(b'A global Codex reset is complete.').hexdigest()}

def envelope(signal='delivered', scope='global', relevance='reset', kind='regular', ident=ID):
    return {'status': 'ready', 'model': 'gpt-6-astra', 'prompt_version': 'test', 'analyzed_at': NOW.isoformat(),
            'result': {'schema_version': 1, 'id': ident, 'source_sha256': post()['source_text_sha256'],
                       'translation_zh': 'Codex 全球额度重置已完成。', 'summary_zh': '全球重置已完成。',
                       'summary_en': 'Global reset complete.', 'signal': signal, 'scope': scope, 'relevance': relevance,
                       'reset_type': kind, 'related_post_id': None, 'reset_at': None,
                       'prediction': {'outlook': 'unknown', 'reason_zh': '无预测。', 'reason_en': 'No forecast.'},
                       'evidence': [post()['text']]}}

class PublicationTests(unittest.TestCase):
    def merge(self, env, rows=None):
        return apply_decisions({'records': rows or []}, {'posts': {ID: post()}}, {ID: env}, NOW)

    def test_irrelevant_and_personal_never_enter_feed(self):
        for env in (envelope(relevance='none', signal='none'), envelope(scope='personal')):
            self.assertEqual(self.merge(env)['records'], [])

    def test_future_not_confirmed_and_hint_not_calendar(self):
        feed = build_events(self.merge(envelope(signal='announced')))
        self.assertEqual(feed['records'][0]['status'], 'planned')
        self.assertEqual(feed['event_stats']['total'], 0)
        self.assertFalse(self.merge(envelope(signal='hint'))['records'])

    def test_unknown_scope_completion_not_global_fact(self):
        feed = build_events(self.merge(envelope(scope='unknown')))
        self.assertEqual(feed['event_stats']['total'], 0)
        self.assertEqual(feed['records'][0]['status'], 'uncertain')

    def test_explicit_scope_delivered_counts(self):
        feed = build_events(self.merge(envelope()))
        self.assertEqual(feed['event_stats']['total'], 1)

    def test_manual_confirmation_cannot_be_downgraded(self):
        row = self.merge(envelope())['records'][0]
        row['reset_confirmation'] = {'method': 'private_reset_report', 'reset_at': '2026-09-13T00:10:00Z'}
        feed = self.merge(envelope(signal='announced'), [row])
        self.assertEqual(feed['records'][0]['status'], 'announced')
        self.assertEqual(feed['records'][0]['reset_confirmation'], row['reset_confirmation'])

    def test_historical_unchanged_even_irrelevant(self):
        row = self.merge(envelope())['records'][0]
        row['historical_verification'] = {'method': 'site_owner_verified_history'}
        feed = self.merge(envelope(signal='none', relevance='none'), [row])
        self.assertEqual(feed['records'][0]['status'], 'announced')

    def test_reanalysis_removes_unverified_model_entry(self):
        row = self.merge(envelope(signal='announced'))['records'][0]
        self.assertEqual(self.merge(envelope(signal='none', relevance='none'), [row])['records'], [])

    def test_watch_suppressed_by_actual_reset(self):
        env = envelope(signal='hint')
        record = self.merge(envelope())['records'][0]
        record['id'] = OLD
        record['reset_confirmation'] = {'method': 'private_reset_report', 'reset_at': '2026-09-13T00:10:00Z'}
        view = make_watch({'records': [record]}, {'posts': {ID: post()}}, {ID: env}, {}, {}, NOW)
        self.assertIsNone(view['watch'])

    def test_watch_and_votes_not_model_probability(self):
        view = make_watch({'records': []}, {'posts': {ID: post()}}, {ID: envelope(signal='hint')}, {}, {}, NOW)
        self.assertEqual(view['watch']['analysis']['prediction']['outlook'], 'unknown')
        self.assertNotIn('yes_percent', view['watch'])
        self.assertNotIn('probability', view['watch']['analysis'])

    def test_related_model_records_group_without_keyword_recheck(self):
        older = self.merge(envelope(signal='announced'))['records'][0]
        older['id'] = OLD; older['announced_at'] = '2026-09-12T20:00:00Z'
        env = envelope(); env['result']['related_post_id'] = OLD
        feed = build_events(self.merge(env, [older]))
        self.assertEqual(len(feed['events']), 1)
        self.assertEqual(feed['event_stats']['total'], 1)

    def test_two_private_confirmed_resets_cannot_be_regrouped_by_model(self):
        older = self.merge(envelope())['records'][0]
        older.update(id=OLD, source_url=post(OLD)['source_url'], announced_at='2026-09-12T20:00:00+00:00')
        newer = self.merge(envelope())['records'][0]
        for row in (older, newer):
            row['reset_confirmation'] = {'method': 'private_reset_report', 'kind': 'official',
                                         'reset_at': row['announced_at'], 'watch_episode_id': row['id']}
        original_times = {row['id']: row['reset_confirmation']['reset_at'] for row in (older, newer)}
        env = envelope(signal='announced')
        env['result']['related_post_id'] = OLD
        feed = build_events(self.merge(env, [older, newer]))
        self.assertEqual(len(feed['events']), 2)
        self.assertEqual(feed['event_stats']['total'], 2)
        self.assertEqual({row['id']: row['reset_confirmation']['reset_at'] for row in feed['records']}, original_times)
        self.assertTrue(all(len(event['record_ids']) == 1 for event in feed['events']))

    def test_new_followup_to_private_confirmed_reset_does_not_count_twice(self):
        older = self.merge(envelope())['records'][0]
        older.update(id=OLD, source_url=post(OLD)['source_url'], announced_at='2026-09-12T20:00:00+00:00')
        older['reset_confirmation'] = {'method': 'private_reset_report', 'kind': 'official',
                                        'reset_at': '2026-09-12T20:10:00Z', 'watch_episode_id': OLD}
        env = envelope(); env['result']['related_post_id'] = OLD
        feed = build_events(self.merge(env, [older]))
        self.assertEqual([row['id'] for row in feed['records']], [OLD])
        self.assertEqual(feed['event_stats']['total'], 1)
        self.assertEqual(feed['records'][0]['reset_confirmation'], older['reset_confirmation'])

    def test_existing_followup_cannot_double_count_after_private_confirmation(self):
        older = self.merge(envelope(signal='announced'))['records'][0]
        older.update(id=OLD, source_url=post(OLD)['source_url'], announced_at='2026-09-12T20:00:00+00:00')
        env = envelope(); env['result']['related_post_id'] = OLD
        before = build_events(self.merge(env, [older]))
        self.assertEqual(before['event_stats']['total'], 1)
        confirmed = next(row for row in before['records'] if row['id'] == OLD)
        confirmed['reset_confirmation'] = {'method': 'private_reset_report', 'kind': 'official',
                                             'reset_at': '2026-09-12T20:10:00Z', 'watch_episode_id': OLD}
        after = build_events(self.merge(env, before['records']))
        self.assertEqual(after['event_stats']['total'], 1)
        self.assertEqual([row['id'] for row in after['records']], [OLD])
        self.assertEqual(after['records'][0]['reset_confirmation'], confirmed['reset_confirmation'])

    def test_banked_issuance_does_not_close_unrelated_regular_watch(self):
        banked = self.merge(envelope(kind='banked'))['records'][0]
        banked.update(id=OLD, source_url=post(OLD)['source_url'], announced_at='2026-09-13T00:30:00+00:00')
        feed = build_events({'records': [banked]})
        view = make_watch(feed, {'posts': {ID: post()}}, {ID: envelope(signal='hint')}, {}, {}, NOW)
        self.assertEqual(view['watch']['reset_type'], 'regular')
        self.assertEqual(watch_state(view['watch'], feed, NOW), 'active')
        # The real same-kind delivery still closes the watch.
        feed['events'][0]['reset_type'] = 'regular'
        self.assertEqual(watch_state(view['watch'], feed, NOW), 'new_announcement')

    def test_linked_banked_issuance_does_not_override_regular_watch(self):
        followup = str(int(ID) + 1)
        banked = envelope(kind='banked', ident=followup)
        banked['result']['related_post_id'] = ID
        archive = {'posts': {ID: post(), followup: post(followup, '2026-09-13T00:30:00+00:00')}}
        view = make_watch({'records': []}, archive, {ID: envelope(signal='hint'), followup: banked}, {}, {}, NOW)
        self.assertEqual(view['watch']['episode_id'], ID)

    def test_reanalysis_unknown_type_withdraws_unverified_delivered_entry(self):
        row = self.merge(envelope())['records'][0]
        feed = build_events(self.merge(envelope(kind='unknown'), [row]))
        self.assertEqual(feed['records'], [])
        self.assertEqual(feed['event_stats']['total'], 0)
        # The same uncertain interpretation cannot erase a private fact.
        row['reset_confirmation'] = {'method': 'private_reset_report', 'reset_at': '2026-09-13T00:10:00Z'}
        self.assertEqual(self.merge(envelope(kind='unknown'), [row])['records'][0]['status'], 'announced')

    def test_missing_current_result_never_revives_watch_after_linked_denial(self):
        prior = make_watch({'records': []}, {'posts': {ID: post()}}, {ID: envelope(signal='hint')}, {}, {}, NOW)
        followup = str(int(ID) + 1)
        denied = envelope(signal='denied', ident=followup)
        denied['result']['related_post_id'] = ID
        archive = {'posts': {ID: post(), followup: post(followup, '2026-09-13T00:30:00+00:00')}}
        # Source is unchanged, but the prior result is unavailable/pending. The
        # previously published card must not bypass current closure decisions.
        view = make_watch({'records': []}, archive, {followup: denied}, {}, prior, NOW)
        self.assertIsNone(view['watch'])
        # A linked denial also closes a currently validated hint.
        view = make_watch({'records': []}, archive, {ID: envelope(signal='hint'), followup: denied}, {}, prior, NOW)
        self.assertIsNone(view['watch'])

if __name__ == '__main__':
    unittest.main()
