import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from translate_posts import translate_pending
from post_briefs import extract


class TranslationTests(unittest.TestCase):
    def setup_state(self, folder):
        path = Path(folder)
        body = 'We will reset usage for all paid users.\n\nNo action is required.'
        digest = hashlib.sha256(body.encode()).hexdigest()
        (path / 'post-content.json').write_text(json.dumps({'posts': {'123': {'full_text': body, 'full_text_sha256': digest, 'status': 'text_ready'}}}))
        return path, body, digest

    def test_new_full_text_is_translated_once_and_bound_to_hash(self):
        class Engine:
            def translate(self, body):
                return '我们将为所有付费用户重置额度。\n\n无需操作。'
        with tempfile.TemporaryDirectory() as directory:
            state, body, digest = self.setup_state(directory)
            self.assertEqual(translate_pending(state, Engine)['translated'], ['123'])
            output = json.loads((state / 'post-translations.zh.json').read_text(encoding='utf-8'))
            self.assertEqual(output['123']['source_sha256'], digest)
            self.assertEqual(translate_pending(state, lambda: self.fail('Matching translation must not re-run'))['translated'], [])

    def test_translation_failure_cannot_change_source_or_publish_success(self):
        class Engine:
            def translate(self, body):
                raise RuntimeError('Engine unavailable')
        with tempfile.TemporaryDirectory() as directory:
            state, body, digest = self.setup_state(directory)
            before = (state / 'post-content.json').read_bytes()
            with self.assertRaises(RuntimeError):
                translate_pending(state, Engine)
            self.assertFalse((state / 'post-translations.zh.json').exists())
            self.assertEqual((state / 'post-content.json').read_bytes(), before)

    def test_extracted_summary_keeps_future_and_eligibility_qualifiers(self):
        body = 'Some Plus users will receive a banked reset later today. If you upgrade before 8pm PT you will qualify.'
        result = extract(body)
        self.assertEqual(result['summary'], 'Some Plus users will receive a banked reset later today.')
        self.assertTrue(result['action'].startswith('If you upgrade'))

    def test_parenthetical_punctuation_does_not_cut_source_sentence(self):
        body = '你们很有耐心（其实并没有，不过没关系！）所以我们将为部分用户发放重置卡。今晚结束前完成。'
        self.assertEqual(extract(body, True)['summary'], body.split('。')[0] + '。')
