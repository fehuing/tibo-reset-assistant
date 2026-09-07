"""Conservative, reproducible interpretation of public announcements.

This describes what an author said, never the state of a personal account.
Only English source text is classified; translations are display-only.
"""
import hashlib
import re
import datetime as dt

VERSION = '2026-09-06.1'
RESET = re.compile(r'\b(?:reset\w*|banked credit)\b', re.I)
CONTEXT = re.compile(r'\b(?:codex|chatgpt|usage|limits?|paid|subscriptions?|accounts?|users?|banked|credits?|allowances?)\b', re.I)
BANKED = re.compile(r'\b(?:banked reset|reset card|saved reset|banked credit)\b', re.I)
NEGATIVE = re.compile(r"\b(?:not|never|no|won't|haven't|hasn't|didn't|cannot|can't|don't|doesn't)\s+(?:(?:be|been|have|going to|yet|currently|actually|now|a|any)\s+){0,3}(?:reset\w*|credit\w*|land\w*|deliver\w*)\b|\breset\w*\s+(?:is |was |has been )?(?:cancelled|canceled)\b", re.I)
FUTURE = re.compile(r"\b(?:will|we'll|going to|plan to|planning to|intend to|soon|tomorrow|later today)\b[^.!?\n]{0,100}\b(?:reset\w*|credit\w*|give|grant)\b|\b(?:lands?|arrives?|will land)\b[^.!?\n]{0,65}\b(?:end of day|today|hours?|tomorrow|by)\b", re.I)
DELIVERED = re.compile(r"\b(?:we (?:have |have now |just |already |now )?reset|we've (?:just |now |already )?reset|(?:usage|limits?|accounts?) (?:have |has |were |are |was )?(?:been )?(?:now |just |already )?reset|reset(?:s)? (?:has |have )?(?:been )?(?:propagated|delivered|applied|completed)|(?:credited|granted|issued|added|delivered)\b[^.!?\n]{0,70}\b(?:reset|credit)|(?:banked reset|reset card)\b[^.!?\n]{0,40}\b(?:available now|now available|is available))\b", re.I)
IN_PROGRESS = re.compile(r"\b(?:we are|we're|currently|now)\s+(?:resetting|reseting|rolling out|crediting)\b", re.I)
SPECULATIVE = re.compile(r'\b(?:if|might|maybe|could|should we|would you|wish|hope to)\b', re.I)


def source_body(record):
    return (record.get('full_text') if record.get('text_complete') else None) or record.get('source_text') or record.get('excerpt', '')


def assess(text, source_type='x_post'):
    text = str(text or '')
    normalized = text.replace('’', "'")
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', normalized) if s.strip()]
    relevant = [s for s in sentences if RESET.search(s)]
    evidence = relevant[0] if relevant else (sentences[0] if sentences else '')
    kind = 'banked' if BANKED.search(normalized) else 'regular'
    state, rule = 'uncertain', 'ambiguous_or_missing_evidence'
    if source_type == 'observed':
        rule = 'observation_is_not_author_confirmation'
    elif not relevant or not CONTEXT.search(normalized):
        rule = 'insufficient_reset_context'
    elif any(NEGATIVE.search(s) for s in relevant):
        evidence = next(s for s in relevant if NEGATIVE.search(s))
        rule = 'negation_requires_review'
    elif any(SPECULATIVE.search(s) for s in relevant):
        evidence = next(s for s in relevant if SPECULATIVE.search(s))
        rule = 'conditional_or_speculative'
    elif any(FUTURE.search(s) for s in sentences):
        state, rule = 'planned', 'future_or_scheduled_rollout'
        evidence = next(s for s in sentences if FUTURE.search(s))
    elif any(IN_PROGRESS.search(s) for s in relevant):
        state, rule = 'planned', 'rollout_in_progress'
        evidence = next(s for s in relevant if IN_PROGRESS.search(s))
    elif any(DELIVERED.search(s) for s in relevant):
        state, rule = 'announced', 'explicit_author_delivery_statement'
        evidence = next(s for s in relevant if DELIVERED.search(s))
    return {
        'status': state, 'reset_type': kind,
        'assessment': {'version': VERSION, 'method': 'source_rules', 'rule': rule,
                       'quote': evidence[:700], 'source_sha256': hashlib.sha256(text.encode()).hexdigest()},
    }


