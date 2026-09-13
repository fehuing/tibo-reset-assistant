"""Analyze archived X posts with an isolated, authenticated Codex CLI process.

This module never writes the collector's feed, translations, calendar or watch.
The trusted publisher revalidates each hash-bound result before applying it.
Run the worker as the same operating-system user who logged into Codex.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
from ai_config import MODEL
from file_lock import file_lock
import shutil
PROMPT_VERSION = 'tibo-ai-v2-20260913'
POST_ID = re.compile(r'\d{10,25}')
SHA256 = re.compile(r'[a-f0-9]{64}')
CJK = re.compile(r'[\u3400-\u9fff]')
MAX_TEXT = 60000
MAX_RESULT_BYTES = 512 * 1024
DISABLED_FEATURES = (
    'shell_tool', 'unified_exec', 'browser_use', 'computer_use', 'apps',
    'plugins', 'multi_agent', 'code_mode', 'code_mode_host',
    'image_generation', 'view_image', 'goals', 'skill_search',
)
DISABLED_CODE_MODE_NOTICE = ('Code Mode is unavailable because code-mode host is disabled. '
                             'Code mode will fail closed; enable `features.code_mode_host` '
                             'and install `codex-code-mode-host`.')


class AnalysisError(ValueError):
    """A stable, public-safe diagnostic; never store raw CLI/provider errors."""

    def __init__(self, code, unexpected_item_types=None):
        super().__init__(code)
        self.unexpected_item_types = sorted({
            value if isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value) else 'unrecognized'
            for value in (unexpected_item_types or [])
        })[:16]


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def iso_time(value):
    if not isinstance(value, str):
        raise AnalysisError('invalid_timestamp')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AnalysisError('invalid_timestamp') from error
    if parsed.tzinfo is None:
        raise AnalysisError('invalid_timestamp')
    return parsed


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_json(path, value):
    """Atomic private output; never serve these files over HTTP."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.ai-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o640)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _context(value, expected_id):
    if not isinstance(value, dict) or not expected_id:
        return None
    text = value.get('text')
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        return None
    source = value.get('source_url')
    if not isinstance(source, str) or not re.fullmatch(r'https://x\.com/[A-Za-z0-9_]+/status/' + re.escape(expected_id), source):
        return None
    return {'id': expected_id, 'author': str(value.get('author') or '')[:64], 'text': text, 'source_url': source}


def _reference(value):
    return str(value) if value is not None and POST_ID.fullmatch(str(value)) else None


