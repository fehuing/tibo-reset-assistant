from contextlib import closing
import datetime as dt
import http.client
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

from collection_status import CollectionStatus, diagnose, XCollectionError
from collector import collect
from server import collect_cycle, handler
from reactions import ReactionServer

NOW = dt.datetime(2026, 9, 7, 12, tzinfo=dt.timezone.utc)


class CollectionDiagnosticsTests(unittest.TestCase):
    def test_transport_and_content_failures_are_distinguished_without_raw_details(self):
        secret = 'private-proxy-password-and-host'
        examples = [
            (urllib.error.URLError(socket.gaierror(-2, secret)), 'x_dns'),
            (urllib.error.URLError(TimeoutError(secret)), 'x_timeout'),
            (ConnectionRefusedError(secret), 'x_network'),
            (ssl.SSLCertVerificationError(secret), 'x_tls'),
            (ValueError(secret), 'x_parse'),
            (PermissionError(secret), 'collector_error'),
            (FileNotFoundError(secret), 'collector_error'),
        ]
        for error, code in examples:
            with self.subTest(code=code):
                output = diagnose(XCollectionError(error))
                self.assertEqual(output['code'], code)
                self.assertNotIn(secret, json.dumps(output))
        for http, code in ((401, 'x_access_denied'), (403, 'x_access_denied'), (429, 'x_rate_limited'), (404, 'x_unavailable'), (503, 'x_http')):
            error = urllib.error.HTTPError('https://user:password@proxy.example/', http, secret, {}, None)
            with closing(error):
                self.assertEqual(diagnose(error), {'code': code, 'http_status': http})

    def test_wrapped_error_retains_actual_timeout_cause(self):
        try:
            try: raise TimeoutError('timeout with private detail')
            except TimeoutError as error: raise RuntimeError('wrapper') from error
        except RuntimeError as error:
            self.assertEqual(diagnose(error), {'code': 'x_timeout'})

    def test_fallback_failure_does_not_hide_the_x_error(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            file = state / 'data.json'; file.write_text('{"previous":"retained"}')
            before = file.read_bytes()
            with patch('collector.fetch_x_profile', side_effect=urllib.error.URLError(socket.gaierror(-2, 'private'))), patch('collector.collect_fallback', side_effect=TimeoutError('fallback')):
                with self.assertRaises(XCollectionError) as raised:
                    collect(file, state / 'cache.json', allow_fallback=True)
            self.assertEqual(diagnose(raised.exception)['code'], 'x_dns')
            self.assertEqual(file.read_bytes(), before)

    def test_failure_does_not_advance_success_and_recovery_clears_error(self):
        clock = [NOW]
        status = CollectionStatus(True, clock=lambda: clock[0])
        status.record('feed'); status.record('watch')
        successful = status.snapshot()['stages']['feed']['last_success_at']
        clock[0] += dt.timedelta(minutes=2)
        status.record('feed', 'error', error=TimeoutError())
        self.assertEqual(status.snapshot()['state'], 'error')
        self.assertEqual(status.snapshot()['stages']['feed']['last_success_at'], successful)
        status.record('feed')
        self.assertEqual(status.snapshot()['state'], 'ok')
        self.assertNotEqual(status.snapshot()['stages']['feed']['last_success_at'], successful)
        self.assertEqual(status.snapshot()['stages']['feed']['code'], 'ok')

    def test_disabled_and_stalled_workers_cannot_look_healthy(self):
        self.assertEqual(CollectionStatus(False).snapshot()['state'], 'disabled')
        clock = [NOW]; status = CollectionStatus(True, clock=lambda: clock[0])
        self.assertEqual(status.snapshot()['state'], 'checking')
        status.record('feed'); status.record('watch')
        clock[0] += dt.timedelta(minutes=9)
        self.assertEqual(status.snapshot()['state'], 'stale')

    def test_healthy_announcements_do_not_hide_missing_replies_or_fallback(self):
        status = CollectionStatus(True)
        status.record('feed'); status.record('watch', 'degraded', diagnostic={'code': 'x_access_denied', 'http_status': 403})
        self.assertEqual(status.snapshot()['state'], 'degraded')
        self.assertEqual(status.snapshot()['stages']['feed']['state'], 'ok')
        status.record('feed', 'degraded', diagnostic={'code': 'x_timeout'})
        self.assertEqual(status.snapshot()['state'], 'degraded')

    def test_collect_cycle_preserves_feed_and_publishes_safe_x_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory); file = state / 'data.json'; file.write_text('{"checked_at":"old"}')
            status = CollectionStatus(True)
            watch = {'collection': {'public_timeline_read': False, 'errors': [{'surface': 'https://x.com/thsottiaux', 'code': 'x_timeout'}]}}
            with patch('server.collect', side_effect=XCollectionError(TimeoutError('private'))), patch('server.collect_watch', return_value=watch):
                collect_cycle(state, status)
            output = json.loads((state / 'collection-status.json').read_text())
            self.assertEqual(output['state'], 'error')
            self.assertEqual(output['stages']['feed']['code'], 'x_timeout')
            self.assertIsNone(output['stages']['feed']['last_success_at'])
            self.assertEqual(json.loads(file.read_text()), {'checked_at': 'old'})
            self.assertNotIn('private', json.dumps(output))

    def test_http_feed_and_status_report_failure_even_when_cached_feed_is_200(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); feed = {'schema_version': 1, 'checked_at': '2026-09-01T00:00:00Z', 'records': [{'id': '1', 'announced_at': '2026-09-01T00:00:00Z'}]}
            (root / 'data.json').write_text(json.dumps(feed))
            status = CollectionStatus(True)
            with closing(urllib.error.HTTPError('https://x.com/', 403, 'private', {}, None)) as error:
                status.record('feed', 'error', error=error)
            service = ReactionServer(('127.0.0.1', 0), handler(root, root, 0, status))
            worker = threading.Thread(target=service.serve_forever, daemon=True); worker.start()
            try:
                with closing(http.client.HTTPConnection(*service.server_address, timeout=3)) as connection:
                    for prefix in ('', '/radar'):
                        connection.request('GET', prefix + '/data.json'); response = connection.getresponse(); value = json.loads(response.read())
                        self.assertEqual(response.status, 200)
                        self.assertEqual(value['checked_at'], feed['checked_at'])
                        self.assertEqual(value['collection_status']['stages']['feed']['code'], 'x_access_denied')
                        connection.request('GET', prefix + '/api/collection-status'); response = connection.getresponse()
                        self.assertEqual(json.loads(response.read())['state'], 'error')
            finally:
                service.shutdown(); service.server_close(); worker.join(timeout=3)
