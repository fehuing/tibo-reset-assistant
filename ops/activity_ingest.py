"""Archive public author-bound X activity, without deciding what it means.

Public SSR pages are incomplete discovery surfaces. This module deliberately
reports that limitation, retains failed attempts, and never imports another
tracker's descriptions or decisions. No credentials or authenticated API are
needed; an unavailable X surface is a collection error, not an empty timeline.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
import urllib.error
import urllib.request

from x_public import public_posts

AUTHOR = 'thsottiaux'
PROFILE = 'https://x.com/' + AUTHOR
SURFACES = (PROFILE, PROFILE + '/with_replies', PROFILE + '/media')
SOURCE = re.compile(r'https://x\.com/thsottiaux/status/(\d{10,25})$')
POST_LINK = re.compile(r'(?:https://x\.com)?/thsottiaux/status/(\d{10,25})(?=["\s?/#<]|$)')
DOCUMENT_LIMIT = 4 * 1024 * 1024
DIRECT_LIMIT = 4
STATE = Path('.data')


def read_json(path):
    """Do not silently replace an unreadable durable archive with an empty one."""
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object in ' + path.name)
    return value


def atomic_json(path, value, mode=0o640):
    """A private archive/manifest writer, independent of the public feed limit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def get_document(url):
    if url not in SURFACES and not SOURCE.fullmatch(url):
        raise ValueError('Unexpected public source')
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'en-US,en;q=0.8',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200 or response.url.rstrip('/') != url or urlsplit(response.url).hostname != 'x.com':
            raise ValueError('Unexpected public source response or redirect')
        raw = response.read(DOCUMENT_LIMIT + 1)
    if len(raw) > DOCUMENT_LIMIT:
        raise ValueError('X document exceeds collection size limit')
    return raw.decode('utf-8')


def valid_post(post):
    source = SOURCE.fullmatch(post.get('source_url', ''))
    if not source or source[1] != post.get('id') or post.get('author') != AUTHOR:
        return False
    if not isinstance(post.get('text'), str) or len(post['text']) > 60000:
        return False
    if not post['text'] and not post.get('has_media'):
        return False
    try:
        date = dt.datetime.fromisoformat(post['announced_at'].replace('Z', '+00:00'))
        return date.tzinfo is not None
    except (TypeError, KeyError, ValueError):
        return False


def merge_post(posts, post, now, surface):
    if not valid_post(post):
        return False
    key = post['id']
    previous = posts.get(key, {})
    digest = hashlib.sha256(post['text'].encode()).hexdigest()
    changed = previous.get('source_text_sha256') != digest
    source_fields = ('id', 'author', 'text', 'announced_at', 'source_url', 'reply_to_id',
                     'reply_context', 'quoted_id', 'quoted_context', 'has_media', 'media_only')
    row = {name: post[name] for name in source_fields if name in post}
    # A later profile response may omit the parent graph node. Retain previously
    # verified context only when the relationship still points to the same post.
    for kind in ('reply', 'quoted'):
        relation = 'reply_to_id' if kind == 'reply' else 'quoted_id'
        field = kind + '_context'
        if field not in row and row.get(relation) and row.get(relation) == previous.get(relation) and previous.get(field):
            row[field] = previous[field]
    row.update(first_seen_at=previous.get('first_seen_at', now), last_seen_at=now,
               content_changed_at=now if changed else previous.get('content_changed_at', now),
               source_text_sha256=digest, author_verified=True,
               discovered_via=sorted(set(previous.get('discovered_via', [])) | {surface}))
    posts[key] = row
    return not bool(previous)


