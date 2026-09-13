'use client';

import { useState } from 'react';
import { ArrowUpRight, ChevronDown, FileText, Maximize2, X } from 'lucide-react';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { formatStamp, text, type Locale } from '@/lib/i18n';
import { postScreenshot, postText, type AnnouncementRecord } from '@/lib/post-content';
import { announcementCopy } from '@/lib/announcements';
import { translationMessage } from '@/lib/translation';

export function PostContent({ record, locale, showSummary = true }: { record: AnnouncementRecord; locale: Locale; showSummary?: boolean }) {
  const [failedImage, setFailedImage] = useState('');
  const [failedThumbnail, setFailedThumbnail] = useState('');
  const body = postText(record);
  const shot = postScreenshot(record);
  const showImage = shot && failedImage !== shot.url;
  const listImage = shot?.thumbnail && failedThumbnail !== shot.thumbnail.url ? shot.thumbnail : shot;
  const t = (key: Parameters<typeof text>[1]) => text(locale, key);
  const captured = shot ? text(locale, 'postCaptured', { time: formatStamp(shot.captured_at, locale) }) : '';
  const brief = locale === 'zh' ? (body.translation ? record.brief?.zh : undefined) : record.brief?.en;
  const translationNotice = translationMessage(record, locale);
  const c = announcementCopy[locale];

  return <div className="post-content">
    {showSummary && locale === 'zh' && !body.translation && <div className="post-brief" role="status"><strong>{announcementCopy[locale].summary}</strong><p>{translationNotice}</p></div>}
    {showSummary && brief?.summary && <div className="post-brief"><strong>{c.summary}</strong><p lang={locale === 'zh' && body.translation ? 'zh-CN' : 'en'}>{brief.summary}</p>
      <details><summary>{c.scope} · {c.action}</summary><dl><dt>{c.scope}</dt><dd>{brief.scope || c.checkSource}</dd><dt>{c.action}</dt><dd>{brief.action || c.checkSource}</dd></dl></details>
      {locale === 'zh' && record.translation_zh?.method?.endsWith('machine_translation') && <small>{c.machine}</small>}
    </div>}
    {showImage ? <>
      <Dialog>
        <DialogTrigger className="post-capture-button" aria-label={t('postEnlarge')}>
          <span className="post-capture-viewport"><img className="post-capture-image" src={listImage!.url} width={listImage!.width} height={listImage!.height} alt={t('postScreenshotAlt')} loading="lazy" decoding="async" onError={() => listImage!.url !== shot.url ? setFailedThumbnail(listImage!.url) : setFailedImage(shot.url)} /></span>
          <span className="post-capture-action"><Maximize2 size={15} />{t('postEnlarge')}</span>
        </DialogTrigger>
        <DialogContent className="post-image-dialog" showCloseButton={false}>
          <DialogHeader className="post-image-header">
            <div><DialogTitle>{t('postScreenshot')}</DialogTitle><DialogDescription>{captured}</DialogDescription></div>
            <DialogClose className="post-image-close" aria-label={t('postClose')}><X size={20} /></DialogClose>
          </DialogHeader>
          <div className="post-image-scroll" tabIndex={0} aria-label={t('postEnlarge')}><img src={shot.url} width={shot.width} height={shot.height} alt={t('postScreenshotAlt')} /></div>
          <div className="post-image-footer"><a href={shot.url} target="_blank" rel="noopener noreferrer">{t('postOpenImage')} <ArrowUpRight size={15} /></a><a href={record.source_url} target="_blank" rel="noopener noreferrer">{t('fullOriginal')} <ArrowUpRight size={15} /></a></div>
        </DialogContent>
      </Dialog>
      <p className="post-capture-caption">{captured}</p>
    </> : <>
      <blockquote className="post-text-preview" lang={locale === 'zh' && body.translation ? 'zh-CN' : 'en'}>{locale === 'zh' && body.translation ? body.translation : body.original}</blockquote>
      <p className="post-text-state">{failedImage ? t('postImageUnavailable') : body.complete ? t('postFullOriginal') : t('postCapturedText')}</p>
    </>}
    <details className="post-text-details" open={!showSummary}>
      <summary><FileText size={17} /><span>{t('postTextAndTranslation')}</span><ChevronDown size={17} className="post-details-chevron" /></summary>
      <div className="post-full-text">
        {locale === 'zh' && (body.translation ? <section><h4>{t('postFullTranslation')}</h4><p lang="zh-CN">{body.translation}</p></section> : <p className="post-translation-pending">{translationNotice}</p>)}
        <section><h4>{body.complete ? t('postFullOriginal') : t('postCapturedText')}</h4><p lang="en">{body.original}</p></section>
        <p className="post-archive-note">{t('postArchiveNote')}</p>
      </div>
    </details>
  </div>;
}
