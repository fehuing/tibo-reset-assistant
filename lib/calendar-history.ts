import history from './calendar-history.json';
import type { ResetRecord } from './post-content';
import type { ResetEvent } from './announcements';
import { confirmedResetAt } from './latest-reset';

// This calendar-only seed preserves the reference site's verified historical set.
// It does not replace source announcements, actual reset times or server statistics.
const DAY = 86400000;
const BEIJING = 8 * 3600000;
const cutoff = Date.parse(history.captured_at);

export function calendarDateKey(time: number) {
  return new Date(time + BEIJING).toISOString().slice(0, 10);
}

export function calendarWindow(now: number) {
  const end = Date.parse(calendarDateKey(now) + 'T00:00:00+08:00');
  const start = end - (26 * 7 - 1) * DAY;
  const first = start - new Date(start + BEIJING).getUTCDay() * DAY;
  return { first, end, columns: Math.ceil((end - first + DAY) / (7 * DAY)) };
}

export function projectCalendar(records: ResetRecord[], events?: ResetEvent[]): ResetRecord[] {
  const byId = new Map(records.map(record => [record.id, record]));
  const rows = new Map<string, ResetRecord>(history.records.map(record => [
    record.id, { ...byId.get(record.id), ...record, status: 'announced' },
  ]));
  // After the frozen historical cutoff, only confirmed events extend the calendar.
  const confirmed: Pick<ResetEvent, 'record_id' | 'announced_at' | 'reset_at'>[] = Array.isArray(events)
    ? events.filter(event => event.status === 'announced')
    : records.filter(record => record.status === 'announced').map(record => ({ record_id: record.id, announced_at: record.announced_at }));
  for (const event of confirmed) {
    const record = byId.get(event.record_id);
    const actual = record ? confirmedResetAt(record) : null;
    const at = actual || event.reset_at || record?.confirmation?.published_at || event.announced_at;
    if (record && Date.parse(at) > cutoff && !rows.has(record.id)) {
      rows.set(record.id, { ...record, announced_at: at, status: 'announced' });
    }
  }
  return [...rows.values()].sort((a, b) => Date.parse(b.announced_at) - Date.parse(a.announced_at));
}
