"""The reading list must not change the authoritative reset-event ledger."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ai_publication as publication
from announcement_semantics import build_events
from historical_baseline import create_baseline
from reset_watch import watch_state
from test_ai_publication import ID, OLD, NOW, envelope, post


def confirmed_record():
    row = publication.apply_decisions({'records': []}, {'posts': {OLD: post(OLD)}},
                                      {OLD: envelope(ident=OLD)}, NOW)['records'][0]
    row['announced_at'] = '2026-09-12T20:00:00Z'
    row['reset_confirmation'] = {'method': 'private_reset_report', 'kind': 'official',
                                  'reset_at': '2026-09-12T20:10:00Z', 'watch_episode_id': OLD}
    return row


class AnnouncementDisplayTests(unittest.TestCase):
    def test_followup_is_readable_without_changing_confirmed_event_or_actual_time(self):
        original = confirmed_record()
        env = envelope()
        env['result']['related_post_id'] = OLD
        archive = {'posts': {ID: post()}}
        feed = build_events(publication.apply_decisions({'records': [original]}, archive, {ID: env}, NOW))
        before = copy.deepcopy(feed)
        self.assertEqual([row['id'] for row in feed['records']], [OLD])
        display = publication.build_announcements(feed, archive, {ID: env})
        self.assertEqual([row['id'] for row in display], [ID, OLD])
        self.assertEqual(feed, before)
        self.assertEqual(feed['event_stats']['total'], 1)
        self.assertEqual(feed['records'][0]['reset_confirmation'], original['reset_confirmation'])
        for row in display:
            for field in ('status', 'reset_type', 'confirmation', 'reset_confirmation', 'event_id', 'related_record_ids'):
                self.assertNotIn(field, row)
        display[1]['source_text'] = 'Changing display memory must not mutate the ledger.'
        self.assertEqual(feed, before)

    def test_hint_unknown_type_and_denial_display_but_irrelevant_or_personal_do_not(self):
        cases = [
            ('hint', 'unknown', 'reset', 'unknown', True),
            ('announced', 'global', 'reset', 'regular', True),
            ('in_progress', 'group', 'reset', 'banked', True),
            ('delivered', 'global', 'reset', 'regular', True),
            ('denied', 'global', 'reset', 'unknown', True),
            ('none', 'unknown', 'none', 'unknown', False),
            ('hint', 'personal', 'reset', 'regular', False),
        ]
        for signal, scope, relevance, kind, expected in cases:
            with self.subTest(signal=signal, scope=scope):
                env = envelope(signal=signal, scope=scope, relevance=relevance, kind=kind)
                display = publication.build_announcements({'records': []}, {'posts': {ID: post()}}, {ID: env})
                self.assertEqual(bool(display), expected)
        env = envelope(signal='hint'); env['result']['evidence'] = []
        self.assertFalse(publication.build_announcements({'records': []}, {'posts': {ID: post()}}, {ID: env}))

    def test_observed_duplicate_deduplicates_by_source_without_deleting_history(self):
        original = confirmed_record()
        observed = dict(original, id='observed-' + OLD, source_type='observed')
        feed = {'records': [original, observed]}
        before = copy.deepcopy(feed)
        display = publication.build_announcements(feed, {'posts': {}}, {})
        self.assertEqual([row['id'] for row in display], [OLD])
        self.assertEqual(feed, before)

    def test_publisher_hydrates_followup_translation_and_screenshot_without_event_change(self):
        archive = {'posts': {ID: post()}}
        env = envelope(); env['result']['related_post_id'] = OLD
        body = post()['text']; digest = hashlib.sha256(body.encode()).hexdigest()
        shot = {'file': ID + '-' + 'a' * 16 + '.jpg', 'sha256': 'a' * 64,
                'source_url': post()['source_url'], 'captured_at': NOW.isoformat(), 'width': 800, 'height': 400}
        manifest = {'posts': {ID: {'status': 'ready', 'full_text': body, 'full_text_sha256': digest,
                                  'text_captured_at': NOW.isoformat(), 'screenshot': shot}}}
        original = confirmed_record(); original.pop('reset_confirmation')
        seeded = {'schema_version': 1, 'records': [original]}
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder); analysis = state / 'analysis'; analysis.mkdir()
            for name, value in [('data.json', seeded), ('activity-archive.json', archive), ('post-content.json', manifest),
                                ('historical-baseline.json', create_baseline(seeded, NOW.isoformat()))]:
                (state / name).write_text(json.dumps(value), encoding='utf-8')
            with patch.object(publication, 'load_envelopes', return_value=({ID: env}, [])):
                with patch.object(publication, 'build_announcements', return_value=[]):
                    control = publication.publish_ai(state, analysis_dir=analysis, now=NOW)
                actual = publication.publish_ai(state, analysis_dir=analysis, now=NOW)
            for field in ('records', 'events', 'event_stats', 'stats'):
                self.assertEqual(actual[field], control[field])
            self.assertEqual(actual['event_stats']['total'], 1)
            latest = actual['announcements'][0]
            self.assertEqual(latest['id'], ID)
            self.assertEqual(latest['full_text'], body)
            self.assertEqual(latest['translation_zh']['text'], env['result']['translation_zh'])
            self.assertEqual(latest['translation_zh']['source_sha256'], latest['full_text_sha256'])
            self.assertEqual(latest['brief']['zh']['summary'], env['result']['summary_zh'])
            self.assertEqual(latest['screenshot'], shot)
            self.assertEqual(json.loads((state / 'data.json').read_text(encoding='utf-8')), actual)

    def test_nonmatching_model_summary_cannot_replace_display_brief(self):
        row = {'id': ID, 'full_text_sha256': '0' * 64, 'brief': {'method': 'archived'}}
        publication.attach_model_briefs({'records': [row]}, {ID: envelope()})
        self.assertEqual(row['brief'], {'method': 'archived'})


class WatchUntilResetTests(unittest.TestCase):
    def view(self, signal='announced', now=NOW, records=None, closures=None):
        archive = {'posts': {ID: post()}}
        envs = {ID: envelope(signal=signal)}
        feed = build_events(publication.apply_decisions({'records': records or []}, archive, envs, now))
        result = publication.make_watch(feed, archive, envs, {}, {}, now, closures)
        return result, feed

    def test_planned_and_in_progress_windows_remain_active_after_three_days(self):
        for signal in ('hint', 'announced', 'in_progress'):
            for delta in (dt.timedelta(hours=26), dt.timedelta(days=3)):
                with self.subTest(signal=signal, delta=delta):
                    now = NOW + delta
                    result, feed = self.view(signal, now)
                    hint = result['watch']
                    self.assertIsNotNone(hint)
                    self.assertEqual(hint['window_basis'], 'until_reset_confirmed')
                    self.assertEqual(hint['expires_at'], '2026-09-14T00:00:00+00:00')
                    self.assertEqual(watch_state(hint, feed, now), 'active')
                    self.assertEqual(feed['event_stats']['total'], 0)

    def test_long_running_window_closes_only_on_confirmation_or_explicit_closure(self):
        now = NOW + dt.timedelta(days=3)
        record = confirmed_record()
        record['reset_confirmation']['reset_at'] = (now - dt.timedelta(minutes=5)).isoformat()
        self.assertIsNone(self.view(now=now, records=[record])[0]['watch'])
        self.assertIsNone(self.view(now=now, closures={'episodes': {ID: {'reason': 'owner_confirmed_reset'}}})[0]['watch'])
        result, feed = self.view(now=now)
        feed['events'] = [{'status': 'announced', 'reset_type': 'regular', 'announced_at': now.isoformat()}]
        self.assertEqual(watch_state(result['watch'], feed, now), 'new_announcement')

    def test_newer_watch_after_last_actual_reset_can_start(self):
        result, feed = self.view(records=[confirmed_record()])
        self.assertEqual(result['watch']['episode_id'], ID)
        self.assertEqual(watch_state(result['watch'], feed, NOW), 'active')

    def test_legacy_window_keeps_fixed_expiry(self):
        result, feed = self.view()
        result['watch']['window_basis'] = 'site_observation_window'
        self.assertEqual(watch_state(result['watch'], feed, NOW + dt.timedelta(days=2)), 'expired')


if __name__ == '__main__':
    unittest.main()