def make_input(post_id, post, content, state_dir):
    """Build the canonical, immutable model input; reject incomplete/stale bodies.

    Normal text can be analyzed while the independent screenshot job retries.
    Media-only posts require their captured original image and visual uncertainty.
    The local image_path is excluded from the logical fingerprint and prompt.
    """
    post_id = str(post_id)
    if not POST_ID.fullmatch(post_id) or not isinstance(post, dict) or not isinstance(content, dict):
        raise AnalysisError('invalid_source')
    expected_url = 'https://x.com/thsottiaux/status/' + post_id
    if str(post.get('id')) != post_id or post.get('author', '').lower() != 'thsottiaux' or post.get('source_url') != expected_url:
        raise AnalysisError('invalid_source')
    if content.get('status') not in ('ready', 'text_ready'):
        raise AnalysisError('content_not_ready')
    text = content.get('full_text')
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise AnalysisError('content_not_ready')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if digest != content.get('full_text_sha256'):
        raise AnalysisError('source_hash_mismatch')
    if content.get('source_url', expected_url) != expected_url or content.get('text_source') != 'x_post_page':
        raise AnalysisError('invalid_source')
    if content.get('author_verified') is False or content.get('text_complete') is False:
        raise AnalysisError('invalid_source')
    discovery = post.get('source_text_sha256')
    if discovery and content.get('discovery_text_sha256') and discovery != content['discovery_text_sha256']:
        raise AnalysisError('source_changed')
    # Legacy captures have no discovery hash. An unchanged excerpt is safe, but
    # an edited public body cannot keep using the old, more complete capture.
    if discovery and not content.get('discovery_text_sha256'):
        old_excerpt = ' '.join(str(post.get('text') or '').split()).rstrip('.…')
        body_prefix = ' '.join(text.split())
        if old_excerpt and not body_prefix.startswith(old_excerpt):
            raise AnalysisError('source_changed')
    announced_at = post.get('announced_at')
    iso_time(announced_at)
    reply_id = _reference(content.get('reply_to_id') or post.get('reply_to_id'))
    quote_id = _reference(content.get('quoted_id') or post.get('quoted_id'))
    result = {
        'schema_version': 1, 'id': post_id, 'author': 'thsottiaux',
        'source_url': expected_url, 'announced_at': announced_at,
        'first_seen_at': post.get('first_seen_at'), 'text': text,
        'source_sha256': digest, 'media_only': not bool(text.strip()),
        'reply_to_id': reply_id,
        'reply_context': _context(content.get('reply_context') or post.get('reply_context'), reply_id),
        'quoted_id': quote_id,
        'quoted_context': _context(content.get('quoted_context') or post.get('quoted_context'), quote_id),
    }
    if result['media_only']:
        if content.get('media_only') is not True or content.get('status') != 'ready':
            raise AnalysisError('media_screenshot_pending')
        shot = content.get('screenshot') or {}
        filename = shot.get('file', '')
        if not re.fullmatch(re.escape(post_id) + r'-[a-f0-9]{16}\.jpg', filename) or not SHA256.fullmatch(str(shot.get('sha256', ''))):
            raise AnalysisError('media_screenshot_pending')
        directory = (Path(state_dir) / 'post-images').resolve()
        image_path = (directory / filename).resolve()
        if image_path.parent != directory or not image_path.is_file() or image_path.stat().st_size > 4 * 1024 * 1024:
            raise AnalysisError('media_screenshot_pending')
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != shot['sha256']:
            raise AnalysisError('screenshot_hash_mismatch')
        result['screenshot_sha256'] = shot['sha256']
        result['image_path'] = str(image_path)
    return result


def prompt_input(source):
    return {key: value for key, value in source.items() if key != 'image_path'}


