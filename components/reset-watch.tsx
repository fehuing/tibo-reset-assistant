'use client';
/* oxlint-disable next/no-img-element -- This static export serves an existing local avatar without an image optimizer. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Eye } from 'lucide-react';
import { runtimeBase } from '@/lib/runtime-base';
import { formatStamp, type Locale } from '@/lib/i18n';
import { postScreenshot, type ResetRecord } from '@/lib/post-content';

type WatchAnalysis = {
  method: 'codex_cli'; model: string; analyzed_at: string;
  translation_zh: string; summary_zh: string; summary_en: string;
  signal: 'none' | 'hint' | 'announced' | 'in_progress' | 'delivered' | 'denied'; scope: 'global' | 'group' | 'personal' | 'unknown';
  prediction: { outlook: 'likely' | 'possible' | 'unlikely' | 'unknown'; reason_zh: string; reason_en: string };
  evidence: string[];
};

type Hint = {
  episode_id: string; source_url: string; text: string; observed_at: string;
  window_basis?: string;
  expires_at: string; verified_at: string; discovered_via: string;
  reply_context?: { text: string; author: string; source_url: string } | null;
  analysis?: WatchAnalysis;
  screenshot?: ResetRecord['screenshot'];
};
type Watch = {
  schema_version: number; watch: Hint | null; state: 'empty' | 'active' | 'expired' | 'new_announcement';
  stale: boolean; yes: number; no: number; total: number; yes_percent: number | null;
};
const copy = {
  zh: {
    label: '重置观察', empty: '暂未发现新的重置线索', loading: '正在查看重置线索…', unavailable: '观察数据暂时无法读取',
    pending: '你觉得这次会重置吗？', agree: '的社区投票认为会重置', vote: '你的看法', yes: '会', no: '不会',
    awaiting: '等待重置确认', untilRule: '预告发布后持续观察，确认重置或明确取消后自动关闭。',
    cutoff: '观察截止', zone: '北京时间', rule: '本站观察窗口为原帖发布后 24 小时，并非官方承诺时间。',
    note: '社区投票 · 不代表实际概率，也不计入已发放统计', first: '还没有投票，来表达你的看法',
    source: '查看原帖', reply: '回复内容', view: '查看上下文', selected: '已记录，可更改选择', error: '提交失败，请重试',
    closed: '观察已结束 · 尚未据此确认发放', announced: '已有新发放公告 · 本轮观察结束', stale: '来源校验延迟，暂缓投票',
    storage: '浏览器需允许保存匿名投票标识后才能投票', details: '这条线索如何收录',
    direct: '来自公开 X 页面，按原文规则收录；不使用大模型判断。',
    reference: '线索链接来自参考站，正文及作者已从 X 原帖核实；不沿用参考站票数。',
    user: '线索链接由本次人工核对参考页面找到，正文及作者已从 X 原帖核实。',
    coverage: '公开页面可能漏掉回复或隐喻，不保证完整监控。每个浏览器每轮保留一个选择。',
    ai: 'AI 推测', aiNote: '基于原帖与上下文的推测，不代表官方承诺或已重置。',
    likely: '较有可能重置', possible: '存在重置可能', unlikely: '目前不太可能重置', unknown: '线索不足，暂不能判断',
    translation: 'AI 中文翻译', original: '查看英文原文', screenshot: 'X 原页面截图', enlarge: '点击查看完整截图',
    aiMethod: '公开 X 动态采集后，由部署者配置的 Codex 模型翻译并分析重置线索；预测与已确认重置分开记录。',
    analyzed: '分析时间', evidence: '原文依据',
  },
  en: {
    label: 'RESET WATCH', empty: 'No new reset hint found', loading: 'Checking for reset hints…', unavailable: 'Watch data is temporarily unavailable',
    pending: 'Will there be a reset this time?', agree: 'of community votes expect a reset', vote: 'YOUR TAKE', yes: 'Yes', no: 'No',
    awaiting: 'Awaiting reset confirmation', untilRule: 'Watching after the post until a reset is confirmed or explicitly cancelled.',
    cutoff: 'Watch closes', zone: 'Beijing time', rule: 'Our observation window is 24 hours after the post. This is not an official deadline.',
    note: 'Community votes · Not an actual probability or a confirmed reset', first: 'No votes yet. Share your take.',
    source: 'View on X', reply: 'Replying to', view: 'View context', selected: 'Vote saved. You can change it.', error: 'Could not save your vote. Try again.',
    closed: 'Watch ended · This hint has not confirmed a reset', announced: 'A new delivery announcement has closed this watch', stale: 'Source check delayed. Voting paused.',
    storage: 'Allow browser storage for an anonymous voting ID to vote.', details: 'How this hint was collected',
    direct: 'Found on public X pages and selected by source-text rules. No model classification.',
    reference: 'Link discovered through the reference site; author and text verified on X. Reference vote counts are not imported.',
    user: 'Link found during a manual check of the reference page; author and text verified on X.',
    coverage: 'Public pages may omit replies or subtle hints. Coverage is incomplete. One choice per browser per watch.',
    ai: 'AI INFERENCE', aiNote: 'An interpretation of the post and its context, not an official promise or a confirmed reset.',
    likely: 'A reset looks likely', possible: 'A reset is possible', unlikely: 'A reset looks unlikely for now', unknown: 'Not enough evidence to tell',
    translation: 'AI Chinese translation', original: 'Read the English original', screenshot: 'Original X page capture', enlarge: 'Open the full capture',
    aiMethod: 'After public X activity is collected, the configured Codex model translates it and assesses reset signals. Predictions stay separate from confirmed resets.',
    analyzed: 'Analyzed', evidence: 'Source evidence',
  },
};

function analysisFor(hint: Hint | null | undefined): WatchAnalysis | null {
  const a = hint?.analysis;
  if (!a || a.method !== 'codex_cli' || typeof a.model !== 'string' || !/^[A-Za-z0-9._-]{1,80}$/.test(a.model) || !Number.isFinite(Date.parse(a.analyzed_at)) ||
      !['none', 'hint', 'announced', 'in_progress', 'delivered', 'denied'].includes(a.signal) || !['global', 'group', 'personal', 'unknown'].includes(a.scope) ||
      ![a.translation_zh, a.summary_zh, a.summary_en].every(s => typeof s === 'string' && s.length <= 60000) ||
      !a.prediction || !['likely', 'possible', 'unlikely', 'unknown'].includes(a.prediction.outlook) ||
      ![a.prediction.reason_zh, a.prediction.reason_en].every(s => typeof s === 'string' && s.length <= 10000) ||
      !Array.isArray(a.evidence) || a.evidence.length > 20 || !a.evidence.every(s => typeof s === 'string' && s.length <= 60000)) return null;
  return a;
}

function valid(value: unknown): value is Watch {
  if (!value || typeof value !== 'object') return false;
  const v = value as Watch;
  return v.schema_version === 1 && ['empty', 'active', 'expired', 'new_announcement'].includes(v.state) &&
    typeof v.stale === 'boolean' && [v.yes, v.no, v.total].every(n => Number.isSafeInteger(n) && n >= 0) &&
    v.yes + v.no === v.total && (v.watch === null ||
      /^\d{10,25}$/.test(v.watch.episode_id) && v.watch.source_url === 'https://x.com/thsottiaux/status/' + v.watch.episode_id &&
      typeof v.watch.text === 'string' && [v.watch.expires_at, v.watch.observed_at, v.watch.verified_at].every(t => Number.isFinite(Date.parse(t))));
}

export function ResetWatch({ locale, now }: { locale: Locale; now: number }) {
  const [data, setData] = useState<Watch | null>(null);
  const [choice, setChoice] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [failed, setFailed] = useState(false);
  const [storageReady, setStorageReady] = useState(false);
  const [failedImage, setFailedImage] = useState('');
  const identity = useRef('');
  const currentEpisode = useRef('');
  const requestSequence = useRef(0);
  const t = copy[locale];
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const sequence = ++requestSequence.current;
    try {
      const response = await fetch(runtimeBase() + '/api/watch', { cache: 'no-store', signal });
      const value: unknown = await response.json();
      if (!response.ok || !valid(value)) throw new Error('Unavailable');
      if (sequence === requestSequence.current) {
        setData(value); setFailed(false); setStorageReady(!!identity.current);
        const episode = value.watch?.episode_id ?? '';
        if (episode !== currentEpisode.current) {
          currentEpisode.current = episode; setChoice(''); setError('');
          try { setChoice(localStorage.getItem('tibo-watch-vote:' + episode) || ''); } catch { /* Optional preference. */ }
        }
      }
    } catch (err) {
      if (!(err instanceof Error && err.name === 'AbortError') && sequence === requestSequence.current) setFailed(true);
    }
  }, []);
  useEffect(() => {
    try {
      let id = localStorage.getItem('tibo-watch-voter');
      if (!id || !/^[A-Za-z0-9_-]{16,64}$/.test(id)) {
        id = crypto.randomUUID(); localStorage.setItem('tibo-watch-voter', id);
      }
      identity.current = id;
    } catch { /* Read-only display remains usable without browser storage. */ }
    const controller = new AbortController();
    void Promise.resolve().then(() => refresh(controller.signal));
    const poll = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh(controller.signal); }, 30000);
    const visible = () => { if (document.visibilityState === 'visible') void refresh(controller.signal); };
    document.addEventListener('visibilitychange', visible);
    return () => { controller.abort(); clearInterval(poll); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);
  const hint = data?.watch;
  const analysis = analysisFor(hint);
  const forecast = analysis && analysis.scope !== 'personal' && ['hint', 'announced'].includes(analysis.signal) ? analysis.prediction : null;
  const translated = locale === 'zh' && !!analysis?.translation_zh.trim();
  const shot = hint ? postScreenshot(hint) : null;
  const listImage = shot?.thumbnail ?? shot;

  const untilConfirmed = hint?.window_basis === 'until_reset_confirmed';
  const expired = !!hint && !untilConfirmed && now >= Date.parse(hint.expires_at);
  const stale = !!hint && (data?.stale || now - Date.parse(hint.verified_at) > 480000);
  const active = !!hint && data?.state === 'active' && !expired && !stale && !failed;
  const total = data?.total ?? 0;
  const percentage = total ? Math.round(data!.yes / total * 100) : null;
  async function vote(next: 'yes' | 'no') {
    if (!hint || !active || !identity.current || busy) return;
    setBusy(true); setError('');
    ++requestSequence.current; // Do not let an older read overwrite the vote response.
    try {
      const response = await fetch(runtimeBase() + '/api/watch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ episode_id: hint.episode_id, voter_id: identity.current, vote: next }),
      });
      const value: unknown = await response.json();
      if (!response.ok || !valid(value)) throw new Error('Vote failed');
      setData(value); setChoice(next); setFailed(false);
      try { localStorage.setItem('tibo-watch-vote:' + hint.episode_id, next); } catch { /* Server has saved the choice. */ }
    } catch { setError('vote'); void refresh(); }
    finally { setBusy(false); }
  }

  if (data && (!hint || data.state === 'new_announcement')) return null;
  return <section className={'watch-card' + (!hint ? ' watch-empty' : '')} aria-labelledby="watch-title">
    <div className="watch-eyebrow"><Eye size={15} aria-hidden="true" />{t.label}</div>
    {!hint ? <p id="watch-title">{failed ? t.unavailable : data ? t.empty : t.loading}</p> : <>
      <div className="watch-top">
        <div className="watch-headline">
          <h2 id="watch-title">{percentage === null ? t.pending : <><span className="watch-percent">{percentage}%</span> {t.agree}</>}</h2>
          <p className="watch-deadline">{untilConfirmed ? t.awaiting : <>{t.cutoff} <time dateTime={hint.expires_at}>{formatStamp(hint.expires_at, locale)}</time> · {t.zone}</>}</p>
        </div>
        <fieldset className="watch-poll" aria-label={t.vote} aria-busy={busy}>
          <span className="watch-poll-label">{t.vote}</span>
          {(['yes', 'no'] as const).map(v => <button key={v} type="button" className={'watch-vote watch-' + v}
            aria-pressed={choice === v} disabled={!active || busy || !storageReady} onClick={() => void vote(v)}>
            <span>{t[v]}</span><span className="watch-count">{new Intl.NumberFormat(locale).format(data?.[v] ?? 0)}</span>
          </button>)}
        </fieldset>
      </div>
      {forecast && <aside className="watch-ai" aria-label={t.ai}>
        <div className="watch-ai-label">{t.ai} · {analysis?.model}</div>
        <strong>{t[forecast.outlook]}</strong>
        <p>{locale === 'zh' ? forecast.reason_zh || analysis?.summary_zh : forecast.reason_en || analysis?.summary_en}</p>
        <small>{t.aiNote}</small>
      </aside>}
      <div className="watch-post">
        <img src="/radar/tibo-avatar.jpg" alt="" width="36" height="36" />
        <div className="watch-post-body">
          <div className="watch-byline"><strong>Tibo</strong><span>@thsottiaux</span><time dateTime={hint.observed_at}>{formatStamp(hint.observed_at, locale)}</time></div>
          {hint.reply_context && <details className="watch-context"><summary>{t.reply} @{hint.reply_context.author}</summary><p>{hint.reply_context.text}</p>
            {/^https:\/\/x\.com\/[A-Za-z0-9_]+\/status\/\d+$/.test(hint.reply_context.source_url) && <a href={hint.reply_context.source_url} target="_blank" rel="noopener noreferrer">{t.view} ↗</a>}
          </details>}
          {translated && <div className="watch-translation-label">{t.translation}</div>}
          <p className="watch-body" lang={translated ? 'zh-CN' : 'en'}>{translated ? analysis!.translation_zh : hint.text}</p>
          {translated && <details className="watch-original"><summary>{t.original}</summary><p className="watch-body" lang="en">{hint.text}</p></details>}
          {shot && listImage && failedImage !== listImage.url && <a className="watch-capture" href={shot.url} target="_blank" rel="noopener noreferrer" aria-label={t.enlarge}>
            <span className="watch-capture-viewport"><img src={listImage.url} width={listImage.width} height={listImage.height} loading="lazy" decoding="async" alt={t.screenshot} onError={() => setFailedImage(listImage.url)} /></span>
            <span>{t.screenshot} · {t.enlarge} ↗</span>
          </a>}
          <a className="watch-source" href={hint.source_url} target="_blank" rel="noopener noreferrer">{t.source}<ArrowUpRight size={15} /></a>
        </div>
      </div>
      <output className="watch-vote-status">{error ? t.error : failed || stale ? t.stale : data?.state === 'new_announcement' ? t.announced : expired || data?.state === 'expired' ? t.closed : !storageReady ? t.storage : choice ? t.selected : !total ? t.first : ''}</output>
      <div className="watch-footnote"><p>{t.note}</p><p>{untilConfirmed ? t.untilRule : t.rule}</p></div>
      <details className="watch-method"><summary>{t.details}</summary><p>{analysis ? t.aiMethod : hint.discovered_via === 'reference_pointer' ? t.reference : hint.discovered_via === 'user_reference' ? t.user : t.direct}</p>
        {analysis && <><p>{t.analyzed} <time dateTime={analysis.analyzed_at}>{formatStamp(analysis.analyzed_at, locale)}</time> · {t.zone}</p>
          {analysis.evidence.length > 0 && <details className="watch-evidence"><summary>{t.evidence}</summary>{analysis.evidence.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}</details>}</>}
        <p>{t.coverage}</p></details>
    </>}
  </section>;
}
