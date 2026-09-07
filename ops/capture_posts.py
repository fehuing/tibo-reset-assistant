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
import tempfile
import time
from urllib.parse import urlsplit
import urllib.request
from playwright.sync_api import sync_playwright

STATE = Path('.data')
SOURCE = re.compile(r'https://x\.com/thsottiaux/status/(\d+)$')


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
        if received.status != 200 or urlsplit(received.url).hostname != 'x.com':
            raise ValueError('Public X document unavailable')
        document = received.read(2 * 1024 * 1024 + 1)
        if len(document) > 2 * 1024 * 1024:
            raise ValueError('X document exceeds limit')
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
    if body.count():
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
    if not full_text or len(full_text) > 60000:
        raise ValueError('Invalid full text length')
    visible = normalized(article.inner_text())
    # Reply recipients can be in the page heading but omitted from the post body.
    visible_body = re.sub(r'^(?:@[A-Za-z0-9_]+\s+)+', '', normalized(full_text))
    if normalized(full_text) not in visible and (not visible_body or visible_body not in visible):
        raise ValueError('Full text is not completely visible in the screenshot area')
    # Quoted-post t.co links become quote cards in X's visible layout.
    excerpt = normalized(re.sub(r'https://t\.co/\S+', '', record['excerpt'])).removesuffix('…')
    if record['source_type'] == 'x_post' and not normalized(full_text).startswith(excerpt):
        raise ValueError('Page text does not match the saved announcement')
    content = {'full_text': full_text, 'text_source': 'x_post_page', 'text_captured_at': utc_now(),
               'full_text_sha256': hashlib.sha256(full_text.encode()).hexdigest(), 'status': 'text_ready'}
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


def main(limit, state=STATE):
    image_dir = state / 'post-images'; image_dir.mkdir(exist_ok=True)
    manifest_path = state / 'post-content.json'
    manifest = read_json(manifest_path)
    documents = manifest.setdefault('posts', {})
    feed = read_json(state / 'data.json')
    jobs = []
    seen = set()
    for record in feed.get('records', []):
        match = SOURCE.fullmatch(record['source_url'])
        if not match or match.group(1) in seen:
            continue
        key = match.group(1); seen.add(key)
        previous = documents.get(key, {})
        old_shot = previous.get('screenshot', {})
        needs_tall_recapture = old_shot.get('height', 0) > 1600 and old_shot.get('capture_version', 1) < 2
        if previous.get('status') == 'ready' and not needs_tall_recapture and (image_dir / old_shot.get('file', 'missing')).is_file():
            continue
        if previous.get('retry_after', 0) > time.time():
            continue
        jobs.append((key, record))
    if not jobs:
        from thumbnails import build_thumbnails
        build_thumbnails(state)
        print(json.dumps({'pending': 0, 'ready': sum(p.get('status') == 'ready' for p in documents.values())}), flush=True)
        return
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context(viewport={'width': 440, 'height': 1000}, device_scale_factor=2,
                                      locale='en-US', timezone_id='Asia/Shanghai', color_scheme='light')
        page = context.new_page()
        for key, record in jobs[:limit]:
            previous = documents.get(key, {})
            try:
                def save_text(value):
                    documents[key] = value
                    manifest['updated_at'] = utc_now(); atomic_json(manifest_path, manifest)
                documents[key] = capture(page, record, image_dir, on_text=save_text)
                print(json.dumps({'id': key, 'ok': True, 'text_chars': len(documents[key]['full_text']),
                                  'screenshot': documents[key]['screenshot']['file']}), flush=True)
            except Exception as error:
                attempts = previous.get('attempts', 0) + 1
                documents[key] = dict(documents.get(key, previous), attempts=attempts, last_attempt=utc_now(),
                                      retry_after=time.time() + min(86400, 900 * 2 ** min(attempts - 1, 6)),
                                      error=type(error).__name__ + ': ' + str(error)[:300])
                print(json.dumps({'id': key, 'ok': False, 'error': documents[key]['error']}), flush=True)
            manifest['updated_at'] = utc_now(); atomic_json(manifest_path, manifest)
            time.sleep(2)
        context.close(); browser.close()
    from thumbnails import build_thumbnails
    build_thumbnails(state)
    print(json.dumps({'ready': sum(p.get('status') == 'ready' for p in documents.values()),
                      'attempted': min(limit, len(jobs)), 'pending_before': len(jobs)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--limit', type=int, default=6)
    parser.add_argument('--state', type=Path, default=STATE)
    args = parser.parse_args(); main(max(1, min(args.limit, 100)), args.state)
