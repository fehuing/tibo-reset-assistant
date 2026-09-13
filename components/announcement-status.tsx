import { statusView, announcementCopy } from '@/lib/announcements';
import type { ResetRecord } from '@/lib/post-content';
import type { Locale } from '@/lib/i18n';

export function AnnouncementStatus({ record, locale, detail = false }: { record: ResetRecord; locale: Locale; detail?: boolean }) {
  const view = statusView(record, locale);
  const aiAssessed = record.ai_analysis?.method === 'codex_cli' || record.assessment?.method === 'codex_cli';
  return <div className="announcement-status">
    <span className={'announcement-state ' + view.status}>{view.label}</span>
    {detail && <><p className="announcement-state-note">{view.note}</p>
      {!record.historical_verification && !record.reset_confirmation && record.assessment?.quote && <details className="assessment-detail"><summary>{aiAssessed ? announcementCopy[locale].aiEvidence : record.confirmation ? announcementCopy[locale].confirmation : announcementCopy[locale].evidence}</summary><blockquote lang="en">{record.assessment.quote}</blockquote>
        {record.confirmation && /^https:\/\/x\.com\/thsottiaux\/status\/\d+$/.test(record.confirmation.source_url) && <p><a href={record.confirmation.source_url} target="_blank" rel="noopener noreferrer">{announcementCopy[locale].confirmationSource} ↗</a><br /><time dateTime={record.confirmation.published_at}>{new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-GB', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short' }).format(new Date(record.confirmation.published_at))} · UTC+8</time></p>}
      </details>}
    </>}
  </div>;
}
