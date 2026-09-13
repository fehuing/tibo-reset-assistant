"""Public translation progress, separate from reset-delivery evidence."""
STATES = {'pending', 'translating', 'retrying', 'unavailable', 'ready', 'awaiting_text'}


def matching_translation(record):
    translation = record.get('translation_zh') or {}
    return bool(record.get('text_complete') and record.get('full_text_sha256')
                and translation.get('source_sha256') == record['full_text_sha256']
                and isinstance(translation.get('text'), str) and translation['text'].strip())


def attach_translation_status(feed, queue):
    posts = queue.get('posts', {})
    for record in feed['records']:
        digest = record.get('full_text_sha256')
        item = dict(posts.get(record['source_url'].rsplit('/', 1)[-1], {}))
        item['state'] = {'analyzing': 'translating', 'pending_content': 'awaiting_text'}.get(item.get('state'), item.get('state'))
        if item.get('retry_at'):
            item['next_retry_at'] = item['retry_at']
        if item.get('started_at'):
            item['last_attempt_at'] = item['started_at']
        if matching_translation(record):
            view = {'state': 'ready', 'source_sha256': digest,
                    'translated_at': record['translation_zh'].get('translated_at')}
        elif not record.get('text_complete'):
            view = {'state': 'awaiting_text'}
        elif item.get('source_sha256') == digest and item.get('state') in STATES - {'ready'}:
            view = {key: item[key] for key in ('state', 'source_sha256', 'attempts', 'last_attempt_at', 'next_retry_at', 'error_code') if key in item}
        else:
            view = {'state': 'pending', 'source_sha256': digest}
        record['translation_status'] = view
    return feed
