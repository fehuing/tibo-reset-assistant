import type { ResetRecord } from './post-content';
import type { Locale } from './i18n';

export type ResetEvent = { id: string; status: 'planned' | 'announced' | 'uncertain'; reset_type: string; announced_at: string; record_id: string; record_ids: string[]; source_url: string };
export type EventStats = { total: number; announcement_total: number; regular: number; banked: number; planned: number; uncertain: number; avg_interval_days: number | null; longest_interval_days: number | null };

export function calendarRecords(records: ResetRecord[], events: ResetEvent[] = []) {
  return events.filter(e => e.status === 'announced').flatMap(e => {
    const record = records.find(r => r.id === e.record_id);
    return record ? [{ ...record, announced_at: e.announced_at }] : [];
  });
}

export const announcementCopy = {
  zh: {
    planned: '预告中', announced: '作者宣布已发放', uncertain: '待确认',
    plannedNote: '仍以预告记录，等待后续明确消息；时间到了也不会自动标记已发放。',
    announcedNote: '原文明确宣布发放，不代表你的个人账户已到账。',
    uncertainNote: '现有原文不足以确认发放，暂不计入已宣布事件。',
    evidence: '查看判定依据', events: '已宣布事件', posts: '公告条数',
    statsNote: '仅按原文明确宣布发放的事件统计；预告和待确认不计入，不代表全部实际发放次数。间隔按这些公告的发布时间计算。',
    calendarNote: '仅展示已明确宣布的事件；点击查看相关公告。',
    related: '同一事件的相关公告', summary: '内容摘要', scope: '适用范围', action: '操作说明',
    checkSource: '以原文说明为准', machine: '机器翻译，请结合英文原文阅读',
    eventCount: '个事件', shareRecord: '分享这条', openRecord: '查看这条公告',
    missing: '这条公告暂未在当前记录中找到，请稍后刷新。',
  },
  en: {
    planned: 'Planned', announced: 'Author reports delivery', uncertain: 'Unconfirmed',
    plannedNote: 'Awaiting an explicit update. Passing the announced time does not confirm delivery.',
    announcedNote: 'The author reports delivery. This does not verify your account balance.',
    uncertainNote: 'The source is insufficient to confirm delivery; excluded from announced events.',
    evidence: 'Why this status?', events: 'Announced events', posts: 'Posts',
    statsNote: 'A sample of explicit delivery statements, not a count of all actual resets. Plans and unconfirmed posts are excluded. Intervals use announcement dates.',
    calendarNote: 'Explicitly announced events only. Select to read related posts.',
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
  return { status, label: c[status], note: c[`${status}Note`] };
}
