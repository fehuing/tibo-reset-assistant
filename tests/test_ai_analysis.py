import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_analysis import (AnalysisError, MODEL, PROMPT_VERSION, analyze_pending,
                         DISABLED_CODE_MODE_NOTICE, input_fingerprint, make_input,
                         validate_events, validate_result)


NOW = dt.datetime(2026, 9, 13, tzinfo=dt.timezone.utc)
ID = '2098612714704891959'
PARENT_ID = '2098300424520687965'


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def setup_source(folder, text='We will reset Codex usage for all paid users. It has not happened yet.', post_id=ID):
    path = Path(folder)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    post = {'id': post_id, 'author': 'thsottiaux', 'source_url': 'https://x.com/thsottiaux/status/' + post_id,
            'text': text, 'source_text_sha256': digest, 'announced_at': '2026-09-12T03:20:36Z',
            'first_seen_at': '2026-09-12T03:21:00Z', 'reply_to_id': None, 'quoted_id': None}
    content = {'full_text': text, 'full_text_sha256': digest, 'status': 'text_ready',
               'source_url': post['source_url'], 'text_source': 'x_post_page',
               'discovery_text_sha256': digest, 'author_verified': True, 'text_complete': True}
    write_json(path / 'activity-archive.json', {'posts': {post_id: post}})
    write_json(path / 'post-content.json', {'posts': {post_id: content}})
    return post, content


def result_for(source, unrelated=False):
    return {'schema_version': 1, 'id': source['id'], 'source_sha256': source['source_sha256'],
            'translation_zh': '我们将为所有付费用户重置 Codex 额度，目前尚未发生。',
            'summary_zh': '宣布未来重置，目前尚未发生。', 'summary_en': 'A future reset is announced but has not happened.',
            'relevance': 'none' if unrelated else 'reset', 'signal': 'none' if unrelated else 'announced',
            'scope': 'unknown' if unrelated else 'global', 'reset_type': 'unknown' if unrelated else 'regular',
            'evidence': [] if unrelated else [source['text']], 'related_post_id': None, 'reset_at': None,
            'prediction': {'outlook': 'unknown' if unrelated else 'likely', 'reason_zh': '作者明确预告，仍需等待确认。', 'reason_en': 'An explicit promise still awaits confirmation.'}}


