"""Archive actual X post text and screenshots without depending on logged-in sessions."""
import argparse
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import urlsplit
import urllib.request
from x_public import public_posts
from activity_ingest import valid_post

STATE = Path('.data')
SOURCE = re.compile(r'https://x\.com/thsottiaux/status/(\d{10,25})$')
MIN_FREE_BYTES = 600 * 1024 * 1024


def sync_playwright():
    # Optional dependency is only imported when capture actually runs.
    from playwright.sync_api import sync_playwright as factory
    return factory()


def capture_proxy():
    value = os.getenv('CAPTURE_PROXY', '').strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https', 'socks5') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('CAPTURE_PROXY must be a proxy server URL without credentials; use separate credential variables')
    proxy = {'server': value.rstrip('/')}
    for key, variable in (('username', 'CAPTURE_PROXY_USERNAME'), ('password', 'CAPTURE_PROXY_PASSWORD')):
        if os.getenv(variable):
            proxy[key] = os.environ[variable]
    return proxy


def capture_error(error):
    if isinstance(error, TimeoutError) or type(error).__name__ == 'TimeoutError':
        return 'x_timeout'
    return 'capture_failed'


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def atomic_json(path, data):
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.content-', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    temporary.chmod(0o644); temporary.replace(path)


def normalized(text):
    return ' '.join(html.unescape(text).split())


