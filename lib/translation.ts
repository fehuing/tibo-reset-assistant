import type { AnnouncementRecord } from './post-content';
import { postText } from './post-content';
import type { Locale } from './i18n';

const copy = {
  zh: { pending: '中文翻译排队中，完成后自动更新摘要。', translating: '正在翻译，完成后自动更新中文摘要。',
    retrying: '中文翻译暂时失败，系统会自动重试。', unavailable: '中文翻译服务暂不可用，原文和截图仍可查看。',
    awaiting_text: '正在采集完整正文，随后生成中文翻译和摘要。' },
  en: { pending: 'Chinese translation queued; the summary will update automatically.', translating: 'Translating; the Chinese summary will update automatically.',
    retrying: 'Chinese translation failed temporarily. An automatic retry is scheduled.', unavailable: 'Chinese translation is unavailable. The original text and screenshot remain available.',
    awaiting_text: 'Collecting the full post before translating and generating the Chinese summary.' },
};
export function translationMessage(record: AnnouncementRecord, locale: Locale) {
  if (postText(record).translation) return '';
  const current = record.translation_status;
  const state = !record.text_complete ? 'awaiting_text' : current?.source_sha256 === record.full_text_sha256 ? current?.state : 'pending';
  return copy[locale][state as keyof typeof copy.zh] || copy[locale].pending;
}
