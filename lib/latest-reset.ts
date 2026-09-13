import type { ResetRecord } from './post-content';

export function confirmedResetAt(record: ResetRecord, now = Infinity) {
  const confirmation = record.reset_confirmation;
  if (!confirmation || confirmation.kind !== 'official') return null;
  const privateReport = confirmation.method === 'private_reset_report';
  const historicalSnapshot = confirmation.method === 'historical_public_snapshot'
    && record.historical_verification?.method === 'site_owner_verified_history'
    && Number.isFinite(Date.parse(confirmation.verified_at));
  if (!privateReport && !historicalSnapshot) return null;
  const time = Date.parse(confirmation.reset_at);
  return Number.isFinite(time) && time <= now ? confirmation.reset_at : null;
}

export function latestReset(records: ResetRecord[], now: number) {
  return records.filter(record => record.status === 'announced' && record.reset_type === 'regular')
    .map(record => {
      const at = confirmedResetAt(record, now);
      return { record, at };
    })
    .sort((a, b) => Date.parse(b.at || b.record.announced_at) - Date.parse(a.at || a.record.announced_at))[0] || null;
}
