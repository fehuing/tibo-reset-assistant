"""Optional local confirmation compatibility; no HTTP reporting interface.

No ledger or credentials are distributed. Existing operators may retain their
own private ledger; new deployments use the public historical seed only.
"""
from contextlib import contextmanager, closing
import json
from pathlib import Path
import sqlite3
from file_lock import file_lock

@contextmanager
def publication_lock(state):
    with file_lock(Path(state) / 'publication.lock'):
        yield


def identity(record):
    return {k: record.get(k) for k in ('id', 'source_url', 'announced_at', 'reset_type', 'source_type')}


def apply_private_reports(feed, state):
    """Only the private ledger is authoritative; upstream fields grant no approval."""
    for record in feed['records']:
        public_snapshot = (record.get('historical_verification', {}).get('method') == 'site_owner_verified_history'
                           and record.get('reset_confirmation', {}).get('method') == 'historical_public_snapshot')
        if not public_snapshot:
            record.pop('reset_confirmation', None)
    path = Path(state) / 'private-reports/reports.sqlite3'
    if not path.exists():
        return feed
    with closing(sqlite3.connect(str(path), timeout=10)) as db:
        rows = db.execute("SELECT target_id, identity_json, public_json FROM reports WHERE kind='official'").fetchall()
    records = {r['id']: r for r in feed['records']}
    for ident, original, public in rows:
        record = records.get(ident)
        if not record or record.get('historical_verification') or identity(record) != json.loads(original):
            continue
        record['status'] = 'announced'
        record['reset_confirmation'] = json.loads(public)
    return feed
