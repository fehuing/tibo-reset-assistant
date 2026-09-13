/* oxlint-disable next/no-img-element -- Static exports serve this local avatar without an image optimizer. */
import { ArrowUpRight } from 'lucide-react';
import { formatElapsed, formatStamp, localizedExcerpt, type Locale } from '@/lib/i18n';
import { postText, type AnnouncementRecord } from '@/lib/post-content';

export function AnnouncementCard({ record, locale, now, onOpen }: {
  record: AnnouncementRecord; locale: Locale; now: number; onOpen: (id: string) => void;
}) {
  const body = postText(record);
  const historical = localizedExcerpt(locale, record.id, body.original);
  const translated = locale === 'zh' && !!(body.translation || historical.translated);
  const preview = (locale === 'zh' && body.translation ? body.translation : historical.value).replace(/\s+/g, ' ').trim();
  const age = formatElapsed(record.announced_at, now, locale);
  return <article className="announcement-row" id={'post-' + record.id}>
    <img className="announcement-avatar" src="/radar/tibo-avatar.jpg" alt="Tibo" width="46" height="46" loading="lazy" />
    <div className="announcement-bubble paper-card">
      <div className="announcement-heading">
        <span className="announcement-age">{age.value}{locale === 'en' ? ' ' : ''}{age.unit}</span>
        <time dateTime={record.announced_at}>{formatStamp(record.announced_at, locale)} · {locale === 'zh' ? '北京时间' : 'GMT+8'}</time>
      </div>
      <p className="announcement-preview" lang={translated ? 'zh-CN' : 'en'}>{preview}</p>
      {locale === 'zh' && !translated && <small className="announcement-language">英文原文 · 中文翻译待更新</small>}
      <div className="announcement-links">
        <a href={record.source_url} target="_blank" rel="noopener noreferrer">{locale === 'zh' ? '查看 X 原帖' : 'View on X'} <ArrowUpRight size={13} /></a>
        <button type="button" onClick={() => onOpen(record.id)}>{locale === 'zh' ? '全文与截图' : 'Full text & capture'}</button>
      </div>
    </div>
  </article>;
}
