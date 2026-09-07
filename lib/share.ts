export const validPostId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
export function recordLink(id: string, locale: string) {
  if (!validPostId(id)) throw new Error('Invalid record ID');
  const url = new URL(typeof window === 'undefined' ? 'http://localhost:8080/' : window.location.origin + window.location.pathname);
  url.searchParams.set('lang', locale === 'en' ? 'en' : 'zh');
  url.searchParams.set('post', id);
  return url.href;
}