def annotate_records(feed):
    for record in feed['records']:
        result = assess(source_body(record), record.get('source_type'))
        # Preserve a historical category when the source does not establish one.
        record['status'] = result['status']
        record['assessment'] = result['assessment']
    feed['semantics_version'] = VERSION
    return feed


def build_events(feed):
    """Merge only an explicit same-author reference, never temporal proximity.

    Unresolved and planned events remain available in the event ledger, but
    only events with explicit author delivery statements enter the calendar.
    """
    records = feed['records']
    by_id = {r['id']: r for r in records}
    parent = {r['id']: r['id'] for r in records}

    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key

    for record in sorted(records, key=lambda r: r['announced_at']):
        refs = re.findall(r'https://(?:www\.)?x\.com/thsottiaux/status/(\d+)', source_body(record))
        if record.get('in_reply_to_status_id'):
            refs.append(str(record['in_reply_to_status_id']))
        # A reference alone can be a comparison. Require explicit follow-up wording.
        followup = re.search(r'\b(?:update|follow.up|this reset|that reset|the reset|as promised|has been propagated|now (?:landed|delivered))\b', source_body(record), re.I)
        candidates = [ref for ref in refs if ref in by_id and ref != record['id']
                      and by_id[ref]['reset_type'] == record['reset_type']
                      and by_id[ref]['source_type'] == record['source_type'] == 'x_post'
                      and by_id[ref]['announced_at'] < record['announced_at']]
        if followup and len(set(candidates)) == 1:
            target = candidates[0]
            parent[root(record['id'])] = root(target)
            record['event_link_evidence'] = {'method': 'explicit_source_reference', 'related_id': target}
        else:
            record.pop('event_link_evidence', None)

    grouped = {}
    for record in records:
        event_id = 'event-' + root(record['id'])
        record['event_id'] = event_id
        grouped.setdefault(event_id, []).append(record)
    events = []
    for event_id, posts in grouped.items():
        posts.sort(key=lambda r: r['announced_at'])
        confirmed = [r for r in posts if r['status'] == 'announced']
        status = 'announced' if confirmed else 'planned' if any(r['status'] == 'planned' for r in posts) else 'uncertain'
        representative = confirmed[0] if confirmed else posts[-1]
        event = {'id': event_id, 'reset_type': representative['reset_type'], 'status': status,
                 'announced_at': representative['announced_at'], 'record_id': representative['id'],
                 'record_ids': [r['id'] for r in posts], 'source_url': representative['source_url']}
        events.append(event)
        for record in posts:
            record['related_record_ids'] = [r['id'] for r in posts if r['id'] != record['id']]
    events.sort(key=lambda e: e['announced_at'], reverse=True)
    confirmed = [e for e in events if e['status'] == 'announced']
    times = [dt.datetime.fromisoformat(e['announced_at'].replace('Z', '+00:00')) for e in confirmed]
    intervals = [(a - b).total_seconds() / 86400 for a, b in zip(times, times[1:])]
    feed['events'] = events
    feed['event_stats'] = {
        'total': len(confirmed), 'announcement_total': len(records),
        'regular': sum(e['reset_type'] == 'regular' for e in confirmed),
        'banked': sum(e['reset_type'] == 'banked' for e in confirmed),
        'planned': sum(e['status'] == 'planned' for e in events),
        'uncertain': sum(e['status'] == 'uncertain' for e in events),
        'avg_interval_days': round(sum(intervals) / len(intervals), 1) if intervals else None,
        'longest_interval_days': round(max(intervals), 1) if intervals else None,
        'basis': 'explicit_author_delivery_statement',
    }
    # stats remains the legacy post-count contract for already-released clients.
    return feed
