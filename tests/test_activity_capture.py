import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import capture_posts

FIRST = '2098612714704891959'
SECOND = '2098612714704891960'


def post(key, text='Unrelated product news.'):
    return {'id': key, 'author': 'thsottiaux', 'text': text,
            'source_url': 'https://x.com/thsottiaux/status/' + key,
            'announced_at': '2026-09-13T00:00:00+00:00',
            'source_text_sha256': hashlib.sha256(text.encode()).hexdigest()}


class ActivityCaptureTests(unittest.TestCase):
    def test_all_activity_merges_once_newest_first_and_retains_cached_capture(self):
        first, second = post(FIRST), post(SECOND)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            filename = FIRST + '-' + 'a' * 16 + '.jpg'
            (root / filename).write_bytes(b'original capture fixture')
            docs = {FIRST: {'status': 'ready', 'full_text': first['text'],
                            'screenshot': {'file': filename, 'height': 300, 'capture_version': 2}}}
            feed = {'records': [first, dict(first)]}
            archive = {'posts': {FIRST: first, SECOND: second}}
            jobs = capture_posts.capture_jobs(feed, archive, docs, root, now=0)
            self.assertEqual([key for key, row in jobs], [SECOND])
            self.assertTrue(jobs[0][1]['activity_archive'])
            jobs = capture_posts.capture_jobs(feed, archive, {}, root, now=0)
            self.assertEqual([key for key, row in jobs], [SECOND, FIRST])

    def test_changed_text_requeues_capture_and_unsafe_paths_never_satisfy_cache(self):
        record = post(FIRST, 'Updated source text.')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            previous = {'status': 'ready', 'full_text': 'Old source text.', 'retry_after': 99999,
                        'discovery_text_sha256': hashlib.sha256(b'Old source text.').hexdigest(),
                        'screenshot': {'file': '../outside.jpg'}}
            jobs = capture_posts.capture_jobs({}, {'posts': {FIRST: record}}, {FIRST: previous}, root, now=0)
            self.assertEqual([key for key, row in jobs], [FIRST])
            previous['discovery_text_sha256'] = record['source_text_sha256']
            self.assertEqual(capture_posts.capture_jobs({}, {'posts': {FIRST: record}}, {FIRST: previous}, root, now=0), [])
            previous.pop('retry_after')
            self.assertEqual(len(capture_posts.capture_jobs({}, {'posts': {FIRST: record}}, {FIRST: previous}, root, now=0)), 1)

    def test_signal_after_each_ready_capture_and_never_after_failed_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'activity-archive.json').write_text(json.dumps({'posts': {FIRST: post(FIRST), SECOND: post(SECOND)}}))
            calls = []
            def capture(page, record, image_dir, on_text):
                calls.append('capture:' + record['id'])
                on_text({'status': 'text_ready', 'full_text': record['text']})
                if record['id'] == FIRST:
                    raise TimeoutError('Screenshot could not be captured')
                return {'status': 'ready', 'full_text': record['text'], 'screenshot': {'file': record['id'] + '-test.jpg'}}
            def signal(state):
                manifest = json.loads((state / 'post-content.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['posts'][SECOND]['status'], 'ready')
                calls.append('signal')
            with patch.object(capture_posts, 'sync_playwright'), patch.object(capture_posts, 'capture', side_effect=capture), \
                 patch.object(capture_posts, 'signal_ai_ready', side_effect=signal), patch.object(capture_posts.time, 'sleep'), \
                 patch('thumbnails.build_thumbnails'):
                capture_posts.main(2, root)
            self.assertEqual(calls, ['capture:' + SECOND, 'signal', 'capture:' + FIRST])
            content = json.loads((root / 'post-content.json').read_text(encoding='utf-8'))['posts']
            self.assertEqual(content[FIRST]['status'], 'text_ready')
            self.assertGreater(content[FIRST]['retry_after'], 0)

    def test_archive_author_or_url_mismatch_never_becomes_capture_job(self):
        rows = [dict(post(FIRST), author='another_user'),
                dict(post(SECOND), source_url='https://x.com/another_user/status/' + SECOND)]
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(capture_posts.capture_jobs({}, {'posts': {str(i): row for i, row in enumerate(rows)}}, {}, Path(folder)), [])

    def test_low_disk_pauses_before_browser_and_preserves_old_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = json.dumps({'posts': {FIRST: post(FIRST)}}).encode()
            (root / 'activity-archive.json').write_bytes(archive)
            old = {'posts': {SECOND: {'full_text': 'Previously archived original', 'status': 'ready'}}}
            (root / 'post-content.json').write_text(json.dumps(old))
            with patch.object(capture_posts.shutil, 'disk_usage', return_value=SimpleNamespace(free=500 * 1024 * 1024)), \
                 patch.object(capture_posts, 'sync_playwright') as browser:
                capture_posts.main(2, root)
                browser.assert_not_called()
            result = json.loads((root / 'post-content.json').read_text(encoding='utf-8'))
            self.assertEqual(result['posts'], old['posts'])
            self.assertEqual(result['capture_error']['code'], 'storage_low')
            self.assertEqual((root / 'activity-archive.json').read_bytes(), archive)
            self.assertFalse((root / 'ai-ready.signal').exists())
            with patch.object(capture_posts.shutil, 'disk_usage', return_value=SimpleNamespace(free=700 * 1024 * 1024)):
                self.assertTrue(capture_posts.storage_ready(root, result, root / 'post-content.json'))
            self.assertNotIn('capture_error', json.loads((root / 'post-content.json').read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
