"""Publish validated model interpretations; never classify source prose here.

The model interprets language. This module checks identity/provenance and applies
the site's state policy, retaining the sealed historical and private ledgers.
"""
import argparse
import copy
import datetime as dt
from pathlib import Path
import re

from collector import read_json, atomic_json, _feed, attach_post_content, parse_date
from announcement_semantics import build_events
from historical_baseline import load_baseline, apply_baseline
from publication_state import publication_lock, apply_private_reports
from post_briefs import attach_briefs
from translation_state import attach_translation_status

VERSION = 'gpt6-2026-09-13.1'
from ai_config import MODEL, analysis_dir as configured_analysis_dir
RESULTS = None
ANNOUNCEMENT_FIELDS = (
    'id', 'source_type', 'announced_at', 'source_url', 'excerpt', 'source_text',
    'collected_at', 'last_seen_at', 'full_text', 'text_complete', 'text_source',
    'text_captured_at', 'full_text_sha256', 'translation_zh', 'translation_status',
    'brief', 'screenshot',
)


def enabled(state):
    return read_json(Path(state) / 'ai-config.json').get('enabled') is True


def protected(record):
    return bool(record.get('historical_verification') or
                record.get('reset_confirmation', {}).get('method') == 'private_reset_report')


def public_analysis(envelope):
    result = envelope['result']
    return {'method': 'codex_cli', 'model': envelope['model'], 'analyzed_at': envelope['analyzed_at'],
            'prompt_version': envelope['prompt_version'], 'source_sha256': result['source_sha256'],
            **{k: result[k] for k in ('translation_zh', 'summary_zh', 'summary_en', 'signal', 'scope', 'prediction', 'evidence')},
            'related_post_id': result['related_post_id'], 'reset_at': result['reset_at']}


def eligible(result):
    # A personal reset/card and image-only speculation cannot publish a public
    # global reset. The exact evidence was checked against the original body.
    return (result['relevance'] == 'reset' and result['scope'] != 'personal'
            and bool(result['evidence']))


def apply_decisions(existing, archive, envelopes, now):
    """Pure deterministic merge of already validated results (easy to audit)."""
    rows = {r['id']: copy.deepcopy(r) for r in existing.get('records', [])}
    for ident, envelope in envelopes.items():
        post = archive['posts'][ident]
        result = envelope['result']
        old = rows.get(ident)
        # Previously verified history/actual times win over a model reading of
        # the original announcement's future tense, forever.
        if old and protected(old):
            old['ai_analysis'] = public_analysis(envelope)
            continue
        accepted = eligible(result)
        signal = result['signal']
        public_record = accepted and signal in ('announced', 'in_progress', 'delivered')
        if not public_record:
            if old and old.get('ai_analysis', {}).get('method') == 'codex_cli':
                # A source edit/reanalysis can withdraw an unverified AI entry.
                # Owner-confirmed entries took the protected branch above.
                rows.pop(ident)
            continue
        if result['reset_type'] == 'unknown':
            # Unknown type can create a watch, but cannot silently become a
            # direct reset or a banked card in the calendar.
            if old and old.get('ai_analysis', {}).get('method') == 'codex_cli':
                rows.pop(ident)
            continue
        target = rows.get(result.get('related_post_id'))
        if target and protected(target):
            # A follow-up to a sealed event is archived without counting the
            # same reset twice or editing the owner's durable confirmation.
            if old and old.get('ai_analysis', {}).get('method') == 'codex_cli':
                rows.pop(ident)
            continue
        status = ('announced' if signal == 'delivered' and result['scope'] in ('global', 'group')
                  else 'planned' if signal in ('announced', 'in_progress') else 'uncertain')
        row = dict(old or {}, id=ident, source_type='x_post', reset_type=result['reset_type'],
                   announced_at=post['announced_at'], source_url=post['source_url'],
                   source_text=post['text'], excerpt=result['summary_en'], status=status, source_status=status,
                   collected_at=post['first_seen_at'], last_seen_at=post['last_seen_at'],
                   ai_analysis=public_analysis(envelope))
        row['assessment'] = {'method': 'codex_cli', 'version': VERSION, 'rule': 'model_' + signal,
                             'quote': '\n'.join(result['evidence'])[:2000], 'source_sha256': result['source_sha256']}
        row['source_assessment'] = dict(row['assessment'])
        row.pop('confirmation', None)
        if post.get('reply_to_id'):
            row['in_reply_to_status_id'] = post['reply_to_id']
        rows[ident] = row
    return _feed(list(rows.values()), now, {'active': 'x_direct', 'primary': 'https://x.com/thsottiaux',
                   'fallback_used': False, 'interpretation': MODEL, 'coverage': archive.get('coverage', {})},
                 max((p['announced_at'] for p in archive.get('posts', {}).values()), default=None))


