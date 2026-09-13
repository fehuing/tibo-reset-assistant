"""Portable capture and model workers; no account login or private HTTP API."""
from pathlib import Path
import threading

from activity_ingest import collect_activity
from ai_analysis import analyze_pending, safe_error, single_worker, atomic_json, read_json
from ai_config import input_dir, analysis_dir, bounded_int
from ai_input import prepare_inputs
from ai_publication import publish_ai


class AIRuntime:
    def __init__(self, state, status, stop, capture=None, runner=None):
        self.state, self.status, self.stop = Path(state), status, stop
        self.inputs, self.results = input_dir(state), analysis_dir(state)
        self.capture = capture
        self.runner = runner
        self.wake = threading.Event()
        self.worker = None
        self.status_lock = threading.Lock()
        self.limit = bounded_int('AI_MAX_JOBS', 3, 1, 20)
        self.timeout = bounded_int('AI_TIMEOUT_SECONDS', 150, 5, 300)
        self.budget = bounded_int('AI_BUDGET_SECONDS', 240, 5, 1800)

    def start(self):
        atomic_json(self.state / 'ai-config.json', {'enabled': True})
        prepare_inputs(self.state, self.inputs)
        self.worker = threading.Thread(target=self.run_worker, name='tibo-analysis', daemon=True)
        self.worker.start()
        self.wake.set()

    def notify(self):
        self.wake.set()

    def save_status(self):
        with self.status_lock:
            atomic_json(self.state / 'collection-status.json', self.status.snapshot())

    def publish(self, _post_id=None):
        # Source fingerprints and result evidence are revalidated under lock.
        return publish_ai(self.state, analysis_dir=self.results)

    def collect(self):
        try:
            archive = collect_activity(self.state)
            coverage = archive.get('coverage', {})
            outcome = {'ok': 'ok', 'partial': 'degraded'}.get(coverage.get('status'), 'error')
            errors = coverage.get('errors') or []
            first = errors[0] if errors else {}
            code = {'x_unreachable': 'x_network', 'x_http_error': 'x_http',
                    'x_public_content_unavailable': 'x_parse'}.get(first.get('code'), first.get('code', 'collector_error'))
            diagnostic = {'code': code, 'http_status': first.get('http_status')}
            for stage in ('feed', 'watch'):
                self.status.record(stage, outcome, diagnostic=diagnostic if outcome != 'ok' else None)
            prepare_inputs(self.state, self.inputs)
            self.notify()
            # Publish updated coverage even when only cached results exist.
            self.publish()
            if self.capture is None:
                from capture_posts import main
                capture = main
            else:
                capture = self.capture
            capture(3, self.state, on_ready=self.notify)
            prepare_inputs(self.state, self.inputs)
            self.notify()
        except Exception as error:
            self.status.record('feed', 'error', error=error)
        finally:
            self.save_status()

    def analyze_once(self):
        try:
            with single_worker(self.results / 'worker.lock'):
                report = analyze_pending(self.inputs, self.results, runner=self.runner,
                                         limit=self.limit, budget=self.budget, timeout=self.timeout,
                                         on_result=self.publish, stop=self.stop)
            failures = report.get('failures') or [item for item in read_json(self.results / 'state.json').get('posts', {}).values()
                                                  if item.get('state') == 'retrying']
            if failures:
                self.status.record('analysis', 'error', diagnostic={'code': failures[0]['error_code']})
            else:
                self.status.record('analysis')
            # Refresh retry/translation statuses, including failed jobs.
            self.publish()
            return report
        except Exception as error:
            self.status.record('analysis', 'error', diagnostic={'code': safe_error(error)})
            return {'failures': [{'error_code': safe_error(error)}]}
        finally:
            self.save_status()

    def run_worker(self):
        while not self.stop.is_set():
            # Events deliver captured posts promptly. The timer drains backlogs
            # and retries on schedule even if X has no newly published posts.
            self.wake.wait(30)
            self.wake.clear()
            if self.stop.is_set():
                break
            self.analyze_once()

    def close(self):
        self.wake.set()
        if self.worker is not None:
            self.worker.join(timeout=1)
