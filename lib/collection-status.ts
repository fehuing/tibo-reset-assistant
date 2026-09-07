export type CollectionStage = { state: 'disabled' | 'checking' | 'ok' | 'error' | 'degraded'; code: string; http_status?: number; checked_at: string | null; last_success_at: string | null };
export type CollectionStatus = { schema_version: 1; enabled: boolean; state: 'disabled' | 'checking' | 'ok' | 'error' | 'degraded' | 'stale'; source_url: string; stages: { feed: CollectionStage; watch: CollectionStage }; interval_seconds: number; next_check_at: string | null; stale: boolean };

export function validCollectionStatus(value: unknown): value is CollectionStatus {
  if (!value || typeof value !== 'object') return false;
  const v = value as CollectionStatus;
  return v.schema_version === 1 && typeof v.enabled === 'boolean' && typeof v.stale === 'boolean' &&
    ['disabled', 'checking', 'ok', 'error', 'degraded', 'stale'].includes(v.state) &&
    v.source_url === 'https://x.com/thsottiaux' && Number.isFinite(v.interval_seconds) && v.interval_seconds >= 120 &&
    !!v.stages && [v.stages.feed, v.stages.watch].every(s => s && typeof s.code === 'string' &&
      ['disabled', 'checking', 'ok', 'error', 'degraded'].includes(s.state) &&
      [s.checked_at, s.last_success_at].every(t => t === null || typeof t === 'string' && Number.isFinite(Date.parse(t))));
}

export const collectionMessages: Record<string, { zh: [string, string]; en: [string, string] }> = {
  x_dns: { zh: ['无法解析 X 的域名', '部署服务器没有成功解析 x.com。请检查服务器的 DNS 和出站网络。'], en: ['X DNS lookup failed', 'The deployment server could not resolve x.com. Check its DNS and outbound connectivity.'] },
  x_timeout: { zh: ['访问 X 超时', '部署服务器连接或读取 X 页面超时。请检查服务器的出站网络或代理是否可用。'], en: ['X request timed out', 'The deployment server timed out while connecting to or reading X. Check its outbound network or configured proxy.'] },
  x_network: { zh: ['部署服务器暂时无法连接 X', '连接失败可能与服务器网络、防火墙或代理有关，不能据此确认 Tibo 没有发布新动态。'], en: ['The deployment server cannot reach X', 'The connection failed. Check the server network, firewall or proxy; this is not evidence that Tibo has not posted.'] },
  x_tls: { zh: ['X 的安全连接校验失败', '请检查服务器时间、证书和代理配置，不要关闭证书验证。'], en: ['X secure connection check failed', 'Check the server clock, certificates and proxy configuration. Keep certificate verification enabled.'] },
  x_access_denied: { zh: ['X 限制了本次访问', 'X 返回了 401 或 403。即使网络可达，也可能因登录要求或访问策略无法采集。'], en: ['X denied this request', 'X returned 401 or 403. Login requirements or access policies can prevent collection even when the network works.'] },
  x_rate_limited: { zh: ['X 暂时限制了请求频率', '收到 429 响应。程序会按既定间隔重试，请勿通过频繁刷新增加采集请求。'], en: ['X temporarily rate-limited requests', 'X returned 429. Collection retries on its schedule; avoid increasing the request frequency.'] },
  x_unavailable: { zh: ['Tibo 的 X 页面暂不可用', 'X 返回了 404 或 410，当前无法读取目标页面；不能仅凭这一响应判断账号或推文已删除。'], en: ['Tibo’s X page is unavailable', 'X returned 404 or 410. This response alone does not establish that the account or post was deleted.'] },
  x_http: { zh: ['X 返回了异常响应', '部署服务器已收到响应，但未能正常读取页面。程序会自动重试。'], en: ['X returned an unexpected response', 'The server received a response but could not read the page successfully. Collection will retry.'] },
  x_parse: { zh: ['已收到页面，但无法识别推文内容', '公开页面可能改变结构、隐藏内容或显示登录页。请更新采集适配器；不是单纯的网络连接失败。'], en: ['Page received, but post content could not be read', 'The public page may have changed structure, hidden its content or shown a login page. The collection adapter may need an update.'] },
  collector_error: { zh: ['采集程序处理失败', '请查看部署端日志，检查配置和数据目录。公开接口不会返回密钥、代理地址或原始异常内容。'], en: ['Collection processing failed', 'Check the deployment logs, configuration and data directory. Public diagnostics do not expose secrets, proxy addresses or raw exceptions.'] },
  worker_stale: { zh: ['采集任务长时间没有更新状态', '请检查部署端的采集进程是否仍在运行。当前状态不能代表 X 访问正常。'], en: ['The collection worker has stopped reporting', 'Check whether the collection process is still running. Its old status cannot confirm current X access.'] },
};
