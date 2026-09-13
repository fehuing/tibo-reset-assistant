import type { ResetRecord } from './post-content';
import type { Locale } from './i18n';
import { projectCalendar } from '@/lib/calendar-history';
import { confirmedResetAt } from './latest-reset';

export type ResetEvent = { id: string; status: 'planned' | 'announced' | 'uncertain'; reset_type: string; announced_at: string; record_id: string; record_ids: string[]; source_url: string; reset_at?: string };
export type EventStats = { total: number; announcement_total: number; regular: number; banked: number; planned: number; uncertain: number; avg_interval_days: number | null; longest_interval_days: number | null };

export function calendarRecords(records: ResetRecord[], events?: ResetEvent[]) {
  return projectCalendar(records, events);
}

export const announcementCopy = {
  zh: {
    planned: '预告已发布 · 发放待核实', announced: '作者宣布已发放', uncertain: '待确认',
    plannedNote: '这是原帖的预告；系统正在查找关联的后续确认。经过预告时间不代表尚未发放，也不自动证明已到账。',
    confirmedNote: '已核验作者关联的后续确认，原预告保留在下方；不代表每个账户都已到账。', confirmation: '后续确认依据', confirmationSource: '查看确认原帖',
    announcedNote: '原文明确宣布发放，不代表你的个人账户已到账。',
    uncertainNote: '现有原文不足以确认发放，暂不计入已宣布事件。',
    delivered: '已发放', historyNote: '这条历史记录已由站长核实并确认为已发放，原帖与公告时间保留。',
    evidence: '查看判定依据', aiEvidence: 'AI 原文分析依据', events: '已发放记录', posts: '公告条数',
    statsNote: '统计已核实的历史记录和后续确认发放的事件；间隔按公告发布时间计算。',
    calendarNote: '历史日历已与参考站核对；新记录按已确认的重置事件补充。日期以北京时间显示，点击查看原始记录。',
    calendarAll: '全部公告', calendarAnnounced: '只看已发放', calendarPending: '仅预告 / 待确认', calendarCount: '条公告', calendarScope: '日历显示范围',
    related: '同一事件的相关公告', summary: '内容摘要', scope: '适用范围', action: '操作说明',
    checkSource: '以原文说明为准', machine: '机器翻译，请结合英文原文阅读',
    eventCount: '个事件', shareRecord: '分享这条', openRecord: '查看这条公告',
    missing: '这条公告暂未在当前记录中找到，请稍后刷新。',
  },
  en: {
    planned: 'Preview posted · Delivery unverified', announced: 'Author reports delivery', uncertain: 'Unconfirmed',
    confirmedNote: 'An explicitly linked author follow-up confirms delivery. The original preview is preserved below; individual balances are not verified.', confirmation: 'Follow-up confirmation', confirmationSource: 'View confirmation on X',
    plannedNote: 'Awaiting an explicit update. Passing the announced time does not confirm delivery.',
    announcedNote: 'The author reports delivery. This does not verify your account balance.',
    uncertainNote: 'The source is insufficient to confirm delivery; excluded from announced events.',
    delivered: 'Delivered', historyNote: 'This historical record was verified as delivered by the site owner. The original post and announcement date are preserved.',
    evidence: 'Why this status?', aiEvidence: 'Source evidence assessed by AI', events: 'Delivered resets', posts: 'Posts',
    statsNote: 'Verified historical records and subsequently confirmed deliveries. Intervals use announcement dates.',
    calendarNote: 'Historical calendar entries were aligned with the reference site. New confirmed reset events are added in Beijing time; select an entry to read its source.',
    calendarAll: 'All posts', calendarAnnounced: 'Delivered only', calendarPending: 'Planned / unconfirmed only', calendarCount: 'posts', calendarScope: 'Calendar view',
    related: 'Related posts for this event', summary: 'At a glance', scope: 'Applies to', action: 'What to do',
    checkSource: 'Check the original announcement', machine: 'Machine translation; check the English source',
    eventCount: 'events', shareRecord: 'Share this post', openRecord: 'View this post',
    missing: 'This post is not in the current feed. Please refresh later.',
  },
};

export function recordState(record: ResetRecord) {
  return record.status === 'planned' || record.status === 'announced' ? record.status : 'uncertain';
}
export function statusView(record: ResetRecord, locale: Locale) {
  const status = recordState(record);
  const c = announcementCopy[locale];
  const confirmedAt = confirmedResetAt(record);
  if (status === 'announced' && confirmedAt) {
    const at = new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-GB', {timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'medium'}).format(new Date(confirmedAt));
    if (record.reset_confirmation?.method === 'historical_public_snapshot') return { status, label: c.delivered, note: locale === 'zh'
      ? `已核实的历史重置时间：${at} · 北京时间。原帖和公告时间保留。`
      : `Verified historical reset time: ${at} · UTC+8. Original post and announcement time preserved.` };
    return { status, label: c.delivered, note: locale === 'zh'
      ? `已根据站长上报的额度重置信号确认发放。重置时间：${at} · 北京时间。原帖和公告时间保留。`
      : `Delivery confirmed from the owner's quota reset report. Reset time: ${at} · UTC+8. Original post and announcement time preserved.` };
  }
  if (status === 'announced' && record.historical_verification?.method === 'site_owner_verified_history') {
    return { status, label: c.delivered, note: c.historyNote };
  }
  return { status, label: c[status], note: status === 'announced' && record.confirmation ? c.confirmedNote : c[`${status}Note`] };
}
