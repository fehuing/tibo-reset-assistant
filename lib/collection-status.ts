export type CollectionStage = { state: 'disabled' | 'checking' | 'ok' | 'error' | 'degraded'; code: string; http_status?: number; checked_at: string | null; last_success_at: string | null };
export type CollectionStatus = { schema_version: 1; enabled: boolean; state: 'disabled' | 'checking' | 'ok' | 'error' | 'degraded' | 'stale'; source_url: string; stages: { feed: CollectionStage; watch: CollectionStage; analysis?: CollectionStage }; interval_seconds: number; next_check_at: string | null; stale: boolean };

export function validCollectionStatus(value: unknown): value is CollectionStatus {
  if (!value || typeof value !== 'object') return false;
  const v = value as CollectionStatus;
  return v.schema_version === 1 && typeof v.enabled === 'boolean' && typeof v.stale === 'boolean' &&
    ['disabled', 'checking', 'ok', 'error', 'degraded', 'stale'].includes(v.state) &&
    v.source_url === 'https://x.com/thsottiaux' && Number.isFinite(v.interval_seconds) && v.interval_seconds >= 120 &&
    !!v.stages && [v.stages.feed, v.stages.watch, ...(v.stages.analysis === undefined ? [] : [v.stages.analysis])].every(s => s && typeof s.code === 'string' &&
      ['disabled', 'checking', 'ok', 'error', 'degraded'].includes(s.state) &&
      [s.checked_at, s.last_success_at].every(t => t === null || typeof t === 'string' && Number.isFinite(Date.parse(t))));
}

export function collectionIssue(status: CollectionStatus) {
  const failed = (stage?: CollectionStage) => stage && ['error', 'degraded'].includes(stage.state);
  const key = failed(status.stages.feed) ? 'feed' : failed(status.stages.analysis) ? 'analysis' : 'watch';
  const stage = status.stages[key]!;
  const code = status.state === 'stale' ? 'worker_stale' : stage.code;
  const message = collectionMessages[code] ?? collectionMessages[key === 'analysis' ? 'analysis_failed' : 'collector_error'];
  return { key, stage, message } as const;
}

export const collectionMessages: Record<string, { zh: [string, string]; en: [string, string] }> = {
  model_auth_required: { zh: ['Codex 账号需要登录或重新授权', '请由部署者使用后台服务的同一系统用户登录 Codex，并检查登录状态。已采集内容会保留，尚未通过分析的新结果不会更新重置状态。'], en: ['Codex sign-in or reauthorization is required', 'Sign in to Codex as the same OS user that runs the service and check login status. Captured content is retained; unvalidated new results do not update reset states.'] },
  model_rate_limited: { zh: ['Codex 请求受到额度或频率限制', '请检查所用账号的可用额度和请求限制。模型任务会稍后重试，当前保留已核实数据。'], en: ['Codex requests are limited by usage or rate limits', 'Check the account’s available usage and request limits. Model tasks retry later; verified data remains visible.'] },
  model_timeout: { zh: ['Codex 分析超时', '正文采集与模型处理是独立步骤。此次模型处理未及时完成，任务会重试；这不表示 X 无法访问。'], en: ['Codex analysis timed out', 'Collection and model processing are separate stages. This model request did not finish in time and will retry; it does not establish an X connectivity failure.'] },
  model_unavailable: { zh: ['Codex CLI 暂不可用', '请检查服务器是否安装 Codex CLI，以及后台服务用户能否运行它。已采集正文和截图会保留。'], en: ['Codex CLI is unavailable', 'Check that Codex CLI is installed and executable by the service user. Captured text and screenshots are retained.'] },
  model_network: { zh: ['服务器暂时无法连接 Codex 模型服务', '请检查后台服务的出站网络和代理配置；能访问 X 不代表能访问模型服务。'], en: ['The server cannot reach the Codex model service', 'Check the service’s outbound network and proxy configuration. X connectivity does not establish model-service connectivity.'] },
  invalid_result_schema: { zh: ['Codex 返回结果未通过格式校验', '此次模型结果没有写入线上重置状态。正文和截图已保留，后续将重新处理。'], en: ['The Codex result failed schema validation', 'This model result was not applied to live reset states. Text and screenshots are retained for another processing attempt.'] },
  analysis_failed: { zh: ['Codex 分析或结果校验暂未完成', '采集与模型分析独立运行。当前保留已核实数据，请由部署者查看模型任务日志；未通过校验的结果不会改动重置状态。'], en: ['Codex analysis or result validation is incomplete', 'Collection and model analysis run separately. Verified data is retained. Check the model worker logs; unvalidated results do not change reset states.'] },
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