def build_announcements(feed, archive, envelopes):
    """Project source posts for reading, independently of reset-event grouping.

    The existing historical list is retained. Current validated reset-related
    posts can appear here even when they are hints, have an unknown reset type,
    or follow up an already confirmed event. No state/statistics are inferred.
    """
    def key(row):
        return row['source_url'].split('?', 1)[0].split('#', 1)[0]

    rows = {}
    for record in feed.get('records', []):
        source = key(record)
        # An original post is preferable to a legacy observed duplicate.
        if source in rows and record.get('source_type') == 'observed':
            continue
        rows[source] = {field: copy.deepcopy(record[field])
                        for field in ANNOUNCEMENT_FIELDS if field in record}
    for ident, envelope in envelopes.items():
        result = envelope['result']
        if not eligible(result) or result['signal'] not in (
                'hint', 'announced', 'in_progress', 'delivered', 'denied'):
            continue
        post = archive['posts'][ident]
        source = key(post)
        row = rows.get(source, {})
        row.update(id=ident, source_type='x_post', announced_at=post['announced_at'],
                   source_url=post['source_url'], source_text=post['text'],
                   excerpt=result['summary_en'], collected_at=post['first_seen_at'],
                   last_seen_at=post['last_seen_at'])
        rows[source] = row
    return sorted(rows.values(), key=lambda row: parse_date(row['announced_at']), reverse=True)


def attach_model_briefs(feed, envelopes):
    """Use a model summary only for the exact archived body it interpreted."""
    for row in feed['records']:
        env = envelopes.get(row['id'])
        if env and row.get('full_text_sha256') == env['result']['source_sha256']:
            result = env['result']
            row['brief'] = {'method': 'codex_cli', 'translation_method': 'codex_cli',
                            'source_sha256': result['source_sha256'],
                            'zh': {'summary': result['summary_zh'], 'scope': '', 'action': ''},
                            'en': {'summary': result['summary_en'], 'scope': '', 'action': ''}}
    return feed


def make_watch(feed, archive, envelopes, manifest, previous, now, closures=None):
    candidates = []
    for ident, envelope in envelopes.items():
        r = envelope['result']; post = archive['posts'][ident]
        if not eligible(r) or r['signal'] not in ('hint', 'announced', 'in_progress'):
            continue
        published = parse_date(post['announced_at'])
        kind = r['reset_type'] if r['reset_type'] != 'unknown' else 'regular'
        cutoff = max((parse_date((row.get('reset_confirmation') or {}).get('reset_at') or row['announced_at'])
                      for row in feed['records'] if row.get('status') == 'announced' and row.get('reset_type') == kind),
                     default=dt.datetime.min.replace(tzinfo=dt.timezone.utc))
        if published <= cutoff or published > now:
            continue
        if ident in (closures or {}).get('episodes', {}):
            continue
        # Closing a related announcement must not leave its earlier hint live.
        linked = [e['result'] for e in envelopes.values() if e['result'].get('related_post_id') == ident
                  and eligible(e['result']) and e['result']['reset_type'] in (kind, 'unknown')]
        if any(item['signal'] == 'denied' or (item['signal'] == 'delivered' and item['scope'] in ('global', 'group')) for item in linked):
            continue
        watch = {'episode_id': ident, 'source_url': post['source_url'], 'text': post['text'],
                 'reply_context': post.get('reply_context'), 'observed_at': post['announced_at'],
                 # Retain these fields for older clients' schema validation.
                 # The until_reset_confirmed policy does not expire at this time.
                 'expires_at': (published + dt.timedelta(hours=24)).isoformat(), 'window_hours': 24,
                 'reset_type': kind,
                 'window_basis': 'until_reset_confirmed', 'discovered_via': 'x_public_activity',
                 'verified_at': post['last_seen_at'], 'analysis': public_analysis(envelope),
                 'evidence': {'method': 'codex_cli', 'version': VERSION, 'rule': 'model_' + r['signal'],
                              'source_sha256': r['source_sha256']}}
        content = manifest.get('posts', {}).get(ident, {})
        if content.get('full_text_sha256') == r['source_sha256']:
            watch['text'] = content.get('full_text', post['text'])
            if content.get('screenshot'):
                watch['screenshot'] = content['screenshot']
        candidates.append(watch)
    watch = max(candidates, key=lambda w: parse_date(w['observed_at']), default=None)
    # Valid cached results are already included above. A missing/stale result
    # cannot revive an earlier watch while edited source text awaits analysis.
    return {'schema_version': 1, 'checked_at': now.isoformat(), 'watch': watch,
            'collection': archive.get('coverage', {}), 'interpretation': MODEL}


