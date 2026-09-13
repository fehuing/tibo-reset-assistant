"""Public X hints, kept separate from reset announcements and their statistics.

No model, confidence score, or vote count is used to classify a hint. Public
reply discovery is best effort; the optional reference pointer supplies URLs
only. Each candidate must be verified against its own public X document.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from collector import atomic_json, read_json
from announcement_semantics import assess
from collection_status import diagnose

AUTHOR = 'thsottiaux'
PROFILE = 'https://x.com/' + AUTHOR
SOURCE = re.compile(r'https://x\.com/thsottiaux/status/(\d{10,25})$')
RESET = re.compile(r'\breset\w*\b', re.I)
CONTEXT = re.compile(r'\b(codex|chatgpt|usage|limits?|banked|credits?|allowance)\b', re.I)
HINT = re.compile(r'\b(who says|will|soon|might|may|could|tomorrow|later|stay tuned)\b|👀', re.I)
NEGATIVE = re.compile(r"\b(no reset|not resetting|won't reset|will not reset)\b", re.I)
VERSION = '2026-09-07.1'


def date(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp needs a timezone')
    return parsed


def get_document(url):
    if url not in (PROFILE, PROFILE + '/with_replies', 'https://codex-resets.com/api/v1/status') and not SOURCE.fullmatch(url):
        raise ValueError('Unexpected public source')
    request = urllib.request.Request(url, headers={'User-Agent': 'ResetRadar/1.0 (+public announcement tracker)', 'Accept': 'text/html,application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.url != url:
            raise ValueError('Unexpected source redirect')
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Document is too large')
    return raw.decode('utf-8')


def public_posts(document):
    """Resolve public SSR references without executing scripts or guessing authors.

    Replies contain multiple authors. A profile name appearing somewhere in a
    document does not establish the author of every tweet in that document.
    """
    starts = list(re.finditer(r'\{__id:"([^"\\]+)"', document))
    nodes = {}
    for index, match in enumerate(starts):
        segment = document[match.end():starts[index + 1].start() if index + 1 < len(starts) else len(document)]
        # Duplicate graph nodes sometimes omit fields; prefer the fuller node.
        if len(segment) > len(nodes.get(match[1], '')):
            nodes[match[1]] = segment

    def ref(node, field):
        value = re.search(r'\b' + field + r':(?:\$R\[\d+\]=)?\{__ref:"([^"\\]+)"', node)
        return value[1] if value else ''

    def string(node, field):
        value = re.search(r'\b' + field + r':"((?:\\.|[^"\\])*)"', node)
        return json.loads('"' + value[1] + '"') if value else ''

    posts = {}
    for node in nodes.values():
        if not node.startswith(',__typename:"Tweet",'):
            continue
        ident = string(node, 'rest_id')
        core = nodes.get(ref(node, 'core'), '')
        user_result = nodes.get(ref(core, 'user_results'), '')
        user = nodes.get(ref(user_result, 'result'), '')
        user_core = nodes.get(ref(user, 'core'), '')
        author = string(user_core, 'screen_name')
        details = nodes.get(ref(node, 'details'), '')
        body = string(details, 'full_text')
        timestamp = re.search(r'\bcreated_at_ms:(\d+)', details)
        if not re.fullmatch(r'\d{10,25}', ident) or not re.fullmatch(r'[A-Za-z0-9_]{1,30}', author) or not body or not timestamp:
            continue
        reply_result = nodes.get(ref(node, 'reply_to_results'), '')
        posts[ident] = {'id': ident, 'author': author, 'text': body,
                        'announced_at': dt.datetime.fromtimestamp(int(timestamp[1]) / 1000, dt.timezone.utc).isoformat(),
                        'source_url': f'https://x.com/{author}/status/{ident}',
                        'reply_to_id': string(reply_result, 'rest_id')}
    for post in posts.values():
        parent = posts.get(post['reply_to_id'])
        if parent:
            post['reply_context'] = {key: parent[key] for key in ('text', 'author', 'source_url')}
    return list(posts.values())


def hint_from_post(post, now, discovered_via):
    if post.get('author') != AUTHOR or not SOURCE.fullmatch(post.get('source_url', '')):
        return None
    published = date(post['announced_at'])
    if not dt.timedelta(0) <= now - published < dt.timedelta(hours=24):
        return None
    body = post['text'].replace('’', "'")
    context = post.get('reply_context', {}).get('text', '')
    if not RESET.search(body) or not CONTEXT.search(body + ' ' + context) or not HINT.search(body):
        return None
    if NEGATIVE.search(body) and not re.search(r'\bwho says\b', body, re.I):
        return None
    if assess(body)['status'] == 'announced':
        return None
    return {'episode_id': post['id'], 'source_url': post['source_url'], 'text': post['text'],
            'reply_context': post.get('reply_context'), 'observed_at': post['announced_at'],
            'expires_at': (published + dt.timedelta(hours=24)).isoformat(), 'window_hours': 24,
            'window_basis': 'site_observation_window', 'discovered_via': discovered_via,
            'evidence': {'method': 'public_x_source_rules', 'version': VERSION,
                         'source_sha256': hashlib.sha256(post['text'].encode()).hexdigest()}}


def watch_state(watch, feed, now):
    if not watch:
        return 'empty'
    if any(event.get('status') == 'announced' and event.get('reset_type', 'regular') == watch.get('reset_type', 'regular') and
           ((event.get('watch_episode_id') == watch['episode_id']) if event.get('confirmation_method') == 'private_reset_report' else
            (watch['episode_id'] in event.get('record_ids', []) or date(event['announced_at']) > date(watch['observed_at'])))
           for event in feed.get('events', [])):
        return 'new_announcement'
    if watch.get('window_basis') == 'until_reset_confirmed':
        return 'active'
    return 'expired' if now >= date(watch['expires_at']) else 'active'


def collect_watch(state, get=get_document, now=None):
    from ai_publication import enabled
    if enabled(state):
        return read_json(state / 'watch.json')
    now = now or dt.datetime.now(dt.timezone.utc)
    previous = read_json(state / 'watch.json')
    config = read_json(state / 'watch-config.json')
    errors, candidates, urls = [], [], {}
    successful_discovery = False
    # These public surfaces may omit replies or stop exposing SSR data.
    for url in (PROFILE, PROFILE + '/with_replies'):
        try:
            posts = public_posts(get(url))
            if not any(post['author'] == AUTHOR for post in posts):
                raise ValueError('No authored public posts')
            successful_discovery = True
            for post in posts:
                if hint_from_post(post, now, 'x_public_timeline'):
                    urls[post['source_url']] = 'x_public_timeline'
        except Exception as error:
            errors.append({'surface': url, **diagnose(error)})
    # Existing user-provided source links bootstrap discovery, never text/state.
    for url in config.get('source_urls', []):
        if SOURCE.fullmatch(url):
            urls.setdefault(url, 'user_reference')
    # Optional URL discovery for otherwise unavailable public replies. The
    # reference's forecast, counts, text and deadline are never imported.
    if config.get('reference_discovery', False):
        try:
            pointer = json.loads(get('https://codex-resets.com/api/v1/status'))['data'].get('active_watch')
            url = (pointer or {}).get('source', {}).get('url', '')
            if SOURCE.fullmatch(url):
                urls.setdefault(url, 'reference_pointer')
        except Exception as error:
            errors.append({'surface': 'reference_pointer', **diagnose(error)})
    old = previous.get('watch')
    if old and now < date(old['expires_at']):
        urls.setdefault(old['source_url'], old['discovered_via'])
    for url, discovery in list(urls.items())[:4]:
        try:
            document = get(url)
            ident = SOURCE.fullmatch(url)[1]
            post = next(post for post in public_posts(document) if post['id'] == ident and post['author'] == AUTHOR)
            hint = hint_from_post(post, now, discovery)
            if hint:
                hint['verified_at'] = now.isoformat()
                hint['evidence']['document_sha256'] = hashlib.sha256(document.encode()).hexdigest()
                candidates.append(hint)
        except Exception as error:
            errors.append({'surface': url, **diagnose(error)})
            if old and old.get('source_url') == url:
                candidates.append(old)  # Expiry/verification timestamp never advance.
    watch = max(candidates, key=lambda hint: date(hint['observed_at']), default=None)
    if watch is None and old and now - date(old['expires_at']) < dt.timedelta(hours=24):
        watch = old
    result = {'schema_version': 1, 'checked_at': now.isoformat(), 'watch': watch,
              'collection': {'public_timeline_read': successful_discovery, 'reply_coverage': 'best_effort', 'errors': errors}}
    atomic_json(state / 'watch.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=Path('.data'))
    args = parser.parse_args()
    result = collect_watch(args.state)
    print(json.dumps({'ok': True, 'watch': (result['watch'] or {}).get('episode_id'), 'errors': result['collection']['errors']}))