def collect_activity(state=STATE, now=None, get=get_document):
    state = Path(state)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Collection timestamp needs a timezone')
    stamp = now.astimezone(dt.timezone.utc).isoformat()
    path = state / 'activity-archive.json'
    archive = read_json(path)
    posts = archive.setdefault('posts', {})
    if not isinstance(posts, dict):
        raise ValueError('Invalid durable activity archive')
    archive['schema_version'] = 1
    previous_coverage = archive.get('coverage', {})
    config = read_json(state / 'watch-config.json')
    errors, observations, direct = [], [], {}
    new_ids, seen_ids = set(), set()

    def ingest(document, surface, requested_id=None):
        parsed = [post for post in public_posts(document) if valid_post(post)]
        if requested_id and not any(post['id'] == requested_id for post in parsed):
            raise ValueError('Requested author-bound post missing from public document')
        if not parsed:
            raise ValueError('No author-bound public posts exposed by surface')
        for post in parsed:
            seen_ids.add(post['id'])
            if merge_post(posts, post, stamp, surface):
                new_ids.add(post['id'])
        return parsed

    def failure(url, error):
        code = 'x_unreachable'
        if isinstance(error, urllib.error.HTTPError):
            code = 'x_rate_limited' if error.code == 429 else 'x_http_error'
        elif isinstance(error, (ValueError, UnicodeError)):
            code = 'x_public_content_unavailable'
        errors.append({'surface': url, 'code': code, 'error_type': type(error).__name__,
                       'checked_at': stamp, 'http_status': getattr(error, 'code', None)})

    for url in SURFACES:
        try:
            document = get(url)
            # Permalinks can still be present when a public timeline omits graph
            # nodes. Every such link is verified on its own X page below.
            for match in POST_LINK.finditer(document):
                source = PROFILE + '/status/' + match[1]
                if match[1] not in posts:
                    direct.setdefault(source, url)
            parsed = ingest(document, url)
            observations.append({'surface': url, 'ok': True, 'authored_posts': len(parsed),
                                 'latest_post_at': max(post['announced_at'] for post in parsed),
                                 'document_sha256': hashlib.sha256(document.encode()).hexdigest()})
        except Exception as error:
            failure(url, error)
            observations.append({'surface': url, 'ok': False, 'authored_posts': 0})
    for source in config.get('source_urls', []):
        if isinstance(source, str) and SOURCE.fullmatch(source):
            direct.setdefault(source, 'user_reference')
    direct = {source: via for source, via in direct.items()
              if via == 'user_reference' or SOURCE.fullmatch(source)[1] not in seen_ids}
    # No reference tracker/API is called, even if a legacy config enables it.
    # Round-robin manual links so a long list cannot starve later URLs forever.
    ordered = sorted(direct, key=lambda source: int(SOURCE.fullmatch(source)[1]), reverse=True)
    cursor = int(previous_coverage.get('direct_cursor', 0)) % max(len(ordered), 1)
    rotated = ordered[cursor:] + ordered[:cursor]
    selected = rotated[:DIRECT_LIMIT]
    for url in selected:
        try:
            parsed = ingest(get(url), url, SOURCE.fullmatch(url)[1])
            observations.append({'surface': url, 'ok': True, 'authored_posts': len(parsed),
                                 'discovered_via': direct[url]})
        except Exception as error:
            failure(url, error)
            observations.append({'surface': url, 'ok': False, 'authored_posts': 0,
                                 'discovered_via': direct[url]})
    succeeded = any(row['ok'] for row in observations)
    coverage = {
        'mode': 'public_x_ssr', 'coverage': 'best_effort', 'checked_at': stamp,
        'last_success_at': stamp if succeeded else previous_coverage.get('last_success_at'),
        'status': 'partial' if succeeded and errors else 'ok' if succeeded else 'unavailable',
        'complete': False, 'reply_coverage': 'best_effort', 'retweet_coverage': 'not_guaranteed',
        'limitations': ['public_pages_may_omit_posts_or_replies', 'no_authenticated_pagination',
                       'retweets_without_verified_activity_identity_are_not_inferred'],
        'surfaces': observations, 'errors': errors,
        'new_posts': len(new_ids), 'seen_posts': len(seen_ids), 'archived_posts': len(posts),
        'direct_attempted': len(selected), 'direct_pending': max(0, len(ordered) - len(selected)),
        'direct_cursor': (cursor + len(selected)) % max(len(ordered), 1),
    }
    archive['coverage'] = coverage
    archive['updated_at'] = stamp
    atomic_json(path, archive)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=STATE)
    args = parser.parse_args()
    result = collect_activity(args.state)
    print(json.dumps(result['coverage'], ensure_ascii=False), flush=True)