def capture(page, record, image_dir, on_text=None):
    source = record['source_url']
    match = SOURCE.fullmatch(source)
    if not match:
        raise ValueError('Unexpected source URL')
    post_id = match.group(1)
    page.set_viewport_size({'width': 440, 'height': 1000})
    # Archive the public HTTP response, then render that exact document. No login,
    # cookies, text reconstruction or rewritten layout is used for the capture.
    with urllib.request.urlopen(source, timeout=25) as received:
        if received.status != 200 or received.url.rstrip('/') != source or urlsplit(received.url).hostname != 'x.com':
            raise ValueError('Public X document unavailable')
        document = received.read(2 * 1024 * 1024 + 1)
        if len(document) > 2 * 1024 * 1024:
            raise ValueError('X document exceeds limit')
    verified = next((post for post in public_posts(document.decode('utf-8'))
                     if post['id'] == post_id and post['author'] == 'thsottiaux'), None)
    if record.get('activity_archive') and verified is None:
        raise ValueError('Requested author could not be verified on original X page')
    media_only = bool(verified and verified.get('media_only'))
    handler = lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=document)
    page.route(source, handler)
    try:
        response = page.goto(source, wait_until='domcontentloaded', timeout=30000)
    finally:
        page.unroute(source, handler)
    if not response or response.status != 200 or urlsplit(page.url).hostname != 'x.com':
        raise ValueError('X post page unavailable')
    # The timestamp permalink identifies the requested post, excluding other replies.
    permalink = page.locator(f'a[href="/thsottiaux/status/{post_id}"]')
    article = page.locator('article').filter(has=permalink).first
    article.wait_for(state='visible', timeout=12000)
    if not article.locator('a[href="/thsottiaux"]').count():
        raise ValueError('Requested author is absent')
    # Current public X pages expose complete post text in the visible H1 and article.
    # Legacy X layouts use tweetText. Never synthesize text from an image or summary.
    body = article.locator('[data-testid="tweetText"]')
    if media_only:
        full_text = ''  # Media has no source text; never invent a caption for it.
    elif body.count():
        full_text = body.first.inner_text().strip()
        extra = body.first.locator('..').get_by_text('Show more', exact=True)
        if extra.count() and extra.first.is_visible():
            extra.first.click(); full_text = body.first.inner_text().strip()
    else:
        headings = page.locator('h1').all_inner_texts()
        candidates = [re.fullmatch(r'Tibo on X: "(.*)"', value.strip(), re.DOTALL) for value in headings]
        candidates = [value.group(1) for value in candidates if value]
        if len(candidates) != 1:
            raise ValueError('Full post text could not be identified')
        full_text = html.unescape(candidates[0])
        # Preserve paragraph breaks from the visible body where possible.
        exact_body = article.locator('div,p').filter(has_text=full_text[:60])
        for value in exact_body.all_inner_texts():
            if normalized(value) == normalized(full_text):
                full_text = value.strip()
                break
    if (not full_text and not media_only) or len(full_text) > 60000:
        raise ValueError('Invalid full text length')
    visible = normalized(article.inner_text())
    # Reply recipients can be in the page heading but omitted from the post body.
    visible_body = re.sub(r'^(?:@[A-Za-z0-9_]+\s+)+', '', normalized(full_text))
    if normalized(full_text) not in visible and (not visible_body or visible_body not in visible):
        raise ValueError('Full text is not completely visible in the screenshot area')
    # Quoted-post t.co links become quote cards in X's visible layout.
    excerpt = normalized(re.sub(r'https://t\.co/\S+', '', record.get('excerpt', ''))).removesuffix('…')
    if not record.get('activity_archive') and record.get('source_type') == 'x_post' and not normalized(full_text).startswith(excerpt):
        raise ValueError('Page text does not match the saved announcement')
    content = {'full_text': full_text, 'text_source': 'x_post_page', 'text_captured_at': utc_now(),
               'full_text_sha256': hashlib.sha256(full_text.encode()).hexdigest(), 'status': 'text_ready',
               'source_url': source, 'author_verified': verified is not None,
               'text_complete': True, 'media_only': media_only,
               'discovery_text_sha256': record.get('source_text_sha256')}
    if verified:
        content['announced_at'] = verified['announced_at']
        content['has_media'] = verified.get('has_media', False)
        for field in ('reply_to_id', 'reply_context', 'quoted_id', 'quoted_context'):
            if field in verified:
                content[field] = verified[field]
    if on_text:
        on_text(content)
    page.evaluate('document.fonts.ready')
    # Wait only for media inside this post, without relying on an endless network-idle state.
    article.evaluate('''async el => {
      await Promise.all(Array.from(el.querySelectorAll('img')).map(img => {
        if (img.complete) return Promise.resolve();
        return Promise.race([new Promise(resolve => { img.addEventListener('load',resolve,{once:true}); img.addEventListener('error',resolve,{once:true}); }),new Promise(resolve=>setTimeout(resolve,5000))]);
      }));
    }''')
    # Full element screenshot, not a viewport crop: even long posts remain complete.
    bounds = article.bounding_box()
    if not bounds or bounds['width'] < 250 or bounds['height'] < 60 or bounds['height'] > 12000:
        raise ValueError('Unexpected screenshot dimensions')
    # A tall viewport keeps the entire post visible, so X's sticky navigation
    # cannot cover the author when Playwright scrolls a long element into view.
    if bounds['height'] + max(bounds['y'], 0) > 900:
        page.set_viewport_size({'width': 440, 'height': min(13000, math.ceil(bounds['height'] + max(bounds['y'], 0) + 150))})
        page.evaluate('window.scrollTo(0, 0)')
        bounds = article.bounding_box()
    raw = article.screenshot(type='jpeg', quality=88, timeout=15000)
    if not raw.startswith(b'\xff\xd8\xff') or len(raw) > 4 * 1024 * 1024:
        raise ValueError('Invalid screenshot')
    digest = hashlib.sha256(raw).hexdigest()
    name = f'{post_id}-{digest[:16]}.jpg'
    destination = image_dir / name
    destination.write_bytes(raw); destination.chmod(0o644)
    document_dir = image_dir.parent / 'post-documents'; document_dir.mkdir(exist_ok=True)
    (document_dir / (post_id + '.html')).write_bytes(document)
    return dict(content, screenshot={'file': name, 'sha256': digest, 'width': round(bounds['width'] * 2),
                       'height': round(bounds['height'] * 2), 'captured_at': utc_now(), 'source_url': source,
                       'method': 'public_html_capture', 'capture_version': 2, 'document_sha256': hashlib.sha256(document).hexdigest()},
                status='ready')


def capture_jobs(feed, archive, documents, image_dir, now=None):
    """One queue for every archived post plus retained historical feed entries."""
    now = time.time() if now is None else now
    candidates = {}
    for record in feed.get('records', []):
        match = SOURCE.fullmatch(record.get('source_url', ''))
        if match:
            candidates[match[1]] = record
    for record in archive.get('posts', {}).values():
        if valid_post(record):
            candidates[record['id']] = dict(record, activity_archive=True, source_type='x_post',
                                             excerpt=record['text'][:160])
    jobs = []
    # Snowflake post IDs increase with publication time, including missing or
    # legacy date fields. New activity must not wait behind a historical backlog.
    for key in sorted(candidates, key=int, reverse=True):
        record = candidates[key]
        previous = documents.get(key, {})
        old_shot = previous.get('screenshot', {})
        needs_tall_recapture = old_shot.get('height', 0) > 1600 and old_shot.get('capture_version', 1) < 2
        discovery_digest = record.get('source_text_sha256')
        saved_digest = previous.get('discovery_text_sha256')
        changed = bool(discovery_digest and saved_digest and discovery_digest != saved_digest)
        if discovery_digest and not saved_digest and previous.get('full_text'):
            # Existing captures predate the all-activity archive. A matching
            # public prefix is sufficient to retain their full original capture.
            prefix = normalized(record.get('text', '')).removesuffix('…')
            changed = not normalized(previous['full_text']).startswith(prefix)
        filename = old_shot.get('file', '')
        safe_image = bool(re.fullmatch(re.escape(key) + r'-[a-f0-9]{16}\.jpg', filename))
        if previous.get('status') == 'ready' and not needs_tall_recapture and not changed and safe_image and (image_dir / filename).is_file():
            continue
        if previous.get('retry_after', 0) > now and not changed:
            continue
        jobs.append((key, record))
    return jobs


