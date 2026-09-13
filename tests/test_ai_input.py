import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ai_analysis import input_fingerprint, make_input
from ai_input import prepare_inputs
from test_ai_analysis import ID, setup_source, write_json


class InputBrokerTests(unittest.TestCase):
    def test_only_public_whitelisted_inputs_are_copied_and_fingerprint_survives(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as dest:
            post, content = setup_source(folder)
            post['private_token'] = 'SECRET'
            content['private_note'] = 'SECRET'
            post['reply_context'] = {'author': 'someone', 'text': 'test', 'source_url': 'https://x.com/someone/status/12345678901', 'cookie': 'SECRET'}
            write_json(Path(folder) / 'activity-archive.json', {'posts': {ID: post}, 'private': 'SECRET'})
            write_json(Path(folder) / 'post-content.json', {'posts': {ID: content}})
            write_json(Path(folder) / 'private-reports.json', {'token': 'SECRET'})
            source = make_input(ID, post, content, folder)
            report = prepare_inputs(folder, dest)
            self.assertEqual(report['ready'], 1)
            self.assertTrue(report['changed'])
            archive = json.loads((Path(dest) / 'activity-archive.json').read_text())
            manifest = json.loads((Path(dest) / 'post-content.json').read_text())
            mirrored = make_input(ID, archive['posts'][ID], manifest['posts'][ID], dest)
            self.assertEqual(input_fingerprint(source), input_fingerprint(mirrored))
            self.assertFalse((Path(dest) / 'private-reports.json').exists())
            self.assertNotIn('SECRET', (Path(dest) / 'activity-archive.json').read_text())
            self.assertNotIn('SECRET', (Path(dest) / 'post-content.json').read_text())
            self.assertFalse(prepare_inputs(folder, dest)['changed'])

    def test_stale_capture_remains_pending_without_sending_excerpt(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as dest:
            post, content = setup_source(folder)
            post['source_text_sha256'] = 'a' * 64
            write_json(Path(folder) / 'activity-archive.json', {'posts': {ID: post}})
            report = prepare_inputs(folder, dest)
            self.assertEqual(report['pending'], 1)
            copied = json.loads((Path(dest) / 'post-content.json').read_text())['posts'][ID]
            self.assertEqual(copied, {'status': 'pending', 'error_code': 'source_changed'})

    def test_only_media_only_original_image_is_copied(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as dest:
            post, content = setup_source(folder, '')
            raw = b'Frozen original screenshot'
            digest = hashlib.sha256(raw).hexdigest()
            name = ID + '-' + digest[:16] + '.jpg'
            (Path(folder) / 'post-images').mkdir()
            (Path(folder) / 'post-images' / name).write_bytes(raw)
            (Path(folder) / 'post-images' / 'unrelated.jpg').write_bytes(b'not copied')
            content.update(status='ready', media_only=True, screenshot={'file': name, 'sha256': digest})
            write_json(Path(folder) / 'post-content.json', {'posts': {ID: content}})
            self.assertEqual(prepare_inputs(folder, dest)['media_images_copied'], 1)
            self.assertEqual((Path(dest) / 'post-images' / name).read_bytes(), raw)
            self.assertFalse((Path(dest) / 'post-images' / 'unrelated.jpg').exists())
            self.assertEqual(prepare_inputs(folder, dest)['media_images_copied'], 0)


if __name__ == '__main__':
    unittest.main()
