"""Read author-bound public X graph nodes, including full long-post text."""
import re
import json
import datetime as dt

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
        try:
            return json.loads('"' + value[1] + '"') if value else ''
        except (ValueError, TypeError):
            return ''

    def has_refs(node, field):
        value = re.search(r'\b' + field + r':(?:\$R\[\d+\]=)?\{__refs:(?:\$R\[\d+\]=)?\[([^\]]*)\]', node)
        return bool(value and value[1].strip())

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
        note = nodes.get(ref(node, 'note_tweet'), '')
        note_results = nodes.get(ref(note, 'note_tweet_results'), '')
        note_body = string(nodes.get(ref(note_results, 'result'), ''), 'text')
        if note_body:
            body = note_body
        quote_results = nodes.get(ref(node, 'quoted_tweet_results'), '')
        quoted = nodes.get(ref(quote_results, 'result'), '')
        timestamp = re.search(r'\bcreated_at_ms:(\d+)', details)
        has_media = has_refs(node, 'media_entities2') or has_refs(node, 'media_entities')
        if not re.fullmatch(r'\d{10,25}', ident) or not re.fullmatch(r'[A-Za-z0-9_]{1,30}', author) or (not body and not has_media) or not timestamp:
            continue
        try:
            announced_at = dt.datetime.fromtimestamp(int(timestamp[1]) / 1000, dt.timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            continue
        reply_result = nodes.get(ref(node, 'reply_to_results'), '')
        posts[ident] = {'id': ident, 'author': author, 'text': body,
                        'announced_at': announced_at,
                        'source_url': f'https://x.com/{author}/status/{ident}',
                        'reply_to_id': string(reply_result, 'rest_id'),
                        'quoted_id': string(quoted, 'rest_id') or string(quote_results, 'rest_id'),
                        'has_media': has_media, 'media_only': bool(has_media and not body)}
    for post in posts.values():
        parent = posts.get(post['reply_to_id'])
        if parent:
            post['reply_context'] = {key: parent[key] for key in ('text', 'author', 'source_url')}
        quoted = posts.get(post['quoted_id'])
        if quoted:
            post['quoted_context'] = {key: quoted[key] for key in ('text', 'author', 'source_url')}
    return list(posts.values())