def signal_ai_ready(state):
    """Private marker for operators using a separate worker."""
    marker = state / 'ai-ready.signal'
    marker.write_text(utc_now() + '\n', encoding='utf-8')
    marker.chmod(0o640)


def storage_ready(state, manifest, manifest_path):
    free = shutil.disk_usage(state).free
    if free < MIN_FREE_BYTES:
        manifest['capture_error'] = {
            'code': 'storage_low', 'checked_at': utc_now(), 'free_bytes': free,
            'required_free_bytes': MIN_FREE_BYTES,
            'message': '截图采集已暂停：服务器可用磁盘不足 600 MiB；历史数据保留，释放空间后自动重试。',
        }
        manifest['updated_at'] = utc_now()
        atomic_json(manifest_path, manifest)
        print(json.dumps({'ok': False, 'paused': True, **manifest['capture_error']}, ensure_ascii=False), flush=True)
        return False
    if manifest.get('capture_error', {}).get('code') == 'storage_low':
        manifest.pop('capture_error')
        manifest['updated_at'] = utc_now()
        atomic_json(manifest_path, manifest)
    return True


def main(limit, state=STATE, on_ready=None):
    state = Path(state)
    image_dir = state / 'post-images'; image_dir.mkdir(exist_ok=True)
    manifest_path = state / 'post-content.json'
    manifest = read_json(manifest_path)
    documents = manifest.setdefault('posts', {})
    feed = read_json(state / 'data.json')
    archive = read_json(state / 'activity-archive.json')
    jobs = capture_jobs(feed, archive, documents, image_dir)
    if not storage_ready(state, manifest, manifest_path):
        return
    if not jobs:
        from thumbnails import build_thumbnails
        build_thumbnails(state)
        print(json.dumps({'pending': 0, 'ready': sum(p.get('status') == 'ready' for p in documents.values())}), flush=True)
        return
    attempted = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=True, proxy=capture_proxy())
        context = browser.new_context(viewport={'width': 440, 'height': 1000}, device_scale_factor=2,
                                      locale='en-US', timezone_id='Asia/Shanghai', color_scheme='light')
        page = context.new_page()
        for key, record in jobs[:limit]:
            if not storage_ready(state, manifest, manifest_path):
                break
            attempted += 1
            previous = documents.get(key, {})
            completed = False
            try:
                def save_text(value):
                    documents[key] = value
                    manifest['updated_at'] = utc_now(); atomic_json(manifest_path, manifest)
                documents[key] = capture(page, record, image_dir, on_text=save_text)
                completed = True
                print(json.dumps({'id': key, 'ok': True, 'text_chars': len(documents[key]['full_text']),
                                  'screenshot': documents[key]['screenshot']['file']}), flush=True)
            except Exception as error:
                attempts = previous.get('attempts', 0) + 1
                current = documents.get(key, previous)
                documents[key] = dict(current, status='text_ready' if current.get('status') == 'text_ready' else 'retrying',
                                      attempts=attempts, last_attempt=utc_now(),
                                      discovery_text_sha256=record.get('source_text_sha256'),
                                      retry_after=time.time() + min(86400, 900 * 2 ** min(attempts - 1, 6)),
                                      error=capture_error(error))
                print(json.dumps({'id': key, 'ok': False, 'error': documents[key]['error']}), flush=True)
            manifest['updated_at'] = utc_now(); atomic_json(manifest_path, manifest)
            from ai_publication import enabled
            if enabled(state):
                from ai_input import prepare_inputs
                prepare_inputs(state)
                if on_ready is not None:
                    on_ready()
            if completed:
                signal_ai_ready(state)
            time.sleep(2)
        context.close(); browser.close()
    from thumbnails import build_thumbnails
    build_thumbnails(state)
    print(json.dumps({'ready': sum(p.get('status') == 'ready' for p in documents.values()),
                      'attempted': attempted, 'pending_before': len(jobs)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--limit', type=int, default=6)
    parser.add_argument('--state', type=Path, default=STATE)
    args = parser.parse_args(); main(max(1, min(args.limit, 100)), args.state)