class WorkerTests(unittest.TestCase):
    def test_unrelated_post_translates_but_cannot_modify_public_or_source_data(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as output:
            post, content = setup_source(folder, 'Happy weekend, Codex friends!')
            sentinel = {'records': [{'id': ID, 'status': 'confirmed', 'manual': True}]}
            write_json(Path(folder) / 'data.json', sentinel)
            write_json(Path(folder) / 'watch.json', {'watch': None})
            before = {file.name: file.read_bytes() for file in Path(folder).iterdir()}
            class Runner:
                def analyze(self, source, timeout):
                    result = result_for(source, unrelated=True)
                    result.update(translation_zh='Codex 的朋友们，周末愉快！', summary_zh='向 Codex 用户问候周末。', summary_en='A weekend greeting to Codex users.')
                    return result
            report = analyze_pending(folder, output, Runner(), now=NOW)
            self.assertEqual(report['completed'], [ID])
            for name, raw in before.items():
                self.assertEqual((Path(folder) / name).read_bytes(), raw)
            result = json.loads((Path(output) / 'results' / (ID + '.json')).read_text(encoding='utf-8'))
            self.assertEqual(result['result']['relevance'], 'none')
            self.assertEqual(result['model'], MODEL)
            self.assertEqual(result['prompt_version'], PROMPT_VERSION)
            self.assertEqual(result['status'], 'ready')

    def test_hash_and_context_cache_skip_only_identical_completed_input(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as output:
            post, content = setup_source(folder)
            calls = []
            class Runner:
                def analyze(self, source, timeout):
                    calls.append(source)
                    return result_for(source)
            analyze_pending(folder, output, Runner(), now=NOW)
            second = analyze_pending(folder, output, Runner(), now=NOW)
            self.assertEqual(second['cached'], 1)
            self.assertEqual(len(calls), 1)
            post['reply_to_id'] = PARENT_ID
            post['reply_context'] = {'author': 'someone', 'text': 'Will Codex reset?', 'source_url': 'https://x.com/someone/status/' + PARENT_ID}
            write_json(Path(folder) / 'activity-archive.json', {'posts': {ID: post}})
            analyze_pending(folder, output, Runner(), now=NOW)
            self.assertEqual(len(calls), 2)

    def test_source_changes_during_model_call_are_discarded(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as output:
            setup_source(folder)
            class Runner:
                def analyze(self, source, timeout):
                    setup_source(folder, 'The Codex reset has been cancelled.')
                    return result_for(source)
            report = analyze_pending(folder, output, Runner(), now=NOW)
            self.assertEqual(report['completed'], [])
            self.assertEqual(report['failures'][0]['error_code'], 'source_changed_during_analysis')
            self.assertFalse((Path(output) / 'results' / (ID + '.json')).exists())

    def test_failure_does_not_starve_another_post_and_retry_backoff_is_safe(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as output:
            post, content = setup_source(folder)
            newer = str(int(ID) + 1)
            second_post = dict(post, id=newer, source_url='https://x.com/thsottiaux/status/' + newer)
            second_content = dict(content, source_url=second_post['source_url'])
            write_json(Path(folder) / 'activity-archive.json', {'posts': {ID: post, newer: second_post}})
            write_json(Path(folder) / 'post-content.json', {'posts': {ID: content, newer: second_content}})
            called = []
            class Runner:
                def analyze(self, source, timeout):
                    called.append(source['id'])
                    if source['id'] == newer:
                        raise RuntimeError('PRIVATE AUTH TOKEN MUST NEVER APPEAR')
                    return result_for(source)
            report = analyze_pending(folder, output, Runner(), now=NOW)
            self.assertEqual(called, [newer, ID])
            self.assertEqual(report['completed'], [ID])
            self.assertEqual(report['failures'], [{'id': newer, 'error_code': 'analysis_failed'}])
            analyze_pending(folder, output, Runner(), now=NOW + dt.timedelta(seconds=119))
            self.assertEqual(len(called), 2)
            self.assertNotIn('PRIVATE', (Path(output) / 'state.json').read_text())

    def test_changed_discovery_hash_waits_for_new_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            post, content = setup_source(folder)
            post['source_text_sha256'] = 'a' * 64
            with self.assertRaisesRegex(AnalysisError, 'source_changed'):
                make_input(ID, post, content, folder)

    def test_new_screenshot_does_not_invalidate_already_analyzed_normal_text(self):
        with tempfile.TemporaryDirectory() as folder:
            post, content = setup_source(folder)
            before = input_fingerprint(make_input(ID, post, content, folder))
            content.update(status='ready', screenshot={'file': ID + '-1234567890abcdef.jpg', 'sha256': 'a' * 64})
            self.assertEqual(input_fingerprint(make_input(ID, post, content, folder)), before)

    def test_media_only_requires_verified_image_and_cannot_be_confirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            post, content = setup_source(folder, '')
            content.update(media_only=True)
            with self.assertRaisesRegex(AnalysisError, 'media_screenshot_pending'):
                make_input(ID, post, content, folder)
            image_dir = Path(folder) / 'post-images'
            image_dir.mkdir()
            image = b'test frozen image bytes'
            digest = hashlib.sha256(image).hexdigest()
            name = ID + '-' + digest[:16] + '.jpg'
            (image_dir / name).write_bytes(image)
            content.update(status='ready', screenshot={'file': name, 'sha256': digest})
            source = make_input(ID, post, content, folder)
            self.assertEqual(source['image_path'], str((image_dir / name).resolve()))
            result = result_for(source, unrelated=True)
            result.update(translation_zh='', summary_zh='仅有图片，没有采集到可翻译的正文。', summary_en='An image-only post has no captured text to translate.')
            self.assertEqual(validate_result(result, source), result)
            result.update(relevance='reset', signal='delivered', scope='global')
            with self.assertRaisesRegex(AnalysisError, 'image_only_claim_unverified'):
                validate_result(result, source)

    def test_post_content_missing_is_pending_and_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as output:
            setup_source(folder)
            write_json(Path(folder) / 'post-content.json', {'posts': {}})
            class Runner:
                def analyze(self, *args, **kwargs):
                    raise AssertionError('Model should not receive excerpts')
            report = analyze_pending(folder, output, Runner(), now=NOW)
            self.assertEqual(report['attempted'], 0)
            self.assertEqual(report['pending_content'], 1)


class ValidationTests(unittest.TestCase):
    def source(self, folder, text=None):
        post, content = setup_source(folder, text or 'We will reset Codex usage for all paid users. It has not happened yet.')
        return make_input(ID, post, content, folder)

    def test_wrong_id_hash_extra_keys_and_non_chinese_summary_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            for patch_value in ({'id': PARENT_ID}, {'source_sha256': 'a' * 64}, {'rogue': True}, {'summary_zh': 'Not translated'}):
                result = result_for(source)
                result.update(patch_value)
                with self.assertRaises(AnalysisError):
                    validate_result(result, source, NOW)

    def test_invented_evidence_and_unprovided_parent_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            result = result_for(source)
            result['evidence'] = ['It is already complete.']
            with self.assertRaisesRegex(AnalysisError, 'evidence_not_in_source'):
                validate_result(result, source)
            result = result_for(source)
            result['related_post_id'] = PARENT_ID
            with self.assertRaisesRegex(AnalysisError, 'unsupported_related_post'):
                validate_result(result, source)

    def test_future_promise_cannot_supply_actual_time(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            result = result_for(source)
            result['reset_at'] = '2026-09-12T08:31:00+00:00'
            with self.assertRaisesRegex(AnalysisError, 'unsupported_reset_time'):
                validate_result(result, source, NOW)

    def test_delivered_claim_does_not_invent_precise_time_from_now_or_post_time(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, 'The global Codex usage reset is now complete.')
            result = result_for(source)
            result.update(signal='delivered', reset_at=None)
            result['prediction']['outlook'] = 'unknown'
            validate_result(result, source, NOW)
            result['reset_at'] = source['announced_at']
            with self.assertRaisesRegex(AnalysisError, 'unsupported_reset_time'):
                validate_result(result, source, NOW)

    def test_explicit_completed_absolute_timestamp_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, 'The global Codex reset completed at 2026-09-12 08:31 UTC.')
            result = result_for(source)
            result.update(signal='delivered', reset_at='2026-09-12T08:31:00Z')
            result['prediction']['outlook'] = 'unknown'
            self.assertEqual(validate_result(result, source, NOW)['reset_at'], '2026-09-12T08:31:00Z')

    def test_personal_card_is_not_rewritten_as_global_and_has_no_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, 'I used a banked reset card on my own Codex account. This was not a global reset.')
            result = result_for(source)
            result.update(signal='delivered', scope='personal', reset_type='banked')
            result['prediction']['outlook'] = 'unknown'
            self.assertEqual(validate_result(result, source, NOW)['scope'], 'personal')
            result['prediction']['outlook'] = 'likely'
            with self.assertRaisesRegex(AnalysisError, 'inconsistent_prediction'):
                validate_result(result, source, NOW)


class EventTests(unittest.TestCase):
    def events(self, values):
        return '\n'.join(json.dumps(value) for value in values)

    def test_verified_fail_closed_startup_notice_is_not_a_tool_call(self):
        # Frozen event ordering/shape from the successful production CLI debug:
        # audit/ai-pipeline-20260913/debug_model.json and debug_events.json.
        validate_events(self.events([
            {'type': 'thread.started', 'thread_id': 'test'},
            {'type': 'item.completed', 'item': {'id': 'notice', 'type': 'error', 'message': DISABLED_CODE_MODE_NOTICE}},
            {'type': 'turn.started'},
            {'type': 'item.completed', 'item': {'id': 'answer', 'type': 'agent_message', 'text': '{}'}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 1}},
        ]))

    def test_other_error_or_same_notice_during_turn_remains_rejected(self):
        for message, during_turn in ((DISABLED_CODE_MODE_NOTICE + ' changed', False),
                                     ('Provider or execution failure', False),
                                     (DISABLED_CODE_MODE_NOTICE, True)):
            events = [{'type': 'thread.started'}]
            if during_turn:
                events.append({'type': 'turn.started'})
            events.append({'type': 'item.completed', 'item': {'type': 'error', 'message': message}})
            with self.assertRaisesRegex(AnalysisError, 'model_runtime_error'):
                validate_events(self.events(events))

    def test_actual_tool_call_rejected_with_only_safe_type_diagnostics(self):
        events = [{'type': 'thread.started'}, {'type': 'turn.started'},
                  {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'PRIVATE COMMAND'}}]
        with self.assertRaises(AnalysisError) as caught:
            validate_events(self.events(events))
        self.assertEqual(str(caught.exception), 'model_used_tools')
        self.assertEqual(caught.exception.unexpected_item_types, ['command_execution'])
        self.assertNotIn('PRIVATE', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
