'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowDown, ArrowRight, ArrowUpRight, Check, Clock3, Copy, History, Moon, Radio, RefreshCw, Sun, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ResetCalendar } from '@/components/reset-calendar';
import { ReactionButton } from '@/components/reaction-button';
import { ResetWatch } from '@/components/reset-watch';
import { PostContent } from '@/components/post-content';
import { AnnouncementStatus } from '@/components/announcement-status';
import { announcementCopy, calendarRecords, type ResetEvent, type EventStats } from '@/lib/announcements';
import { formatElapsed, formatStamp, resetLabel, text as i18nText, type Locale } from '@/lib/i18n';
import type { ResetRecord } from '@/lib/post-content';
import { siteConfig } from '@/lib/site-config';
import { runtimeBase } from '@/lib/runtime-base';
import { recordLink, validPostId } from '@/lib/share';

type FeedSource = {
  active: 'x_direct' | 'codex_resets_fallback';
  primary: string;
  fallback: string;
  fallback_used: boolean;
  recent_posts_seen?: number;
  reset_posts_matched?: number;
};
type Feed = {
  mode?: 'snapshot' | 'live';
  schema_version: number;
  checked_at: string;
  source_generated_at: string | null;
  history_complete: boolean;
  source: FeedSource;
  records: ResetRecord[];
  events?: ResetEvent[];
  event_stats?: EventStats;
  stats: { total: number; avg_interval_days: number | null; longest_interval_days: number | null };
};
function isFeed(value: unknown): value is Feed {
  if (!value || typeof value !== 'object') return false;
  const f = value as Feed;
  if (f.events !== undefined && (!Array.isArray(f.events) || !Array.isArray(f.records) || !f.events.every(e => e && ['planned', 'announced', 'uncertain'].includes(e.status) && Array.isArray(e.record_ids) && e.record_ids.every(id => f.records.some(r => r.id === id)) && f.records.some(r => r.id === e.record_id && r.announced_at === e.announced_at)))) return false;
  if (f.event_stats && (!Number.isSafeInteger(f.event_stats.total) || f.event_stats.total !== f.events?.filter(e => e.status === 'announced').length || !['avg_interval_days', 'longest_interval_days'].every(key => { const v = f.event_stats![key as 'avg_interval_days' | 'longest_interval_days']; return v === null || Number.isFinite(v) && v >= 0; }))) return false;
  return f.schema_version === 1 && Number.isFinite(Date.parse(f.checked_at)) && Array.isArray(f.records) && !!f.stats &&
    !!f.source && (f.source.active === 'x_direct' || f.source.active === 'codex_resets_fallback') &&
    f.records.every(r => typeof r.id === 'string' && Number.isFinite(Date.parse(r.announced_at)) && typeof r.excerpt === 'string' &&
      /^https:\/\/x\.com\/thsottiaux\/status\/[0-9]+$/.test(r.source_url));
}

