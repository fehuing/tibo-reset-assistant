"""Extract short, attributed reading aids without generating new claims."""
import re
from announcement_semantics import source_body


def sentences(body, chinese=False):
    # Parenthetical punctuation belongs to the same source sentence. Splitting
    # there can discard the qualifier and leave a summary starting with ")".
    parts, start, depth = [], 0, 0
    stops = '。！？' if chinese else '.!?'
    for i, char in enumerate(body):
        if char in '(（':
            depth += 1
        elif char in ')）':
            depth = max(0, depth - 1)
        boundary = char == '\n' or char in stops and (chinese or i + 1 == len(body) or body[i + 1].isspace())
        if boundary and not depth:
            if body[start:i + 1].strip():
                parts.append(body[start:i + 1].strip())
            start = i + 1
    if body[start:].strip():
        parts.append(body[start:].strip())
    return parts


def extract(body, chinese=False):
    parts = sentences(body, chinese)
    relevant = re.compile(r'重置|额度|限额|使用量' if chinese else r'\breset\w*\b|\busage\b', re.I)
    summary = next((part for part in parts if relevant.search(part)), parts[0] if parts else '')
    # Whole sentences preserve qualifiers such as "some", "not yet", and "if".
    scope = re.compile(r'(?:所有|部分|符合|订阅|付费|Plus|Pro|Business).{0,60}(?:用户|账户|计划)' if chinese else r'\b(?:all|some|paid|eligible|Plus|Pro|Business)\b.{0,65}\b(?:users?|accounts?|plans?|subscriptions?)\b', re.I)
    action = re.compile(r'领取|兑换|手动|点击|升级|创建.{0,20}账户|无需' if chinese else r'\b(?:redeem|claim|manually|click|upgrade|create (?:your |an? |the )?account|no action)\b', re.I)
    return {'summary': summary[:500] + ('…' if len(summary) > 500 else ''),
            'scope': next((part[:500] for part in parts if scope.search(part)), ''),
            'action': next((part[:500] for part in parts if action.search(part)), '')}


def attach_briefs(feed):
    for record in feed['records']:
        source = source_body(record)
        value = {'method': 'source_sentence_extract', 'en': extract(source)}
        translation = record.get('translation_zh', {})
        if record.get('text_complete') and translation.get('source_sha256') == record.get('full_text_sha256') and translation.get('text'):
            value['zh'] = extract(translation['text'], True)
            value['translation_method'] = translation.get('method', 'archived_translation')
        record['brief'] = value
    return feed
