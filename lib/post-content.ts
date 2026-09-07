export type ResetRecord = {
  id: string;
  reset_type: string;
  announced_at: string;
  excerpt: string;
  source_url: string;
  source_type: string;
  status?: 'planned' | 'announced' | 'uncertain';
  assessment?: { rule: string; quote: string; source_sha256: string; method: string };
  event_id?: string;
  related_record_ids?: string[];
  source_text?: string;
  full_text?: string;
  text_complete?: boolean;
  full_text_sha256?: string;
  translation_zh?: { text: string; source_sha256: string; method?: string };
  brief?: { method: string; en: { summary: string; scope: string; action: string }; zh?: { summary: string; scope: string; action: string }; translation_method?: string };
  screenshot?: { file: string; sha256: string; width: number; height: number; captured_at: string; source_url: string;
    thumbnail?: { file: string; sha256: string; width: number; height: number; source_sha256: string; source_url: string } };
};

export function postText(record: ResetRecord) {
  const complete = record.text_complete === true && typeof record.full_text === 'string' && record.full_text.length > 0 && record.full_text.length <= 60000;
  const original = complete ? record.full_text! : typeof record.source_text === 'string' && record.source_text ? record.source_text : record.excerpt;
  const translation = record.translation_zh;
  const translated = complete && /^[a-f0-9]{64}$/.test(record.full_text_sha256 ?? '') && !!translation &&
    translation.source_sha256 === record.full_text_sha256 && typeof translation.text === 'string' && translation.text.trim();
  return { original, complete, translation: translated ? translation!.text : '' };
}

export function postScreenshot(record: ResetRecord) {
  const shot = record.screenshot;
  const id = /^https:\/\/x\.com\/thsottiaux\/status\/(\d+)$/.exec(record.source_url)?.[1];
  if (!shot || !id || typeof shot.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(shot.sha256) ||
      shot.file !== `${id}-${shot.sha256.slice(0, 16)}.jpg` || shot.source_url !== record.source_url ||
      typeof shot.captured_at !== 'string' || !Number.isFinite(Date.parse(shot.captured_at)) || !Number.isInteger(shot.width) || !Number.isInteger(shot.height) ||
      shot.width < 1 || shot.height < 1 || shot.width > 24000 || shot.height > 24000) return null;
  // Both the canonical domain and the existing /radar/ address use this archive.
  const thumb = shot.thumbnail;
  const validThumb = thumb && /^[a-f0-9]{64}$/.test(thumb.sha256) && thumb.file === `${id}-${thumb.sha256.slice(0, 16)}.jpg` && thumb.source_sha256 === shot.sha256 && thumb.source_url === record.source_url && Number.isInteger(thumb.width) && thumb.width > 0 && thumb.width <= 440 && Number.isInteger(thumb.height) && thumb.height > 0 && thumb.height <= 24000;
  return { ...shot, url: '/radar/post-images/' + shot.file,
    thumbnail: validThumb ? { ...thumb, url: '/radar/post-images/' + thumb.file } : null };
}
