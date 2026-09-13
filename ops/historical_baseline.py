"""Sealed, exact-ID history confirmed by the site owner; never date-based approval."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

METHOD = 'site_owner_verified_history'
IDENTITY = ('id', 'source_url', 'source_type', 'announced_at', 'reset_type')


def digest(records):
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def create_baseline(feed, initialized_at):
    records = copy.deepcopy(feed['records'])
    return {'schema_version': 1, 'method': METHOD, 'initialized_at': initialized_at,
            'reason': 'The operator explicitly verified the records in this historical baseline.',
            'records': records, 'records_sha256': digest(records)}


def load_baseline(path):
    if not Path(path).exists():
        return None
    # Corruption must fail the collection, retaining the last published feed.
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    records = value.get('records', [])
    assert value.get('schema_version') == 1 and value.get('method') == METHOD
    assert records and len({r['id'] for r in records}) == len(records)
    assert value.get('records_sha256') == digest(records)
    assert dt.datetime.fromisoformat(value['initialized_at']).tzinfo
    return value


def retain_history(feed, existing, baseline):
    """Fallback is a source of updates, not permission to erase local history."""
    merged = {}
    for rows in ((baseline or {}).get('records', []), existing.get('records', []), feed['records']):
        for row in rows:
            merged[row['id']] = dict(merged.get(row['id'], {}), **copy.deepcopy(row))
    for original in (baseline or {}).get('records', []):
        # Preserve the verified category and original announcement date.
        merged[original['id']].update({key: original[key] for key in IDENTITY})
    from collector import _feed, parse_date
    rebuilt = _feed(list(merged.values()), parse_date(feed['checked_at']), feed['source'], feed.get('source_generated_at'))
    feed.update({key: rebuilt[key] for key in ('records', 'stats')})
    return feed


def public_confirmation(record):
    """Only a sealed operator snapshot may retain this public actual time."""
    value = record.get('reset_confirmation')
    if not isinstance(value, dict) or value.get('method') != 'historical_public_snapshot' or value.get('kind') != 'official':
        return None
    for key in ('reset_at', 'verified_at'):
        if not isinstance(value.get(key), str):
            raise ValueError('Invalid public snapshot confirmation')
        if dt.datetime.fromisoformat(value[key].replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('Public snapshot confirmation needs a timezone')
    return {key: value[key] for key in ('method', 'kind', 'reset_at', 'verified_at')}


def apply_baseline(feed, baseline):
    approved = {r['id']: r for r in (baseline or {}).get('records', [])}
    for record in feed['records']:
        # Only the separate local ledger grants historical approval.
        record.pop('historical_verification', None)
        original = approved.get(record['id'])
        if original is None:
            continue
        assert all(record[k] == original[k] for k in IDENTITY), 'Historical identity changed'
        record['status'] = 'announced'  # Existing website and mini-program contract.
        record.pop('reset_confirmation', None)
        confirmed = public_confirmation(original)
        if confirmed:
            record['reset_confirmation'] = confirmed
        record.pop('confirmation', None)
        record['historical_verification'] = {
            'method': METHOD, 'initialized_at': baseline['initialized_at'],
            'baseline_sha256': baseline['records_sha256'], 'status': 'delivered'}
        # source_status/source_assessment keep the automatic reading separately.
        record['assessment'] = {'method': METHOD, 'version': '1', 'rule': 'owner_confirmed_historical_delivery',
                                'quote': '', 'source_sha256': record.get('source_assessment', {}).get('source_sha256', '')}
    if baseline:
        feed['historical_baseline'] = {key: baseline[key] for key in ('method', 'initialized_at', 'records_sha256')}
        feed['historical_baseline']['record_count'] = len(approved)
    return feed
