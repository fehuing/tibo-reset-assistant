import { statusView, announcementCopy } from '@/lib/announcements';
import type { ResetRecord } from '@/lib/post-content';
import type { Locale } from '@/lib/i18n';

export function AnnouncementStatus({ record, locale, detail = false }: { record: ResetRecord; locale: Locale; detail?: boolean }) {
  const view = statusView(record, locale);
  return <div className="announcement-status">
    <span className={'announcement-state ' + view.status}>{view.label}</span>
    {detail && <><p className="announcement-state-note">{view.note}</p>
      {record.assessment?.quote && <details className="assessment-detail"><summary>{announcementCopy[locale].evidence}</summary><blockquote lang="en">{record.assessment.quote}</blockquote></details>}
    </>}
  </div>;
}
