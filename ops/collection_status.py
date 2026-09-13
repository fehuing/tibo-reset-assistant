"""Safe, public collection diagnostics. Never serialize exception messages."""
import datetime as dt
import socket
import ssl
import threading
import urllib.error

SOURCE = 'https://x.com/thsottiaux'
CODES = {'ok', 'disabled', 'checking', 'x_dns', 'x_timeout', 'x_network', 'x_tls',
         'x_access_denied', 'x_rate_limited', 'x_unavailable', 'x_http', 'x_parse',
         'collector_error', 'worker_stale', 'model_auth_required', 'model_rate_limited',
         'model_timeout', 'model_unavailable', 'model_request_failed', 'model_runtime_error',
         'model_result_missing', 'model_used_tools', 'model_output_too_large', 'invalid_result_json',
         'invalid_result_schema', 'analysis_failed', 'worker_already_running',
         'evidence_not_in_source', 'result_source_mismatch', 'source_changed_during_analysis',
         'incomplete_translation', 'invalid_summary', 'model_network', 'capture_failed'}


def diagnose(error):
    """Unwrap transport errors, including those wrapped by the feed collector."""
    seen, chain = set(), []
    while isinstance(error, BaseException) and id(error) not in seen:
        seen.add(id(error)); chain.append(error)
        if isinstance(getattr(error, 'diagnostic', None), dict):
            return safe_diagnostic(error.diagnostic)
        error = error.__cause__ or (error.reason if isinstance(error, urllib.error.URLError) and isinstance(error.reason, BaseException) else None)
    for item in reversed(chain):
        if isinstance(item, urllib.error.HTTPError):
            status = item.code
            code = ('x_access_denied' if status in (401, 403) else 'x_rate_limited' if status == 429
                    else 'x_unavailable' if status in (404, 410) else 'x_http')
            return {'code': code, 'http_status': status}
        if isinstance(item, ssl.SSLError): return {'code': 'x_tls'}
        if isinstance(item, socket.gaierror): return {'code': 'x_dns'}
        if isinstance(item, TimeoutError): return {'code': 'x_timeout'}
        if isinstance(item, (FileNotFoundError, PermissionError)): return {'code': 'collector_error'}
        if isinstance(item, (ConnectionError, urllib.error.URLError, OSError)): return {'code': 'x_network'}
        if isinstance(item, (ValueError, StopIteration, UnicodeError)): return {'code': 'x_parse'}
    return {'code': 'collector_error'}


def safe_diagnostic(value):
    result = {'code': value.get('code') if value.get('code') in CODES else 'collector_error'}
    status = value.get('http_status')
    if type(status) is int and 100 <= status <= 599: result['http_status'] = status
    return result


class XCollectionError(RuntimeError):
    def __init__(self, source_error, fallback_error=None):
        super().__init__('X collection failed; previous feed retained')
        self.diagnostic = diagnose(source_error)
        self.fallback_failed = fallback_error is not None


class CollectionStatus:
    def __init__(self, enabled, interval=120, clock=None, ai=False):
        self.enabled = enabled
        self.interval = max(120, interval)
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.lock = threading.Lock()
        self.started = self.clock()
        self.updated = self.started
        self.next_check = None
        self.stages = {key: {'state': 'checking' if enabled else 'disabled',
                             'code': 'checking' if enabled else 'disabled',
                             'checked_at': None, 'last_success_at': None}
                       for key in (('feed', 'watch', 'analysis') if ai else ('feed', 'watch'))}

    def record(self, stage, outcome='ok', error=None, diagnostic=None):
        with self.lock:
            now = self.clock()
            result = self.stages[stage]
            result.update(state=outcome, code='ok', checked_at=now.isoformat())
            result.pop('http_status', None)
            result.update(diagnose(error) if error else safe_diagnostic(diagnostic) if diagnostic else {})
            if outcome == 'ok': result['last_success_at'] = now.isoformat()
            self.updated = now

    def schedule(self):
        with self.lock:
            self.next_check = self.clock() + dt.timedelta(seconds=self.interval)

    def snapshot(self):
        with self.lock:
            now = self.clock()
            stages = {key: dict(value) for key, value in self.stages.items()}
            last_feed_check = stages['feed'].get('checked_at')
            freshness = dt.datetime.fromisoformat(last_feed_check) if last_feed_check else self.started
            stale = self.enabled and (now - freshness).total_seconds() > max(480, self.interval + 180)
            if not self.enabled: overall = 'disabled'
            elif stale: overall = 'stale'
            elif stages['feed']['state'] == 'error': overall = 'error'
            elif stages['feed']['state'] == 'checking': overall = 'checking'
            elif any(value['state'] in ('error', 'degraded') for value in stages.values()): overall = 'degraded'
            else: overall = 'ok'
            return {'schema_version': 1, 'enabled': self.enabled, 'state': overall,
                    'source_url': SOURCE, 'stages': stages,
                    'next_check_at': self.next_check.isoformat() if self.next_check else None,
                    'interval_seconds': self.interval, 'stale': stale}
