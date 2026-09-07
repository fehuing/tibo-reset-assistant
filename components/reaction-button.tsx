'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { text as i18nText, type Locale } from '@/lib/i18n';
import { runtimeBase } from '@/lib/runtime-base';

type Reaction = {
  schema_version: number;
  cycle_id: string;
  since: string;
  count: number;
};

type Burst = {
  id: number;
  value: string;
  style: CSSProperties & Record<`--${string}`, string>;
};

function isReaction(value: unknown): value is Reaction {
  if (!value || typeof value !== 'object') return false;
  const reaction = value as Reaction;
  return reaction.schema_version === 1 && typeof reaction.cycle_id === 'string' &&
    Number.isFinite(Date.parse(reaction.since)) && Number.isSafeInteger(reaction.count) && reaction.count >= 0;
}

function requestId() {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

export function ReactionButton({ locale, now }: { locale: Locale; now: number }) {
  const [reaction, setReaction] = useState<Reaction | null>(null);
  const [optimistic, setOptimistic] = useState(0);
  const [pressed, setPressed] = useState(false);
  const [bursts, setBursts] = useState<Burst[]>([]);
  const pending = useRef(0);
  const flushTimer = useRef<number | null>(null);
  const pressTimer = useRef<number | null>(null);
  const burstId = useRef(0);
  const sendChain = useRef<Promise<void>>(Promise.resolve());

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(runtimeBase() + '/api/reactions', { cache: 'no-store', signal });
      if (!response.ok) return;
      const value = await response.json();
      if (isReaction(value)) {
        setReaction(current => current && current.cycle_id === value.cycle_id && current.count > value.count ? current : value);
      }
    } catch { /* The button stays unavailable until the next poll. */ }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const poll = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh(controller.signal);
    }, 15000);
    const onVisible = () => { if (document.visibilityState === 'visible') void refresh(controller.signal); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      controller.abort();
      clearInterval(poll);
      if (flushTimer.current !== null) clearTimeout(flushTimer.current);
      if (pressTimer.current !== null) clearTimeout(pressTimer.current);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refresh]);

  const thanksMode = !reaction || Date.parse(reaction.since) + 86400000 > now;
  const formatter = useMemo(() => new Intl.NumberFormat(locale === 'zh' ? 'zh-CN' : 'en-US'), [locale]);
  const count = reaction ? reaction.count + optimistic : null;

  const send = useCallback(async (amount: number, id: string) => {
    try {
      const response = await fetch(runtimeBase() + '/api/reactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ request_id: id, n: amount }),
      });
      const value = await response.json().catch(() => null);
      if (response.ok && isReaction(value)) {
        setReaction(current => current && current.cycle_id === value.cycle_id && current.count > value.count ? current : value);
      }
      else void refresh();
    } catch {
      void refresh();
    } finally {
      setOptimistic(value => Math.max(0, value - amount));
    }
  }, [refresh]);

  const flush = useCallback(() => {
    flushTimer.current = null;
    const amount = pending.current;
    pending.current = 0;
    if (amount > 0) sendChain.current = sendChain.current.then(() => send(amount, requestId()));
  }, [send]);

  function addBurst() {
    const values = thanksMode
      ? locale === 'zh' ? ['+1', '🙏', '谢谢', '🧡'] : ['+1', '🙏', 'thx', '🧡']
      : locale === 'zh' ? ['+1', '🙏', '求重置', '🔄'] : ['+1', '🙏', 'pls', '🔄'];
    const id = ++burstId.current;
    const burst: Burst = {
      id,
      value: values[Math.floor(Math.random() * values.length)],
      style: {
        '--burst-x': `${Math.round(Math.random() * 64 - 48)}px`,
        '--burst-y': `${-58 - Math.round(Math.random() * 42)}px`,
        '--burst-rotate': `${Math.round(Math.random() * 28 - 14)}deg`,
      },
    };
    setBursts(items => [...items.slice(-8), burst]);
    window.setTimeout(() => setBursts(items => items.filter(item => item.id !== id)), 900);
  }

  function react() {
    if (!reaction) return;
    try { navigator.vibrate?.(12); } catch { /* Haptics are optional. */ }
    setOptimistic(value => value + 1);
    pending.current += 1;
    setPressed(false);
    window.requestAnimationFrame(() => setPressed(true));
    if (pressTimer.current !== null) clearTimeout(pressTimer.current);
    pressTimer.current = window.setTimeout(() => setPressed(false), 280);
    addBurst();
    if (pending.current >= 10) {
      if (flushTimer.current !== null) clearTimeout(flushTimer.current);
      flush();
    } else if (flushTimer.current === null) {
      flushTimer.current = window.setTimeout(flush, 120);
    }
  }

  const label = i18nText(locale, thanksMode ? 'reactionThanks' : 'reactionBeg');
  const action = i18nText(locale, thanksMode ? 'reactionThanksAria' : 'reactionBegAria');
  const countLabel = count === null
    ? i18nText(locale, 'reactionUnavailable')
    : i18nText(locale, 'reactionCount', { count: formatter.format(count) });

  return (
    <div className="reaction-widget" data-mode={thanksMode ? 'thanks' : 'beg'}>
      <button
        type="button"
        className={'reaction-button' + (pressed ? ' is-pressed' : '')}
        onClick={react}
        disabled={!reaction}
        aria-label={`${action} · ${countLabel}`}
        title={action}
      >
        <span className="reaction-emoji" aria-hidden="true">🙏</span>
        <span>{label}</span>
        <span className="reaction-count" aria-live="polite" aria-atomic="true">{count === null ? '—' : formatter.format(count)}</span>
      </button>
      <span className="reaction-bursts" aria-hidden="true">
        {bursts.map(burst => <span className="reaction-burst" style={burst.style} key={burst.id}>{burst.value}</span>)}
      </span>
    </div>
  );
}
