import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from ai_analysis import AnalysisError, executable_command, read_json
from ai_input import prepare_inputs
from ai_runtime import AIRuntime
from collection_status import CollectionStatus
from collector import _feed, atomic_json
from file_lock import file_lock
from test_ai_analysis import ID, NOW, setup_source, result_for, write_json


class RuntimeTests(unittest.TestCase):
    def setup_state(self, folder):
        state = Path(folder)
        post, content = setup_source(folder)
        post['last_seen_at'] = NOW.isoformat()
        content['text_captured_at'] = NOW.isoformat()
        write_json(state / 'post-content.json', {'posts': {ID: content}})
        archive = {'posts': {ID: post}, 'coverage': {'status': 'ok', 'errors': []}}
        write_json(state / 'activity-archive.json', archive)
        atomic_json(state / 'data.json', _feed([], NOW, {'active': 'snapshot'}))
        atomic_json(state / 'watch.json', {'schema_version': 1, 'checked_at': NOW.isoformat(), 'watch': None})
        prepare_inputs(state)
        return state, archive

    def runtime(self, state, runner=None, capture=None):
        return AIRuntime(state, CollectionStatus(True, ai=True), threading.Event(), capture=capture, runner=runner)

    def test_model_auth_error_is_safe_and_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            state, archive = self.setup_state(folder)
            class Runner:
                def analyze(self, source, timeout):
                    raise AnalysisError('model_auth_required')
            runtime = self.runtime(state, Runner())
            before = read_json(state / 'data.json')['records']
            with patch('collector.collect') as legacy, patch('reset_watch.collect_watch') as legacy_watch:
                report = runtime.analyze_once()
            legacy.assert_not_called(); legacy_watch.assert_not_called()
            self.assertEqual(report['failures'][0]['error_code'], 'model_auth_required')
            self.assertEqual(runtime.status.snapshot()['stages']['analysis']['code'], 'model_auth_required')
            self.assertEqual(read_json(state / 'data.json')['records'], before)
            self.assertEqual(read_json(state / 'watch.json')['watch'], None)
            runtime.analyze_once()  # Waiting for backoff must not look recovered.
            self.assertEqual(runtime.status.snapshot()['stages']['analysis']['code'], 'model_auth_required')

    def test_unavailable_x_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            state, archive = self.setup_state(folder)
            archive['coverage'] = {'status': 'unavailable', 'errors': [{'code': 'x_unreachable'}]}
            runtime = self.runtime(state, capture=lambda *args, **kwargs: None)
            with patch('ai_runtime.collect_activity', return_value=archive):
                runtime.collect()
            status = runtime.status.snapshot()
            self.assertEqual(status['state'], 'error')
            self.assertEqual(status['stages']['feed']['code'], 'x_network')
            self.assertEqual(status['stages']['watch']['state'], 'error')

    def test_unrelated_post_translates_without_reset_or_watch(self):
        with tempfile.TemporaryDirectory() as folder:
            state, archive = self.setup_state(folder)
            class Runner:
                def analyze(self, source, timeout):
                    return result_for(source, unrelated=True)
            runtime = self.runtime(state, Runner())
            report = runtime.analyze_once()
            self.assertEqual(report['completed'], [ID])
            self.assertEqual(read_json(state / 'data.json')['records'], [])
            self.assertIsNone(read_json(state / 'watch.json')['watch'])
            self.assertTrue(read_json(state / 'ai-analysis/results' / (ID + '.json'))['result']['translation_zh'])

    def test_ready_result_is_published_per_post_and_cached_on_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            state, archive = self.setup_state(folder)
            calls = []
            class Runner:
                def analyze(self, source, timeout):
                    calls.append(source['id'])
                    return result_for(source)
            runtime = self.runtime(state, Runner())
            runtime.analyze_once()
            feed = read_json(state / 'data.json')
            self.assertEqual(feed['records'][0]['id'], ID)
            self.assertEqual(feed['records'][0]['status'], 'planned')
            self.assertEqual(read_json(state / 'watch.json')['watch']['window_basis'], 'until_reset_confirmed')
            runtime.analyze_once()
            self.assertEqual(calls, [ID])

    def test_slow_model_does_not_block_capture_thread(self):
        with tempfile.TemporaryDirectory() as folder:
            state, archive = self.setup_state(folder)
            started, release, captured = threading.Event(), threading.Event(), threading.Event()
            class Runner:
                def analyze(self, source, timeout):
                    started.set()
                    if not release.wait(5):
                        raise TimeoutError('Test worker did not release')
                    return result_for(source, unrelated=True)
            def capture(*args, **kwargs):
                captured.set()
            runtime = self.runtime(state, Runner(), capture)
            runtime.start()
            try:
                self.assertTrue(started.wait(2))
                with patch('ai_runtime.collect_activity', return_value=archive):
                    runtime.collect()
                self.assertTrue(captured.is_set())
                self.assertFalse(release.is_set())
            finally:
                release.set()
                runtime.stop.set()
                runtime.close()
                if runtime.worker is not None:
                    runtime.worker.join(timeout=5)

    def test_model_configuration_changes_fingerprint_and_publisher(self):
        script = "import json; from ai_analysis import MODEL,input_fingerprint; import ai_publication; print(json.dumps([MODEL, ai_publication.MODEL, input_fingerprint({'text':'same'})]))"
        values = []
        for model in ('model-alpha', 'model-beta'):
            env = dict(os.environ, CODEX_MODEL=model, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'ops'))
            output = subprocess.check_output([sys.executable, '-c', script], env=env, text=True)
            values.append(json.loads(output))
        self.assertEqual(values[0][:2], ['model-alpha', 'model-alpha'])
        self.assertEqual(values[1][:2], ['model-beta', 'model-beta'])
        self.assertNotEqual(values[0][2], values[1][2])

    def test_worker_lock_excludes_another_thread(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'worker.lock'
            errors = []
            def contender():
                try:
                    with file_lock(path, blocking=False):
                        errors.append('entered')
                except BlockingIOError:
                    errors.append('locked')
            with file_lock(path):
                thread = threading.Thread(target=contender)
                thread.start(); thread.join(timeout=2)
            self.assertEqual(errors, ['locked'])
            with file_lock(path, blocking=False):
                pass

    def test_missing_cli_does_not_execute_a_shell(self):
        with patch('ai_analysis.shutil.which', return_value=None), patch('ai_analysis.subprocess.Popen') as process:
            with self.assertRaisesRegex(AnalysisError, 'model_unavailable'):
                executable_command('nonexistent-tibo-codex-binary')
            process.assert_not_called()

    def test_model_state_maps_to_translation_client_contract(self):
        from translation_state import attach_translation_status
        feed = {'records': [{'id': ID, 'source_url': 'https://x.com/thsottiaux/status/' + ID,
                             'text_complete': True, 'full_text_sha256': 'abc'}]}
        queue = {'posts': {ID: {'state': 'retrying', 'source_sha256': 'abc', 'retry_at': NOW.isoformat(),
                                 'started_at': NOW.isoformat(), 'error_code': 'model_rate_limited'}}}
        value = attach_translation_status(feed, queue)['records'][0]['translation_status']
        self.assertEqual(value['next_retry_at'], NOW.isoformat())
        self.assertEqual(value['error_code'], 'model_rate_limited')

    def test_model_heartbeat_does_not_hide_stale_x_collection(self):
        clock = [NOW]
        status = CollectionStatus(True, ai=True, clock=lambda: clock[0])
        status.record('feed'); status.record('watch'); status.record('analysis')
        clock[0] += dt.timedelta(minutes=9)
        status.record('analysis')
        self.assertEqual(status.snapshot()['state'], 'stale')

    def test_ai_launcher_enables_live_capture_without_logging_in(self):
        import run
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'dist/client/radar/index.html'
            target.parent.mkdir(parents=True); target.write_text('<html></html>')
            previous = Path.cwd()
            try:
                with patch.object(run, 'ROOT', root), patch.object(sys, 'argv', ['run.py', '--no-build', '--ai']), \
                     patch.dict(os.environ, {'AI_ANALYSIS': '0', 'TRANSLATE_POSTS': '0'}), \
                     patch('importlib.util.find_spec', return_value=object()), \
                     patch('ai_analysis.executable_command', return_value=['codex']) as lookup, \
                     patch('server.serve') as serve, patch('subprocess.Popen') as process:
                    run.main()
                    args = serve.call_args.args[1]
                    self.assertTrue(args.ai and args.live and args.capture)
                    self.assertFalse(args.translate)
                    lookup.assert_called_once()
                    process.assert_not_called()
            finally:
                os.chdir(previous)

    def test_ai_launcher_rejects_a_second_translation_pipeline(self):
        import run
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'dist/client/radar/index.html'
            target.parent.mkdir(parents=True); target.write_text('<html></html>')
            previous = Path.cwd()
            try:
                with patch.object(run, 'ROOT', root), patch.object(sys, 'argv', ['run.py', '--no-build', '--ai', '--translate']), \
                     patch.dict(os.environ, {'TRANSLATE_POSTS': '0'}), patch('server.serve') as serve:
                    with self.assertRaisesRegex(RuntimeError, 'already translates'):
                        run.main()
                    serve.assert_not_called()
            finally:
                os.chdir(previous)
