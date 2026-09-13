'use client';

import { Fragment, useEffect, useMemo, useRef, type CSSProperties } from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { localizedExcerpt, resetLabel, text as i18nText, type Locale } from '@/lib/i18n';
import { announcementCopy, statusView } from '@/lib/announcements';
import type { ResetRecord } from '@/lib/post-content';
import { calendarDateKey as dateKey, calendarWindow } from '@/lib/calendar-history';

type CalendarRecord = {
  id: string;
  reset_type: string;
  announced_at: string;
  excerpt: string;
  source_url: string;
  source_type: string;
  status?: 'planned' | 'announced' | 'uncertain';
  historical_verification?: ResetRecord['historical_verification'];
};
const DAY = 86400000;
const BEIJING = 8 * 3600000;

export function ResetCalendar({ records, now, ready, locale, onSelect }: { records: CalendarRecord[]; now: number; ready: boolean; locale: Locale; onSelect?: (id: string) => void }) {
  const scroll = useRef<HTMLDivElement>(null);
  const today = dateKey(now);
  const t = (key: Parameters<typeof i18nText>[1], values?: Record<string, string | number>) => i18nText(locale, key, values);
  const weekdays = locale === 'zh' ? ['', '一', '', '三', '', '五', ''] : ['', 'Mon', '', 'Wed', '', 'Fri', ''];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const weeks = useMemo(() => {
    const { first, end, columns } = calendarWindow(Date.parse(today + 'T00:00:00+08:00'));
    const byDay = new Map<string, CalendarRecord[]>();
    for (const record of records) {
      const key = dateKey(Date.parse(record.announced_at));
      byDay.set(key, [...(byDay.get(key) ?? []), record]);
    }
    return Array.from({ length: columns }, (_, week) =>
      Array.from({ length: 7 }, (_, row) => {
        const time = first + (week * 7 + row) * DAY;
        const key = dateKey(time);
        return { key, future: time > end, month: new Date(time + BEIJING).getUTCMonth() + 1, events: byDay.get(key) ?? [] };
      }),
    );
  }, [records, today]);

  useEffect(() => {
    if (scroll.current) scroll.current.scrollLeft = scroll.current.scrollWidth;
  }, [today]);

  return (
    <section id="history" className="history-section" aria-labelledby="calendar-heading">
      <div className="calendar-heading">
        <h2 id="calendar-heading">{t('calendarTitle')}</h2>
        <div className="calendar-legend">
          <span className="calendar-range">{t('lastWeeks')}</span>
          <span><i className="legend-square regular" />{t('regular')}</span>
          <span><i className="legend-square banked" />{t('banked')}</span>
          <span><i className="legend-square" />{t('noRecord')}</span>
        </div>
      </div>
      <div className="calendar-card">
        <TooltipProvider delay={0}>
          <div className="calendar-container" style={{ '--calendar-columns': weeks.length, '--calendar-weekday-width': locale === 'zh' ? '12px' : '24px' } as CSSProperties}>
            <div className="calendar-weekdays" aria-hidden="true">
              <span />
              {weekdays.map((label, index) => <span key={index}>{label}</span>)}
            </div>
            <div className="calendar-scroll" ref={scroll} role="region" aria-label={t('calendarRegion')} tabIndex={0}>
              <div className="calendar-grid" style={{ gridTemplateColumns: `repeat(${weeks.length}, var(--calendar-cell))` }}>
                {weeks.map((week, column) => (
                  <Fragment key={week[0].key}>
                    {(column === 0 || week[0].month !== weeks[column - 1][0].month) && <span className="calendar-month" style={{ gridColumn: column + 1, gridRow: 1 }}>{locale === 'zh' ? week[0].month + '月' : months[week[0].month - 1]}</span>}
                    {week.map((day, row) => {
                      const position = { gridColumn: column + 1, gridRow: row + 2 };
                      if (day.future) return <span key={day.key} className="calendar-day calendar-future" style={position} aria-hidden="true" />;
                      const event = day.events[0];
                      const kind = day.events.some(record => record.reset_type === 'banked') ? 'banked' : event ? 'regular' : '';
                      const pendingOnly = day.events.length > 0 && !day.events.some(record => record.status === 'announced');
                      const description = !ready ? t('loadingRecords') : day.events.length ? day.events.length + ' ' + announcementCopy[locale].calendarCount : t('noResetDay');
                      const statuses = Array.from(new Set(day.events.map(record => statusView(record, locale).label))).join(' / ');
                      return (
                        <Tooltip key={day.key}>
                          <TooltipTrigger
                            className={'calendar-day ' + kind + (pendingOnly ? ' pending-only' : '')}
                            style={position}
                            disabled={!ready}
                            aria-label={[day.key, description, t('beijing'), statuses].filter(Boolean).join(', ') + (event ? t('clickOriginal') : '')}
                            closeOnClick={!!event}
                            render={event ? <button type="button" onClick={() => onSelect?.(event.id)} /> : <button type="button" disabled={!ready} />}
                          />
                          <TooltipContent className="calendar-tooltip" sideOffset={12}>
                            <div>
                              <strong>{day.key}</strong><span className="calendar-tooltip-zone"> · {t('beijing')}</span>
                              {day.events.length ? day.events.map(record => (
                                <div className="calendar-tooltip-event" key={record.id}>
                                  <span>{resetLabel(locale, record.reset_type)} · {statusView(record, locale).label}{record.source_type === 'observed' ? t('observedNote') : ''}</span>
                                  {(() => { const excerpt = localizedExcerpt(locale, record.id, record.excerpt); return <p lang={excerpt.translated ? 'zh-CN' : 'en'}>{excerpt.value}</p>; })()}
                                </div>
                              )) : <p>{t('noResetSentence')}</p>}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      );
                    })}
                  </Fragment>
                ))}
              </div>
            </div>
          </div>
        </TooltipProvider>
      </div>
    </section>
  );
}
