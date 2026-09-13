import { AlertTriangle, CheckCircle2, CirclePause, ExternalLink } from 'lucide-react';
import { collectionIssue, validCollectionStatus, type CollectionStatus } from '@/lib/collection-status';
import { formatStamp, type Locale } from '@/lib/i18n';

export function CollectionNotice({ status, locale, snapshot, unavailable = false }: { status?: CollectionStatus; locale: Locale; snapshot: boolean; unavailable?: boolean }) {
  const zh = locale === 'zh';
  if (unavailable || !validCollectionStatus(status)) return <p className="error-note" role="status">{zh ? '无法读取本站的最新处理状态，X 采集与 Codex 分析是否正常暂时未知。' : 'The latest processing status is unavailable. X collection and Codex analysis status are unknown.'}</p>;
  const disabled = status.state === 'disabled';
  const checking = status.state === 'checking';
  const good = status.state === 'ok';
  const { key: issueKey, stage: issue, message: reason } = collectionIssue(status);
  const title = disabled ? (zh ? '实时采集未开启' : 'Live collection is off') : checking ? (zh ? '正在检查部署服务器能否访问 X' : 'Checking X access from the deployment server') : good ? (zh ? '最近一轮 X 采集成功' : 'The latest X collection succeeded') :
    status.state === 'stale' || issueKey === 'analysis' ? reason[locale][0] : issueKey === 'feed' ? (zh ? '暂时无法从 Tibo 的 X 页面获取最新公告' : 'Latest announcements could not be collected from Tibo’s X page') : (zh ? '回复与观察线索采集不完整' : 'Reply and watch collection is incomplete');
  const body = disabled ? (zh ? '当前显示已有数据。需要实时更新时，请由部署者开启采集并确认服务器可以访问 X。' : 'Existing data is displayed. Enable live collection and ensure the deployment server can access X to receive updates.') :
    checking ? (zh ? '首次检查尚未完成，已有数据会继续显示。' : 'The first check is still running. Existing data remains visible.') :
    good ? (zh ? '公开页面可能遗漏回复或暗示；采集成功不代表覆盖全部动态。' : 'Public pages may omit replies or hints; a successful collection does not guarantee complete coverage.') : reason[locale][1];
  const date = (value: string | null) => value ? formatStamp(value, locale) : (zh ? '本次启动后尚无成功记录' : 'No successful check since startup');
  const stages = (['feed', 'watch', 'analysis'] as const).filter(key => status.stages[key]);
  const stageLabel = { feed: zh ? 'X 公告采集' : 'X announcements', watch: zh ? '回复与观察' : 'Replies and watch', analysis: zh ? 'Codex 翻译与分析' : 'Codex translation and analysis' };
  return <section className={'collection-notice paper-card ' + (good ? 'collection-ok' : disabled ? 'collection-off' : 'collection-warning')} aria-label={zh ? '采集与模型处理状态' : 'Collection and model processing status'} role="status" aria-live="polite">
    <div className="collection-heading">{good ? <CheckCircle2 size={20} /> : disabled ? <CirclePause size={20} /> : <AlertTriangle size={20} />}<strong>{title}</strong></div>
    {!good && !disabled && !checking && status.state !== 'stale' && <p className="collection-reason">{stageLabel[issueKey]} · {reason[locale][0]}{issue.http_status ? ` · HTTP ${issue.http_status}` : ''}</p>}
    <p>{body}</p>
    {(!good || snapshot) && <p className="collection-retained">{zh ? (snapshot ? '当前为历史快照。' : '当前保留上次成功取得的数据。') + '数据未更新不代表没有新公告。' : (snapshot ? 'This is a historical snapshot. ' : 'The last successful data is retained. ') + 'Unchanged data does not mean there are no new announcements.'}</p>}
    <details><summary>{zh ? '采集详情与部署排查' : 'Collection details and deployment help'}</summary>
      <dl>{stages.map(key => { const stage = status.stages[key]!; return <div key={key}><dt>{stageLabel[key]}</dt><dd>{zh ? '状态' : 'Status'}: {stage.code}<br />{zh ? '最近检查' : 'Last attempt'}: {stage.checked_at ? formatStamp(stage.checked_at, locale) : '—'}<br />{zh ? '最近成功' : 'Last success'}: {date(stage.last_success_at)}</dd></div>; })}</dl>
      <p>{zh ? '需要能访问 X 的是部署服务器。你手机或电脑能打开 X，并不能证明服务器网络可用；只读刷新不会额外触发 X 请求。' : 'X must be accessible from the deployment server. Access on your phone or computer does not prove server connectivity. Refreshing this page only reads status; it does not trigger an extra X request.'}</p>
      {status.enabled && <p>{zh ? `每轮处理完成后至少等待 ${status.interval_seconds} 秒再试。` : `The worker waits at least ${status.interval_seconds} seconds after each cycle before retrying.`}</p>}
      <a href="https://github.com/fehuing/tibo-reset-assistant/blob/main/docs/DEPLOYMENT.md#采集失败提示与排查" target="_blank" rel="noopener noreferrer">{zh ? '查看部署排查说明' : 'Deployment troubleshooting'} <ExternalLink size={14} /></a>
    </details>
  </section>;
}
