'use client';
/* oxlint-disable next/no-img-element -- This static export serves an existing local avatar without an image optimizer. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Eye } from 'lucide-react';
import { runtimeBase } from '@/lib/runtime-base';
import { formatStamp, type Locale } from '@/lib/i18n';

type Hint = {
  episode_id: string; source_url: string; text: string; observed_at: string;
  expires_at: string; verified_at: string; discovered_via: string;
  reply_context?: { text: string; author: string; source_url: string } | null;
};
type Watch = {
  schema_version: number; watch: Hint | null; state: 'empty' | 'active' | 'expired' | 'new_announcement';
  stale: boolean; yes: number; no: number; total: number; yes_percent: number | null;
};
const copy = {
  zh: {
    label: '重置观察', empty: '暂未发现新的重置线索', loading: '正在查看重置线索…', unavailable: '观察数据暂时无法读取',
    pending: '你觉得这次会重置吗？', agree: '的投票认为会重置', vote: '你的看法', yes: '会', no: '不会',
    cutoff: '观察截止', zone: '北京时间', rule: '本站观察窗口为原帖发布后 24 小时，并非官方承诺时间。',
    note: '社区投票 · 不代表实际概率，也不计入已发放统计', first: '还没有投票，来表达你的看法',
    source: '查看原帖', reply: '回复内容', view: '查看上下文', selected: '已记录，可更改选择', error: '提交失败，请重试',
    closed: '观察已结束 · 尚未据此确认发放', announced: '已有新发放公告 · 本轮观察结束', stale: '来源校验延迟，暂缓投票',
    storage: '浏览器需允许保存匿名投票标识后才能投票', details: '这条线索如何收录',
    direct: '来自公开 X 页面，按原文规则收录；不使用大模型判断。',
    reference: '线索链接来自参考站，正文及作者已从 X 原帖核实；不沿用参考站票数。',
    user: '线索链接由本次人工核对参考页面找到，正文及作者已从 X 原帖核实。',
    coverage: '公开页面可能漏掉回复或隐喻，不保证完整监控。每个浏览器每轮保留一个选择。',
  },
  en: {
    label: 'RESET WATCH', empty: 'No new reset hint found', loading: 'Checking for reset hints…', unavailable: 'Watch data is temporarily unavailable',
    pending: 'Will there be a reset this time?', agree: 'of votes expect a reset', vote: 'YOUR TAKE', yes: 'Yes', no: 'No',
    cutoff: 'Watch closes', zone: 'Beijing time', rule: 'Our observation window is 24 hours after the post. This is not an official deadline.',
    note: 'Community votes · Not an actual probability or a confirmed reset', first: 'No votes yet. Share your take.',
    source: 'View on X', reply: 'Replying to', view: 'View context', selected: 'Vote saved. You can change it.', error: 'Could not save your vote. Try again.',
    closed: 'Watch ended · This hint has not confirmed a reset', announced: 'A new delivery announcement has closed this watch', stale: 'Source check delayed. Voting paused.',
    storage: 'Allow browser storage for an anonymous voting ID to vote.', details: 'How this hint was collected',
    direct: 'Found on public X pages and selected by source-text rules. No model classification.',
    reference: 'Link discovered through the reference site; author and text verified on X. Reference vote counts are not imported.',
    user: 'Link found during a manual check of the reference page; author and text verified on X.',
    coverage: 'Public pages may omit replies or subtle hints. Coverage is incomplete. One choice per browser per watch.',
  },
};

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

  const expired = !!hint && now >= Date.parse(hint.expires_at);
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

  return <section className={'watch-card' + (!hint ? ' watch-empty' : '')} aria-labelledby="watch-title">
    <div className="watch-eyebrow"><Eye size={15} aria-hidden="true" />{t.label}</div>
    {!hint ? <p id="watch-title">{failed ? t.unavailable : data ? t.empty : t.loading}</p> : <>
      <div className="watch-top">
        <div className="watch-headline">
          <h2 id="watch-title">{percentage === null ? t.pending : <><span className="watch-percent">{percentage}%</span> {t.agree}</>}</h2>
          <p className="watch-deadline">{t.cutoff} <time dateTime={hint.expires_at}>{formatStamp(hint.expires_at, locale)}</time> · {t.zone}</p>
        </div>
        <fieldset className="watch-poll" aria-label={t.vote} aria-busy={busy}>
          <span className="watch-poll-label">{t.vote}</span>
          {(['yes', 'no'] as const).map(v => <button key={v} type="button" className={'watch-vote watch-' + v}
            aria-pressed={choice === v} disabled={!active || busy || !storageReady} onClick={() => void vote(v)}>
            <span>{t[v]}</span><span className="watch-count">{new Intl.NumberFormat(locale).format(data?.[v] ?? 0)}</span>
          </button>)}
        </fieldset>
      </div>
      <div className="watch-post">
        <img src="/radar/tibo-avatar.jpg" alt="" width="36" height="36" />
        <div className="watch-post-body">
          <div className="watch-byline"><strong>Tibo</strong><span>@thsottiaux</span><time dateTime={hint.observed_at}>{formatStamp(hint.observed_at, locale)}</time></div>
          {hint.reply_context && <details className="watch-context"><summary>{t.reply} @{hint.reply_context.author}</summary><p>{hint.reply_context.text}</p>
            {/^https:\/\/x\.com\/[A-Za-z0-9_]+\/status\/\d+$/.test(hint.reply_context.source_url) && <a href={hint.reply_context.source_url} target="_blank" rel="noopener noreferrer">{t.view} ↗</a>}
          </details>}
          <p className="watch-body">{hint.text}</p>
          <a className="watch-source" href={hint.source_url} target="_blank" rel="noopener noreferrer">{t.source}<ArrowUpRight size={15} /></a>
        </div>
      </div>
      <output className="watch-vote-status">{error ? t.error : failed || stale ? t.stale : data?.state === 'new_announcement' ? t.announced : expired || data?.state === 'expired' ? t.closed : !storageReady ? t.storage : choice ? t.selected : !total ? t.first : ''}</output>
      <div className="watch-footnote"><p>{t.note}</p><p>{t.rule}</p></div>
      <details className="watch-method"><summary>{t.details}</summary><p>{hint.discovered_via === 'reference_pointer' ? t.reference : hint.discovered_via === 'user_reference' ? t.user : t.direct}</p><p>{t.coverage}</p></details>
    </>}
  </section>;
}