export default function Home() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [dark, setDark] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [filter, setFilter] = useState('all');
  const [limit, setLimit] = useState(6);
  const [locale, setLocale] = useState<Locale>('zh');
  const [selectedPost, setSelectedPost] = useState('');
  const [sharedPost, setSharedPost] = useState('');
  const t = useCallback((key: Parameters<typeof i18nText>[1], values?: Record<string, string | number>) => i18nText(locale, key, values), [locale]);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const response = await fetch(runtimeBase() + '/data.json', { cache: 'no-store', signal });
      if (!response.ok) throw new Error('feed unavailable');
      const result = await response.json();
      if (!isFeed(result)) throw new Error('invalid feed');
      setFeed(result);
      setFailure(false);
      setNow(Date.now());
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      setFailure(true);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const poll = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh(controller.signal);
    }, 60000);
    const tick = window.setInterval(() => setNow(Date.now()), 30000);
    const onVisible = () => { if (document.visibilityState === 'visible') void refresh(controller.signal); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { controller.abort(); clearInterval(poll); clearInterval(tick); document.removeEventListener('visibilitychange', onVisible); };
  }, [refresh]);

  useEffect(() => {
    const readLink = () => { const id = new URLSearchParams(window.location.search).get('post'); setSelectedPost(validPostId(id) ? id : ''); };
    readLink();
    window.addEventListener('popstate', readLink);
    return () => window.removeEventListener('popstate', readLink);
  }, []);
  useEffect(() => {
    try {
      setDark(localStorage.getItem('radar-theme') === 'dark');
      const requested = new URLSearchParams(window.location.search).get('lang');
      const saved = localStorage.getItem('radar-locale');
      setLocale(requested === 'en' || requested === 'zh' ? requested : saved === 'en' ? 'en' : 'zh');
    } catch { /* Preferences are optional. */ }
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
    document.documentElement.dataset.locale = locale;
    document.title = i18nText(locale, 'documentTitle');
    document.querySelector('meta[name="description"]')?.setAttribute('content', i18nText(locale, 'documentDescription'));
  }, [locale]);

  const latest = feed?.records[0];
  const c = announcementCopy[locale];
  const eventStats = feed?.event_stats;
  const selectedRecord = feed?.records.find(record => record.id === selectedPost);
  const age = latest ? formatElapsed(latest.announced_at, now, locale) : null;
  const stale = !!feed && now - Date.parse(feed.checked_at) > 8 * 60000;
  const filtered = (feed?.records ?? []).filter(r => filter === 'all' || r.reset_type === filter);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    try { localStorage.setItem('radar-theme', next ? 'dark' : 'light'); } catch { /* No storage required to use the site. */ }
  }
  function toggleLanguage() {
    const next: Locale = locale === 'zh' ? 'en' : 'zh';
    setLocale(next);
    try {
      localStorage.setItem('radar-locale', next);
      const url = new URL(window.location.href);
      url.searchParams.set('lang', next);
      window.history.replaceState(null, '', url);
    } catch { /* The language still switches without storage or history access. */ }
  }
  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.origin + runtimeBase() + '/?lang=' + locale);
      setCopied(true); setCopyError(false);
      window.setTimeout(() => setCopied(false), 2400);
    } catch { setCopyError(true); }
  }
  function openPost(id: string) {
    setSelectedPost(id);
    const url = new URL(window.location.href); url.searchParams.set('post', id);
    window.history.pushState(null, '', url);
  }
  function closePost() {
    setSelectedPost('');
    const url = new URL(window.location.href); url.searchParams.delete('post');
    window.history.replaceState(null, '', url);
  }
  async function sharePost(record: ResetRecord) {
    try {
      const url = recordLink(record.id, locale);
      if (navigator.share) await navigator.share({ title: t('brand'), text: formatStamp(record.announced_at, locale), url });
      else await navigator.clipboard.writeText(url);
      setSharedPost(record.id); window.setTimeout(() => setSharedPost(''), 2400);
    } catch (error) { if (!(error instanceof Error && error.name === 'AbortError')) setCopyError(true); }
  }

  return (
    <div className="site-shell">
      <a className="skip-link" href="#latest">{t('skip')}</a>
      <header className="site-header">
        <a href="./" className="brand" aria-label={t('home')}>
          <span className="brand-mark"><img className="brand-avatar" src="/radar/tibo-avatar.jpg" alt="" width="64" height="64" /></span>
          <span className="brand-name">{t('brand')}<span className="brand-en">{t('brandTag')}</span></span>
        </a>
        <nav className="header-actions" aria-label={t('navigation')}>
          <a href="#history" className="text-link nav-history">{t('historyNav')} <ArrowUpRight size={16} /></a>
          {siteConfig.miniProgramCode && <a href="#miniprogram" className="text-link nav-history">{t('miniProgramNav')} <ArrowUpRight size={16} /></a>}
          <Button className="language-button" onClick={toggleLanguage} aria-label={t('switchLanguage')} lang={locale === 'zh' ? 'en' : 'zh-CN'}>
            {t('languageButton')}
          </Button>
          <Button className="icon-button" onClick={toggleTheme} aria-label={dark ? t('lightMode') : t('darkMode')}>
            {dark ? <Sun size={20} /> : <Moon size={20} />}
          </Button>
        </nav>
      </header>

      <main>
        {feed?.mode === 'snapshot' && <p className="error-note" role="status">{locale === 'zh' ? '本地历史快照 · 未启用实时采集；互动计数仅保存在此实例。' : 'Local historical snapshot · Live collection is off. Counts belong to this instance.'}</p>}
        <ResetWatch locale={locale} now={now} />
        <section className="intro">
          <div className="eyebrow"><span className="tiny-square" /> {t('introKicker')}</div>
          <h1>{t('headline')} <span className="question-mark">{t('headlineQuestion')}</span></h1>
          <p>{t('introBefore')}<a href="https://x.com/thsottiaux" target="_blank" rel="noopener noreferrer">@thsottiaux <ArrowUpRight size={15} /></a>{t('introAfter')}</p>
        </section>

        <section id="latest" className="latest-card paper-card">
          <div className="latest-topline">
            <span className="eyebrow">{t('latest')} {locale === 'zh' && <span className="muted-english">/ LATEST RESET</span>}</span>
            <span className={'status-badge ' + (failure || stale ? 'status-warning' : '')}>
              <span className="status-dot" />{feed?.mode === 'snapshot' ? (locale === 'zh' ? '历史快照' : 'Snapshot') : !feed ? failure ? t('disconnected') : t('reading') : failure || stale ? t('delayed') : t('tracking')}
            </span>
          </div>
          {age && latest ? (
            <>
              <div className="latest-center">
                <div>
                  <div className="big-time"><span className="highlight-number">{age.value}</span><span className="time-unit">{age.unit}</span></div>
                  <p className="time-detail">{age.detail}</p>
                </div>
                <div className="reset-sticker" aria-hidden="true"><Zap size={32} fill="currentColor" /><span>{t('good')}<br />{t('news')}</span></div>
              </div>
              <AnnouncementStatus record={latest} locale={locale} detail />
              <div className="latest-divider" />
              <div className="latest-bottom">
                <div className="event-info">
                  <span className={'event-type ' + latest.reset_type}>{resetLabel(locale, latest.reset_type)}</span>
                  <time dateTime={latest.announced_at}>{formatStamp(latest.announced_at, locale)} <span>{t('beijing')}</span></time>
                </div>
                <div className="latest-actions">
                  <ReactionButton locale={locale} now={now} />
                  <a className="press-button yellow" href={latest.source_url} target="_blank" rel="noopener noreferrer">{t('viewOriginal')} <ArrowUpRight size={18} /></a>
                </div>
              </div>
            </>
          ) : (
            <div className="loading-state" role="status">
              <Radio size={38} />
              <h2>{failure ? t('failedTitle') : t('loadingTitle')}</h2>
              <p>{failure ? t('failedText') : t('loadingText')}</p>
            </div>
          )}
        </section>

        <div className="sync-row">
          <div className="sync-info">
            <p><Clock3 size={14} /><span>{feed ? t('checkedAt', { time: formatStamp(feed.checked_at, locale, true) }) : t('waitingFirst')}</span></p>
            {feed && <span className={'source-chip ' + (feed.source.fallback_used ? 'fallback' : 'direct')}><span className="source-pulse" />{feed.source.fallback_used ? t('sourceFallback') : t('sourceDirect')}</span>}
          </div>
          <Button className="refresh-button" variant="ghost" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />{loading ? t('checking') : t('checkUpdates')}
          </Button>
        </div>
        {(failure || stale) && <div className="error-note" role="status">{feed ? t('staleCached') : t('unavailable')}</div>}

        <section className="stats-grid" aria-label={t('statsAria')}>
          <div className="stat-card yellow"><span className="stat-label">{c.events} <Zap size={17} /></span><div className="stat-value">{eventStats?.total ?? '—'}{t('totalUnit') && <span>{t('totalUnit')}</span>}</div><span className="stat-caption">{c.posts} · {feed?.records.length ?? '—'}</span></div>
          <div className="stat-card pink"><span className="stat-label">{t('average')} <Clock3 size={17} /></span><div className="stat-value">{eventStats?.avg_interval_days?.toFixed(1) ?? '—'}<span>{t('daysUnit')}</span></div><span className="stat-caption">{c.events}</span></div>
          <div className="stat-card blue"><span className="stat-label">{t('longest')} <History size={17} /></span><div className="stat-value">{eventStats?.longest_interval_days?.toFixed(1) ?? '—'}<span>{t('daysUnit')}</span></div><span className="stat-caption">{c.events}</span></div>
        </section>
        <p className="event-stats-note">{c.statsNote}</p>
        {eventStats && <p className="event-breakdown">{t('regular')} {eventStats.regular} · {t('banked')} {eventStats.banked} · {c.planned} {eventStats.planned} · {c.uncertain} {eventStats.uncertain}</p>}
        <ResetCalendar records={calendarRecords(feed?.records ?? [], feed?.events)} now={now} ready={!!feed?.events} locale={locale} onSelect={openPost} />
        <p className="event-stats-note">{c.calendarNote}</p>

        <section id="announcements" className="announcements-section">
          {selectedPost && feed && !selectedRecord && <p role="status" className="error-note">{c.missing}</p>}
          <div className="section-heading"><div><span className="eyebrow">{t('logKicker')}</span><h2>{t('logTitle')}<span className="heading-dot">.</span></h2></div><span className="log-count">{feed ? t('announcementCount', { count: feed.records.length }) : '—'}</span></div>
          <Tabs value={filter} onValueChange={value => { setFilter(String(value)); setLimit(6); }} className="announcement-tabs">
            <TabsList className="filter-tabs">
              <TabsTrigger value="all">{t('all')}</TabsTrigger>
              <TabsTrigger value="regular">{t('regular')}</TabsTrigger>
              <TabsTrigger value="banked">{t('banked')}</TabsTrigger>
            </TabsList>
            {['all', 'regular', 'banked'].map(tab => (
              <TabsContent value={tab} key={tab}>
                {filtered.length ? <div className="announcement-list">{filtered.slice(0, limit).map((record, index) => (
                  <article className="announcement paper-card" key={record.id} id={'post-' + record.id}>
                    <div className="announcement-rail"><span className={'event-icon ' + record.reset_type}><img src="/radar/tibo-avatar.jpg" alt="" width="48" height="48" /></span><span className="record-index">{String((feed?.records.length ?? 0) - (feed?.records.findIndex(r => r.id === record.id) ?? index)).padStart(2, '0')}</span></div>
                    <div className="announcement-body">
                      <div className="announcement-meta"><span className={'event-type ' + record.reset_type}>{resetLabel(locale, record.reset_type)}</span><time dateTime={record.announced_at}>{formatStamp(record.announced_at, locale)}</time></div>
                      <AnnouncementStatus record={record} locale={locale} detail />
                      <PostContent record={record} locale={locale} />
                      <div className="record-actions"><Button variant="ghost" onClick={() => openPost(record.id)}>{c.openRecord}</Button><Button variant="ghost" onClick={() => void sharePost(record)}>{sharedPost === record.id ? t('copied') : c.shareRecord} <ArrowUpRight size={16} /></Button></div>
                      {!!record.related_record_ids?.length && <div className="related-posts"><strong>{c.related}</strong>{record.related_record_ids.map(id => { const related = feed?.records.find(r => r.id === id); return related ? <a key={id} href={'?lang=' + locale + '&post=' + encodeURIComponent(id)}>{formatStamp(related.announced_at, locale)} ↗</a> : null; })}</div>}
                      <div className="announcement-bottom"><span>{record.source_type === 'observed' ? t('observed') : t('author')}</span><a className="source-link" href={record.source_url} target="_blank" rel="noopener noreferrer">{record.source_type === 'observed' ? t('relatedOriginal') : t('fullOriginal')} <ArrowUpRight size={16} /></a></div>
                    </div>
                  </article>
                ))}</div> : <div className="empty-records">{feed ? t('emptyFilter') : t('recordsLoading')}</div>}
                {filtered.length > limit && <div className="load-more"><Button className="press-button paper" onClick={() => setLimit(value => value + 6)}>{t('loadSix')} <ArrowDown size={17} /></Button><span>{t('shown', { shown: Math.min(limit, filtered.length), total: filtered.length })}</span></div>}
              </TabsContent>
            ))}
          </Tabs>
        </section>

        {siteConfig.miniProgramCode && (<aside id="miniprogram" className="mini-program-card paper-card" aria-labelledby="mini-program-title">
          <a className="mini-program-code" href={siteConfig.miniProgramCode} target="_blank" rel="noopener noreferrer" aria-label={t('miniProgramEnlarge')}>
            <img src={siteConfig.miniProgramCode} alt={t('miniProgramCodeAlt')} width="720" height="720" loading="lazy" />
          </a>
          <div className="mini-program-copy">
            <p className="mini-program-label">{t('miniProgramLabel')}</p>
            <h2 id="mini-program-title" lang="zh-CN">Tibo重置助手</h2>
            <p>{t('miniProgramScan')}</p>
            <p className="mini-program-search">{t('miniProgramSearch')}<strong lang="zh-CN">Tibo重置助手</strong></p>
            <a className="mini-program-enlarge" href={siteConfig.miniProgramCode} target="_blank" rel="noopener noreferrer">{t('miniProgramEnlarge')} <ArrowUpRight size={16} /></a>
          </div>
        </aside>)}

        {siteConfig.wechatCode && (<aside id="wechat" className="mini-program-card wechat-contact-card paper-card" aria-labelledby="wechat-contact-title">
          <a className="mini-program-code" href={siteConfig.wechatCode} target="_blank" rel="noopener noreferrer" aria-label={t('wechatContactEnlarge')}>
            <img src={siteConfig.wechatCode} alt={t('wechatContactCodeAlt')} width="660" height="660" loading="lazy" />
          </a>
          <div className="mini-program-copy">
            <p className="mini-program-label">{t('wechatContactLabel')}</p>
            <h2 id="wechat-contact-title" lang="zh-CN">{siteConfig.wechatName}</h2>
            <p>{t('wechatContactScan')}</p>
            <a className="mini-program-enlarge" href={siteConfig.wechatCode} target="_blank" rel="noopener noreferrer">{t('wechatContactEnlarge')} <ArrowUpRight size={16} /></a>
          </div>
        </aside>)}

        <aside className="about-strip">
          <span className="about-symbol"><Radio size={31} /></span>
          <div><h2>{t('aboutTitle')}</h2><p>{t('aboutText')}</p></div>
          <Button className="press-button yellow" onClick={copyLink}>{copied ? <Check size={17} /> : <Copy size={17} />}{copied ? t('copied') : t('copy')}</Button>
        </aside>
        <p className="copy-status" role="status">{copyError ? t('copyFailure') : copied ? t('copySuccess') : ''}</p>
      </main>

      <Dialog open={!!selectedRecord} onOpenChange={open => { if (!open) closePost(); }}>
        <DialogContent className="record-dialog"><DialogHeader><DialogTitle>{t('brand')} · {c.openRecord}</DialogTitle><DialogDescription>{selectedRecord ? formatStamp(selectedRecord.announced_at, locale) : ''}</DialogDescription></DialogHeader>
          {selectedRecord && <div className="record-dialog-body"><AnnouncementStatus record={selectedRecord} locale={locale} detail /><PostContent record={selectedRecord} locale={locale} />
            {!!selectedRecord.related_record_ids?.length && <div className="related-posts"><strong>{c.related}</strong>{selectedRecord.related_record_ids.map(id => <Button key={id} variant="ghost" onClick={() => openPost(id)}>{formatStamp(feed!.records.find(r => r.id === id)!.announced_at, locale)}</Button>)}</div>}
            <div className="record-actions"><a href={selectedRecord.source_url} target="_blank" rel="noopener noreferrer">{t('fullOriginal')} ↗</a><Button onClick={() => void sharePost(selectedRecord)}>{sharedPost === selectedRecord.id ? t('copied') : c.shareRecord}</Button></div>
          </div>}
        </DialogContent>
      </Dialog>

      <footer className="site-footer">
        <div className="footer-brand"><Radio size={18} /><strong>{t('footerBrand')}</strong><span>{t('footerTag')}</span></div>
        <p>{t('sourceBefore')}<a href="https://x.com/thsottiaux" target="_blank" rel="noopener noreferrer">@thsottiaux <ArrowUpRight size={12} /></a>{t('sourceAfter')}</p>
        <div className="footer-bottom"><span>{t('footerNote')}</span><a href="#latest">{t('backTop')} <ArrowRight size={14} /></a></div>
      </footer>
    </div>
  );
}