def load_envelopes(state, archive, manifest, analysis_dir):
    from ai_analysis import make_input, input_fingerprint, validate_result
    accepted, rejected = {}, []
    for ident, post in archive.get('posts', {}).items():
        if not re.fullmatch(r'\d{10,25}', ident):
            continue
        path = analysis_dir / 'results' / (ident + '.json')
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > 1024 * 1024:
                raise ValueError('Oversized model result')
            env = read_json(path)
            if env.get('status') != 'ready' or env.get('model') != MODEL:
                raise ValueError('Unexpected model result envelope')
            source = make_input(ident, post, manifest.get('posts', {}).get(ident, {}), state)
            if env['input_sha256'] != input_fingerprint(source):
                raise ValueError('Stale model result')
            validate_result(env['result'], source)
            parse_date(env['analyzed_at'])
            accepted[ident] = env
        except (ValueError, TypeError, KeyError, OSError) as error:
            rejected.append({'id': ident, 'error': type(error).__name__})
    return accepted, rejected


def publish_ai(state, archive=None, analysis_dir=RESULTS, now=None):
    state = Path(state)
    analysis_dir = Path(analysis_dir) if analysis_dir is not None else configured_analysis_dir(state)
    now = now or dt.datetime.now(dt.timezone.utc)
    with publication_lock(state):
        archive = read_json(state / 'activity-archive.json') or archive or {'posts': {}}
        manifest = read_json(state / 'post-content.json')
        envelopes, rejected = load_envelopes(state, archive, manifest, analysis_dir)
        baseline = load_baseline(state / 'historical-baseline.json')
        existing = apply_baseline(read_json(state / 'data.json'), baseline)
        existing = apply_private_reports(existing, state)
        feed = apply_decisions(existing, archive, envelopes, now)
        # Preserve hashes/translations and screenshots already archived; replace
        # the translation only when the model processed the exact current body.
        translations = read_json(state / 'post-translations.zh.json')
        for ident, env in envelopes.items():
            r = env['result']
            translations[ident] = {'text': r['translation_zh'], 'source_sha256': r['source_sha256'],
                                   'method': 'codex_cli', 'engine': env['model'], 'translated_at': env['analyzed_at']}
        feed = attach_post_content(feed, {}, manifest, translations)
        feed = apply_baseline(feed, baseline)
        feed = apply_private_reports(feed, state)
        feed = attach_translation_status(feed, read_json(analysis_dir / 'state.json'))
        feed = attach_briefs(feed)
        feed = attach_model_briefs(feed, envelopes)
        feed['semantics_version'] = VERSION
        queue = read_json(analysis_dir / 'state.json')
        feed['analysis_pipeline'] = {'method': 'codex_cli', 'model': MODEL,
              'archive_count': len(archive.get('posts', {})), 'validated_results': len(envelopes),
              'rejected_results': len(rejected), 'coverage': archive.get('coverage', {}),
              'worker_updated_at': queue.get('updated_at')}
        feed = build_events(feed)
        display = {'records': build_announcements(feed, archive, envelopes)}
        display = attach_post_content(display, {}, manifest, translations)
        display = attach_translation_status(display, queue)
        display = attach_model_briefs(attach_briefs(display), envelopes)
        feed['announcements'] = display['records']
        watch = make_watch(feed, archive, envelopes, manifest, read_json(state / 'watch.json'), now,
                           read_json(state / 'watch-closures.json'))
        atomic_json(state / 'data.json', feed)
        atomic_json(state / 'watch.json', watch)
    return feed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--state', type=Path, default=Path('.data'))
    args = parser.parse_args()
    if enabled(args.state):
        result = publish_ai(args.state)
        print({'ok': True, 'records': len(result['records']), 'validated': result['analysis_pipeline']['validated_results']})