def input_fingerprint(source, role_text=None, schema=None):
    role_text = role_text if role_text is not None else (HERE / 'ai_role.md').read_text(encoding='utf-8')
    schema = schema if schema is not None else read_json(HERE / 'ai_analysis.schema.json')
    logical = {'source': prompt_input(source), 'model': MODEL, 'prompt_version': PROMPT_VERSION,
               'role': role_text, 'schema': schema}
    return hashlib.sha256(json.dumps(logical, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _schema_check(value, schema):
    """Validate the small, closed schema without adding a worker dependency."""
    types = schema.get('type')
    types = types if isinstance(types, list) else [types]
    matches = {'object': isinstance(value, dict), 'array': isinstance(value, list),
               'string': isinstance(value, str), 'integer': type(value) is int, 'null': value is None}
    if not any(matches.get(kind, False) for kind in types):
        raise AnalysisError('invalid_result_schema')
    if 'enum' in schema and value not in schema['enum']:
        raise AnalysisError('invalid_result_schema')
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        if set(schema.get('required', [])) - set(value) or (schema.get('additionalProperties') is False and set(value) - set(properties)):
            raise AnalysisError('invalid_result_schema')
        for key, child in value.items():
            if key in properties:
                _schema_check(child, properties[key])
    if isinstance(value, list):
        for child in value:
            _schema_check(child, schema['items'])


def validate_result(result, source, now=None):
    """Validate structure, evidence and provenance, not semantic keywords.

    The model decides relevance. This boundary prevents wrong-post output,
    unsupported links/times, and syntactically inconsistent public decisions.
    """
    _schema_check(result, read_json(HERE / 'ai_analysis.schema.json'))
    if result['id'] != source['id'] or result['source_sha256'] != source['source_sha256']:
        raise AnalysisError('result_source_mismatch')
    text = source['text']
    translation = result['translation_zh']
    if not text.strip():
        if translation:
            raise AnalysisError('invented_translation')
    elif not translation.strip() or len(translation) > 90000 or (re.search(r'[A-Za-z\u3400-\u9fff]', text) and not CJK.search(translation)):
        raise AnalysisError('incomplete_translation')
    for term in ('Codex', 'ChatGPT', 'Astra', 'Plus', 'Pro', 'Business'):
        if re.search(r'\b' + term + r'\b', text) and term not in translation:
            raise AnalysisError('missing_product_name')
    for field in ('summary_zh', 'summary_en'):
        if not result[field].strip() or len(result[field]) > 2000:
            raise AnalysisError('invalid_summary')
    if not CJK.search(result['summary_zh']):
        raise AnalysisError('invalid_summary')
    prediction = result['prediction']
    if not CJK.search(prediction['reason_zh']) or not prediction['reason_en'].strip() or max(len(prediction['reason_zh']), len(prediction['reason_en'])) > 2000:
        raise AnalysisError('invalid_prediction')
    sources = [text] + [source[key]['text'] for key in ('reply_context', 'quoted_context') if source.get(key)]
    if len(result['evidence']) > 12 or any(not quote.strip() or len(quote) > 3000 or not any(quote in body for body in sources) for quote in result['evidence']):
        raise AnalysisError('evidence_not_in_source')
    related = result['related_post_id']
    if related is not None and related not in (source.get('reply_to_id'), source.get('quoted_id')):
        raise AnalysisError('unsupported_related_post')
    if result['relevance'] == 'none' and (result['signal'] != 'none' or result['scope'] != 'unknown' or result['reset_type'] != 'unknown' or related is not None or prediction['outlook'] != 'unknown'):
        raise AnalysisError('inconsistent_unrelated_result')
    if result['relevance'] == 'reset' and not result['evidence'] and not source['media_only']:
        raise AnalysisError('missing_reset_evidence')
    if source['media_only'] and (result['evidence'] or result['signal'] not in ('none', 'hint') or result['scope'] != 'unknown'):
        raise AnalysisError('image_only_claim_unverified')
    if result['signal'] in ('announced', 'in_progress', 'delivered', 'denied') and not any(quote in text for quote in result['evidence']):
        raise AnalysisError('missing_current_post_evidence')
    if (result['signal'] == 'delivered' or result['scope'] == 'personal') and prediction['outlook'] != 'unknown':
        raise AnalysisError('inconsistent_prediction')
    if result['reset_at'] is not None:
        if result['relevance'] != 'reset' or result['signal'] != 'delivered':
            raise AnalysisError('unsupported_reset_time')
        actual = iso_time(result['reset_at'])
        if actual > (now or utc_now()) + dt.timedelta(minutes=5):
            raise AnalysisError('unsupported_reset_time')
        # An absolute date, time and timezone must actually occur in quoted
        # source evidence. Relative wording never creates a precise timestamp.
        quotes = '\n'.join(result['evidence'])
        date_pattern = r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b'
        if not re.search(date_pattern, quotes, re.I) or not re.search(r'\b\d{1,2}:\d{2}\b', quotes) or not re.search(r'\b(?:UTC|GMT|PDT|PST|PT|EST|EDT|Beijing|Asia/Shanghai)\b|[+-]\d\d:\d\d|\d\d:\d\d(?::\d\d)?Z\b', quotes, re.I):
            raise AnalysisError('unsupported_reset_time')
    return result


def _stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'posix':
        os.killpg(process.pid, signal.SIGTERM)
    else:
        # The npm shim may own a native CLI child; stop that job tree too.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if process.poll() is None:
            process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=3)


def model_error_code(message, default='model_runtime_error'):
    message = str(message).lower()
    if any(term in message for term in ('not logged in', 'refresh token', '401 unauthorized', 'please log in', 'codex login', 'authentication required')):
        return 'model_auth_required'
    if any(term in message for term in ('usage limit', 'rate limit', 'quota exceeded', '429')):
        return 'model_rate_limited'
    if any(term in message for term in ('connection refused', 'failed to connect', 'could not resolve', 'network is unreachable', 'error sending request')):
        return 'model_network'
    return default


def validate_events(raw):
    """Reject tool usage and runtime failures, retaining one observed notice.

    CLI 0.154.0 emits this exact fail-closed startup notice even when both Code
    Mode features are explicitly disabled. It is not a tool invocation. Only
    that message, between thread.started and turn.started, is exempted.
    """
    thread_started, turn_started = False, False
    unexpected = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get('type')
        if kind == 'thread.started':
            thread_started = True
        elif kind == 'turn.started':
            turn_started = True
        elif kind in ('error', 'turn.failed'):
            raise AnalysisError(model_error_code(event.get('message') or event.get('error') or ''))
        item = event.get('item') or {}
        item_type = item.get('type')
        if item_type == 'error':
            if (kind == 'item.completed' and thread_started and not turn_started
                    and item.get('message') == DISABLED_CODE_MODE_NOTICE):
                continue
            raise AnalysisError(model_error_code(item.get('message', '')), unexpected_item_types=['error'])
        if item_type not in (None, 'agent_message', 'reasoning'):
            unexpected.append(item_type)
    if unexpected:
        raise AnalysisError('model_used_tools', unexpected_item_types=unexpected)


def executable_command(executable):
    """Resolve CLI without shell interpolation, including npm's Windows shim."""
    resolved = shutil.which(executable)
    if not resolved and Path(executable).is_file():
        resolved = str(Path(executable).resolve())
    if not resolved:
        raise AnalysisError('model_unavailable')
    path = Path(resolved)
    if os.name == 'nt' and path.suffix.lower() in ('.cmd', '.bat'):
        script = path.parent / 'node_modules/@openai/codex/bin/codex.js'
        node = shutil.which('node')
        if not script.is_file() or not node:
            raise AnalysisError('model_unavailable')
        return [node, str(script)]
    return [str(path)]


class CodexRunner:
    def __init__(self, work_root, executable=None, stop=None):
        self.work_root = Path(work_root)
        self.work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.executable = executable or os.getenv('CODEX_EXECUTABLE', 'codex')
        self.stop = stop

    def analyze(self, source, timeout=150):
        role = (HERE / 'ai_role.md').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory(prefix='post-' + source['id'] + '-', dir=self.work_root) as folder:
            work = Path(folder)
            final = work / 'final.json'
            events = work / 'events.jsonl'
            errors = work / 'stderr.txt'
            args = executable_command(self.executable) + ['exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                    '--sandbox', 'read-only', '--color', 'never', '--model', MODEL,
                    '-c', 'model_reasoning_effort="low"', '-c', 'web_search="disabled"',
                    '--cd', str(work), '--json', '--output-schema', str(HERE / 'ai_analysis.schema.json'),
                    '-o', str(final)]
            for feature in DISABLED_FEATURES:
                args += ['--disable', feature]
            if source.get('image_path'):
                args += ['--image', source['image_path']]
            # End options so the variadic --image argument cannot absorb the
            # analyst instructions as another image filename.
            args += ['--', role]
            payload = json.dumps(prompt_input(source), ensure_ascii=False).encode('utf-8')
            started = time.monotonic()
            process = None
            try:
                # Pipe input comes from our bounded captured document, never a
                # shell command. All generated output stays in this private job.
                with (work / 'input.json').open('wb') as stream:
                    stream.write(payload)
                with (work / 'input.json').open('rb') as incoming, events.open('wb') as outgoing, errors.open('wb') as error_stream:
                    process = subprocess.Popen(args, stdin=incoming, stdout=outgoing, stderr=error_stream,
                                               cwd=work, start_new_session=True)
                    while process.poll() is None:
                        if self.stop is not None and self.stop.is_set():
                            raise AnalysisError('model_cancelled')
                        if time.monotonic() - started >= timeout:
                            raise AnalysisError('model_timeout')
                        if events.stat().st_size > 2 * 1024 * 1024 or errors.stat().st_size > 256 * 1024 or (final.exists() and final.stat().st_size > MAX_RESULT_BYTES):
                            raise AnalysisError('model_output_too_large')
                        time.sleep(0.2)
                if process.returncode != 0:
                    message = errors.read_text(encoding='utf-8', errors='replace')
                    raise AnalysisError(model_error_code(message, 'model_request_failed'))
                if not final.is_file() or final.stat().st_size > MAX_RESULT_BYTES:
                    raise AnalysisError('model_result_missing')
                validate_events(events.read_text(encoding='utf-8', errors='replace'))
                try:
                    return json.loads(final.read_text(encoding='utf-8'))
                except (ValueError, UnicodeError) as error:
                    raise AnalysisError('invalid_result_json') from error
            finally:
                if process is not None:
                    _stop_process(process)


def safe_error(error):
    if isinstance(error, AnalysisError) and re.fullmatch(r'[a-z_]{1,64}', str(error)):
        return str(error)
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return 'model_timeout'
    if isinstance(error, FileNotFoundError):
        return 'model_unavailable'
    return 'analysis_failed'


def _read_inputs(state_dir):
    archive = read_json(state_dir / 'activity-archive.json')
    manifest = read_json(state_dir / 'post-content.json')
    archive_generation = archive.get('input_generation')
    manifest_generation = manifest.get('input_generation')
    if (archive_generation or manifest_generation) and archive_generation != manifest_generation:
        raise AnalysisError('input_snapshot_incomplete')
    return archive.get('posts', {}), manifest.get('posts', {})


def analyze_pending(state_dir, analysis_dir, runner=None, limit=3, budget=240, timeout=150, now=None, force=False, on_result=None, stop=None):
    state_dir, analysis_dir = Path(state_dir), Path(analysis_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    archive, manifest = _read_inputs(state_dir)
    state_path = analysis_dir / 'state.json'
    state = read_json(state_path)
    jobs = state.setdefault('posts', {})
    state.update(schema_version=1, model=MODEL, prompt_version=PROMPT_VERSION)
    now = now or utc_now()
    started = time.monotonic()
    deadline = started + max(1, budget)
    report = {'attempted': 0, 'completed': [], 'failures': [], 'cached': 0, 'pending_content': 0}
    def save():
        state['checked_at'] = now.isoformat()
        state['updated_at'] = utc_now().isoformat()
        atomic_json(state_path, state)
    for post_id, post in sorted(archive.items(), key=lambda row: int(row[0]) if POST_ID.fullmatch(str(row[0])) else 0, reverse=True):
        if stop is not None and stop.is_set():
            break
        if not POST_ID.fullmatch(str(post_id)):
            continue
        try:
            source = make_input(post_id, post, manifest.get(post_id, {}), state_dir)
        except AnalysisError as error:
            report['pending_content'] += 1
            jobs[post_id] = {'state': 'pending_content', 'error_code': safe_error(error), 'checked_at': now.isoformat()}
            continue
        digest = input_fingerprint(source)
        result_path = analysis_dir / 'results' / (post_id + '.json')
        previous = read_json(result_path)
        if not force and previous.get('status') == 'ready' and previous.get('input_sha256') == digest and previous.get('model') == MODEL and previous.get('prompt_version') == PROMPT_VERSION:
            try:
                validate_result(previous.get('result'), source, now)
            except AnalysisError:
                pass
            else:
                report['cached'] += 1
                jobs[post_id] = {'state': 'ready', 'input_sha256': digest, 'source_sha256': source['source_sha256'], 'analyzed_at': previous.get('analyzed_at')}
                continue
        job = jobs.get(post_id, {})
        same_input = job.get('input_sha256') == digest
        if not force and same_input and job.get('retry_at'):
            try:
                if iso_time(job['retry_at']) > now:
                    continue
            except AnalysisError:
                pass
        if report['attempted'] >= max(1, limit) or deadline - time.monotonic() < 5:
            jobs[post_id] = dict(job, state='pending', input_sha256=digest, source_sha256=source['source_sha256'])
            continue
        attempts = int(job.get('attempts', 0)) + 1 if same_input else 1
        jobs[post_id] = {'state': 'analyzing', 'input_sha256': digest, 'source_sha256': source['source_sha256'], 'attempts': attempts, 'started_at': now.isoformat()}
        save()
        report['attempted'] += 1
        try:
            if runner is None:
                runner = CodexRunner(analysis_dir / 'jobs', stop=stop)
            result = runner.analyze(source, timeout=min(timeout, max(1, deadline - time.monotonic())))
            validate_result(result, source, now)
            latest_archive, latest_manifest = _read_inputs(state_dir)
            latest = make_input(post_id, latest_archive.get(post_id, {}), latest_manifest.get(post_id, {}), state_dir)
            if input_fingerprint(latest) != digest:
                raise AnalysisError('source_changed_during_analysis')
            completed = (now + dt.timedelta(seconds=time.monotonic() - started)).isoformat()
            envelope = {'status': 'ready', 'schema_version': 1, 'model': MODEL, 'analyzed_at': completed,
                        'prompt_version': PROMPT_VERSION, 'input_sha256': digest, 'result': result}
            atomic_json(result_path, envelope)
            jobs[post_id] = {'state': 'ready', 'input_sha256': digest, 'source_sha256': source['source_sha256'], 'attempts': attempts, 'analyzed_at': completed}
            report['completed'].append(post_id)
            # A path unit wakes the trusted publisher immediately per post;
            # capture and subsequent model jobs can continue independently.
            save()
            atomic_json(analysis_dir / 'publish.signal', {'id': post_id, 'analyzed_at': completed})
            if on_result is not None:
                on_result(post_id)
        except Exception as error:
            code = safe_error(error)
            retry_seconds = min(3600, 120 * (2 ** min(attempts - 1, 5)))
            failed = now + dt.timedelta(seconds=time.monotonic() - started)
            jobs[post_id].update(state='retrying', error_code=code, failed_at=failed.isoformat(), retry_at=(failed + dt.timedelta(seconds=retry_seconds)).isoformat())
            failure = {'id': post_id, 'error_code': code}
            if isinstance(error, AnalysisError) and error.unexpected_item_types:
                details = {'unexpected_item_types': error.unexpected_item_types}
                jobs[post_id]['error_details'] = details
                failure['error_details'] = details
            report['failures'].append(failure)
        save()
    state['last_run'] = dict(report, completed_at=utc_now().isoformat())
    save()
    return report


@contextlib.contextmanager
def single_worker(path):
    try:
        with file_lock(path, blocking=False):
            yield
    except BlockingIOError as error:
        raise AnalysisError('worker_already_running') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('.data'))
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--budget', type=int, default=240)
    parser.add_argument('--timeout', type=int, default=150)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    from ai_config import analysis_dir
    args.output = args.output or analysis_dir(args.state)
    os.umask(0o027)
    try:
        with single_worker(args.output / 'worker.lock'):
            print(json.dumps(analyze_pending(args.state / 'ai-input', args.output, limit=max(1, min(args.limit, 20)), budget=max(5, min(args.budget, 1800)), timeout=max(5, min(args.timeout, 300)), force=args.force), ensure_ascii=False))
    except AnalysisError as error:
        print(json.dumps({'status': 'idle' if str(error) == 'worker_already_running' else 'error', 'error_code': safe_error(error)}))
        return 0 if str(error) == 'worker_already_running' else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
