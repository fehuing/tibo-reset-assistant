"""All-activity discovery must not inherit reset keyword filtering."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from activity_ingest import PROFILE, SURFACES, atomic_json, collect_activity
from x_public import public_posts

NOW = dt.datetime(2026, 9, 13, 1, tzinfo=dt.timezone.utc)
FIRST = '2098612714704891959'
SECOND = '2098612714704891960'
OTHER = '2098612714704891961'


def graph(rows):
    chunks = []
    for row in rows:
        key = row['id']
        author = row.get('author', 'thsottiaux')
        def node(name, content):
            chunks.append('{__id:"' + name + '",' + content + '}')
        extra = ''
        if row.get('reply_to_id'):
            extra += ',reply_to_results:{__ref:"reply-' + key + '"}'
            node('reply-' + key, 'rest_id:' + json.dumps(row['reply_to_id']))
        if row.get('quoted_id'):
            extra += ',quoted_tweet_results:{__ref:"quote-' + key + '"}'
            node('quote-' + key, 'result:{__ref:"tweet-' + row['quoted_id'] + '"}')
        if row.get('has_media'):
            extra += ',media_entities2:{__refs:["media-' + key + '"]}'
        node('tweet-' + key, '__typename:"Tweet",rest_id:' + json.dumps(key) +
             ',core:{__ref:"core-' + key + '"},details:{__ref:"details-' + key + '"}' + extra)
        node('core-' + key, 'user_results:{__ref:"user-result-' + key + '"}')
        node('user-result-' + key, 'result:{__ref:"user-' + key + '"}')
        node('user-' + key, 'core:{__ref:"user-core-' + key + '"}')
        node('user-core-' + key, 'screen_name:' + json.dumps(author))
        node('details-' + key, 'full_text:' + json.dumps(row.get('text', '')) + ',created_at_ms:1789260000000')
    return ','.join(chunks)


class ActivityIngestTests(unittest.TestCase):
    def test_unrelated_original_reply_and_quote_are_archived_with_author_binding(self):
        document = graph([
            {'id': FIRST, 'text': 'Lovely weather for a walk.', 'quoted_id': OTHER},
            {'id': SECOND, 'text': 'Thank you for the photos!', 'reply_to_id': OTHER},
            {'id': OTHER, 'author': 'someone_else', 'text': 'Here are the photos.'},
        ])
        with tempfile.TemporaryDirectory() as folder:
            result = collect_activity(Path(folder), now=NOW, get=lambda url: document)
            self.assertEqual(set(result['posts']), {FIRST, SECOND})
            self.assertEqual(result['posts'][SECOND]['reply_context']['author'], 'someone_else')
            self.assertEqual(result['posts'][FIRST]['quoted_context']['text'], 'Here are the photos.')
            self.assertEqual(result['posts'][FIRST]['first_seen_at'], NOW.isoformat())
            self.assertEqual(result['posts'][FIRST]['discovered_via'], sorted(SURFACES))
            self.assertNotIn('signal', result['posts'][FIRST])
            self.assertFalse(result['coverage']['complete'])

    def test_partial_and_total_failure_retain_old_posts_and_report_gap(self):
        document = graph([{'id': FIRST, 'text': 'A normal product update.'}])
        def partial(url):
            if url.endswith('/with_replies'):
                raise urllib.error.HTTPError(url, 429, 'Rate limited', {}, None)
            return document
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = collect_activity(root, now=NOW, get=partial)
            self.assertEqual(first['coverage']['status'], 'partial')
            self.assertEqual(first['coverage']['errors'][0]['code'], 'x_rate_limited')
            def unavailable(url):
                raise TimeoutError('offline')
            second = collect_activity(root, now=NOW + dt.timedelta(minutes=2), get=unavailable)
            self.assertEqual(second['posts'], first['posts'])
            self.assertEqual(second['coverage']['status'], 'unavailable')
            self.assertEqual(second['coverage']['last_success_at'], NOW.isoformat())

    def test_manual_link_verified_no_tracker_api_and_first_seen_preserved(self):
        document = graph([{'id': FIRST, 'text': 'A normal product update.'}])
        direct = PROFILE + '/status/' + SECOND
        direct_doc = graph([{'id': SECOND, 'text': 'A separate reply.', 'reply_to_id': OTHER},
                            {'id': OTHER, 'text': 'Parent', 'author': 'another_user'}])
        calls = []
        def get(url):
            calls.append(url)
            return direct_doc if url == direct else document
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_json(root / 'watch-config.json', {'reference_discovery': True, 'source_urls': [direct, 'https://evil.invalid/']})
            first = collect_activity(root, now=NOW, get=get)
            second = collect_activity(root, now=NOW + dt.timedelta(minutes=2), get=get)
            self.assertEqual(set(second['posts']), {FIRST, SECOND})
            self.assertEqual(second['posts'][SECOND]['first_seen_at'], NOW.isoformat())
            self.assertEqual(second['posts'][SECOND]['last_seen_at'], (NOW + dt.timedelta(minutes=2)).isoformat())
            self.assertTrue(all(url.startswith(PROFILE) for url in calls))
            self.assertEqual(first['coverage']['new_posts'], 2)
            self.assertEqual(second['coverage']['new_posts'], 0)

    def test_media_only_kept_without_invented_source_text(self):
        posts = public_posts(graph([{'id': FIRST, 'has_media': True}, {'id': SECOND}]))
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['text'], '')
        self.assertTrue(posts[0]['media_only'])
        with tempfile.TemporaryDirectory() as folder:
            result = collect_activity(Path(folder), now=NOW, get=lambda url: graph([{'id': FIRST, 'has_media': True}]))
            self.assertTrue(result['posts'][FIRST]['media_only'])

    def test_permalink_only_surface_is_verified_on_original_page(self):
        source = PROFILE + '/status/' + FIRST
        calls = []
        def get(url):
            calls.append(url)
            return graph([{'id': FIRST, 'text': 'No reset words at all.'}]) if url == source else '<a href="/thsottiaux/status/' + FIRST + '">Post</a>'
        with tempfile.TemporaryDirectory() as folder:
            result = collect_activity(Path(folder), now=NOW, get=get)
            self.assertIn(FIRST, result['posts'])
            self.assertEqual(calls.count(source), 1)
            self.assertEqual(result['coverage']['status'], 'partial')

    def test_corrupt_archive_is_not_replaced_and_large_archive_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'activity-archive.json'
            path.write_text('{incomplete', encoding='utf-8')
            with self.assertRaises(ValueError):
                collect_activity(root, now=NOW, get=lambda url: '')
            self.assertEqual(path.read_text(encoding='utf-8'), '{incomplete')
            atomic_json(path, {'posts': {}, 'audit_padding': 'a' * (2 * 1024 * 1024)})
            self.assertGreater(path.stat().st_size, 2 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
