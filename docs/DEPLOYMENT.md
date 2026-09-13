# 部署和维护

## 运行模型

```text
浏览器 → 本实例的 Python HTTP 服务 → 静态页面 / SQLite / .data
                                 ↑
                X 采集 / 原图 → 可选 Codex 分析 → 校验发布
```

Node.js 只用于安装、构建和前端开发；正式服务由 Python 提供。默认使用标准库 SQLite，不需要 Redis、MySQL 或在线示例站的 API。前端请求与当前站点同源，`/` 和 `/radar/` 两个路径都可访问。

默认 `npm start` 使用历史快照，不调用 X 或模型。`npm start -- --ai` 启用新版公开动态采集、截图和 Codex 分析；`npm start -- --live` 保留旧规则模式。AI 需要在运行机器安装截图依赖、Chromium、官方 Codex CLI 并完成同用户登录，步骤见 [Codex 接入指南](CODEX-SETUP.md)。网页与存储自行部署，模型请求通过云端处理。

首次启动将 `sample-data/` 中的历史快照复制到 `.data/`，已有文件不覆盖。快照保留原采集时间，陈旧观察窗不接受投票。数据库首次初始化从 0 计数。定期备份整个 `.data/`；操作 SQLite 文件时先停止服务。

## 配置

`.env` 由启动脚本读取，不执行其中任何 shell 内容；已有系统环境变量优先。

| 参数 | 默认 | 用途 |
| --- | --- | --- |
| `HOST` / `PORT` | `127.0.0.1` / `8080` | 本地服务监听 |
| `DATA_DIR` | `.data` | 数据与私有配置目录 |
| `PUBLIC_SITE_URL` | `http://localhost:8080` | 构建时的分享元数据域名 |
| `ALLOWED_ORIGINS` | localhost 地址 | 允许提交互动的页面来源，逗号分隔，包含协议和端口 |
| `LIVE_COLLECTION` | `0` | 是否持续采集公开 X 页面 |
| `POLL_SECONDS` | `120` | 每轮处理后等待时长，最小 120 秒 |
| `ALLOW_REFERENCE_FALLBACK` | `0` | 允许参考站公告接口回退 |
| `CAPTURE_POSTS` | `0` | 采集新正文和截图，需要截图依赖及实时模式 |
| `TRANSLATE_POSTS` | `0` | 翻译新正文，需要私有配置及实时模式 |
| `AI_ANALYSIS` | `0` | 启用 Codex 分析，同时启用实时采集与原图归档 |
| `CODEX_EXECUTABLE` | `codex` | CLI 可执行文件名或路径，不是 shell 命令 |
| `CODEX_MODEL` | `gpt-6-astra` | 分析模型，需自己的账号具有访问权限 |
| `AI_MAX_JOBS` | `3` | 每次最多顺序处理的模型任务数 |
| `AI_TIMEOUT_SECONDS` | `150` | 单条模型请求的超时秒数 |
| `AI_BUDGET_SECONDS` | `240` | 每次模型处理的总时间预算秒数 |
| `CAPTURE_PROXY` | 空 | Playwright 的显式代理地址，按自己的网络配置 |
| `CAPTURE_PROXY_USERNAME` / `CAPTURE_PROXY_PASSWORD` | 空 | 可选浏览器代理认证，不提交仓库 |

命令行 `--ai` 可以直接打开 AI 模式，无需再附加 `--live --capture`。AI 模式不运行旧浏览器翻译或旧语义分类流程；同时设置 `TRANSLATE_POSTS=1` / `--translate` 会被拒绝，需要先关闭旧翻译选项。调整任务数量会影响本轮可能发起的请求数，不代表费用或处理速度保证。

上线自己的域名时填写 `PUBLIC_SITE_URL` 和 `ALLOWED_ORIGINS`，重新构建。Python 端口放在提供 HTTPS 的反向代理后面，公共请求在代理处限流。服务本身不信任请求中的 `X-Real-IP`，代理后的请求会共享服务端限额；有较大访问量时请在可信代理层按客户端限流并调整服务方案。该轻量服务适合单实例，不提供多节点共享数据库或管理员后台。

Docker 映射端口由 `PORT` 控制，但容器内仍是 8080。改为宿主机 9000 时，同步配置 `ALLOWED_ORIGINS=http://localhost:9000` 和 `PUBLIC_SITE_URL=http://localhost:9000`。需要直接对外监听时显式设置 `BIND_ADDRESS=0.0.0.0`；有同机反向代理时保持默认回环绑定。

## 数据来源与失败处理

**AI 模式：** `ops/activity_ingest.py` 从公开主页、回复、媒体页及配置的直接原帖链接发现可核对作者的内容，不先按重置关键词筛掉普通动态。`ops/capture_posts.py` 保存完整正文、上下文、X 原页面截图及各阶段时间。公开页面没有提供的回复、转发或分页内容无法凭空获取；覆盖状态为 `ok`、`partial` 或 `unavailable`，不能承诺完整实时采集。

`ops/ai_input.py` 准备公开内容白名单输入；`ops/ai_analysis.py` 用 Codex CLI 生成翻译、摘要、相关性、信号、范围和原文依据。`ops/ai_publication.py` 检查结构、ID、哈希和证据后更新公开数据。普通动态只归档和翻译；个人周期或手动重置卡不计入全局事件。模型失败、无权限或结果无依据时保留旧数据并重试，**不自动调用旧规则替代分析结果**。

**旧 `--live` 模式：** `ops/collector.py` 解析公开结构化内容，`ops/reset_watch.py` 核对回复作者和上下文，`ops/announcement_semantics.py` 执行旧规则。旧翻译不改变状态。此模式保留供显式选择，与 AI 模式的语义分析不同。

两种模式都不读取网站访问者的 Codex 额度，没有要求配置 X 登录 cookie 或付费 X API Key。公开文本的完成声明可以成为事件依据，不等于测量了每个账户的实际到账情况。失败不会清空已有历史，也不会把发布时间冒充本次来源读取成功时间。

可选 `.data/watch-config.json`：

```json
{
  "source_urls": [],
  "reference_discovery": false
}
```

`source_urls` 可放入你已知的 Tibo 原帖链接，仍需采集和核对作者。旧规则模式的 `reference_discovery=true` 只从参考站取候选链接，不复制其预测、投票数或截止时间。`ALLOW_REFERENCE_FALLBACK=1` 是旧规则模式的可选参考接口回退；默认关闭。AI 模式按独立采集的公开原文分析，不使用参考站分类替代模型结果。

截图通过 Playwright 访问公开原帖页面，只在采集成功后生成原图和缩略图。正文与截图保留各自成功时间，图片失败可独立重试。首次运行缺少 Chromium 或系统库时，安装后重试即可。AI 模式保留 X 原始截图，不做网页翻译；旧模式的可选翻译仍使用 `docs/translation.example.json`，自己的密钥仅保存到 `.data/translation.json`。

新公告使用独立展示列表，默认三条、可展开全文和原图；后台保留事件与关联数据。新的观察窗使用 `until_reset_confirmed`，确认或明确取消后关闭，不再仅因发布满 24 小时结束；旧快照中的固定窗口仍按旧规则兼容。来源陈旧时暂停投票，时间流逝、模型预测和投票比例都不算已完成证据。日历保留最近 26 周北京时间布局，已核实的历史与实际时间不会因重读旧预告被降级。

## 运行数据与升级

`.data/` 存放本实例数据与 SQLite。AI 输入位于 `.data/ai-input/`，分析队列与结果位于 `.data/ai-analysis/`，每条任务记录处理状态、安全错误码和重试时间。采集归档保留公开帖 ID、正文 / 上下文、发布时间、首次采集、最近看见、正文成功和截图成功等时间；这几种时间用途不同。

升级前停止服务、备份 `.data/`，再更新代码和构建。首次启动才从仓库快照补齐缺少的初始文件，**不会将新快照覆盖到已有实例历史上**。希望查看新版快照时可另设新的 `DATA_DIR`，保留原实例用于恢复。运行数据库、AI 输入 / 结果、账号登录缓存与私有配置不属于公开仓库内容。

## Docker 截图镜像

默认 Docker 提供示例网页和 API；本节是旧规则采集的截图镜像，不是已经配置 Codex 账号的 AI 镜像。AI 模式推荐先按照 [宿主机 CLI 接入](CODEX-SETUP.md) 运行，本版本不宣称 Docker AI 已验证。

需要实时采集新截图时使用单独的浏览器镜像：

```sh
docker build -f Dockerfile.capture -t tibo-reset-capture .
docker run --init --rm -p 127.0.0.1:8080:8080 -v tibo-capture-data:/app/.data tibo-reset-capture
```

镜像以非 root 用户运行，并保留 Chromium sandbox。容器宿主必须允许非特权用户命名空间；受限制的内核或 seccomp 配置可能阻止 Chromium sandbox。请按 Playwright 的容器部署文档配置宿主，而不要把运行参数改成 `--privileged`。默认轻量镜像的网页和 API 不依赖浏览器。

## 常用命令

```sh
# 安装 / 构建 / 校验
npm ci
npm run typecheck
npm test
npm run build
python scripts/smoke.py

# 保持构建，重新启动
npm start -- --no-build

# 完成 Codex 同用户登录和截图依赖安装后使用新版管线
npm start -- --ai

# 以下为旧规则模式的单次调试；不要与正在运行的 AI 发布进程混用
# 先正常启动一次以初始化 .data
python ops/collector.py --output .data/data.json --cache .data/source-cache.json
python ops/reset_watch.py --state .data
python ops/capture_posts.py --state .data --limit 3
python ops/translate_posts.py --state .data --config .data/translation.json
```

## 采集失败提示与排查

**能打开本项目网页，不代表部署服务器能访问 X。** 采集发生在服务器进程里；个人电脑或手机上的网络设置不会自动作用于云服务器或 Docker 容器。

前端会在页面上方显示具体情况。`/data.json` 同时附带 `collection_status`，也可独立读取 `/api/collection-status`。HTTP 200 只表示本实例成功返回数据，不代表 X 采集成功；请检查状态字段。

| 状态或错误码 | 含义 | 部署者检查项 |
| --- | --- | --- |
| `disabled` | 未启用实时采集 | 新版使用 `--ai`；旧模式设置 `LIVE_COLLECTION=1` 或加 `--live` |
| `checking` | 首次采集尚未完成 | 等待本轮检查 |
| `x_dns` | 无法解析 x.com | 服务器 / 容器 DNS |
| `x_timeout` | 连接或读取超时 | 服务器出站网络、防火墙、代理可达性 |
| `x_network` | 网络连接失败 | 出站网络、路由、代理；不等同于确定“没有梯子” |
| `x_tls` | 证书或安全连接失败 | 系统时间、证书和代理，保持证书验证开启 |
| `x_access_denied` | HTTP 401/403 | X 登录要求或访问策略；有网络也不一定可采集 |
| `x_rate_limited` | HTTP 429 | 等待自动重试，减少请求频率 |
| `x_unavailable` | HTTP 404/410 | 目标页面当前不可读，不据此断定账号已删除 |
| `x_http` | 其他异常 HTTP 响应 | 记录响应状态并等待恢复 |
| `x_parse` | 已读页面但无法识别目标内容 | 页面结构改变、登录页、公开内容缺失，更新适配器 |
| `collector_error` | 其他处理失败 | 部署配置、数据目录权限和程序日志 |
| `model_auth_required` | CLI 需要认证 | 用后台同一用户检查 `codex login status`，失效时重新登录 |
| `model_rate_limited` | 模型额度或频率限制 | 检查账号额度，等待自动重试，降低任务量 |
| `model_timeout` | 模型请求超时 | 检查后台进程网络和服务可用性 |
| `model_network` | 模型网络连接失败 | 检查模型进程实际继承的网络 / 代理配置 |
| `model_unavailable` | Codex CLI 不可调用 | 检查可执行文件路径和服务的 `PATH` |
| `model_request_failed` | 模型请求失败 | 检查模型名称、账号权限与网络 |
| `invalid_result_schema` / `evidence_not_in_source` | 模型结果未通过校验 | 检查来源内容与模型兼容性，不绕过校验发布 |
| 顶层 `stale` | 采集进程长时间未报告状态 | 检查采集进程是否停止或卡住 |

`stages.feed` 与 `stages.watch` 记录采集阶段，AI 模式另有 `stages.analysis`。状态包含 `state`、`code`、可选 `http_status`、`checked_at` 和 `last_success_at`。HTTP 服务存活、X 读取成功和模型分析成功需要分别看。旧模式中参考回退成功仍为 `degraded`，保留 X 的错误原因；AI 模式的 `data.json.source.coverage` 记录真实 X 扫描覆盖，与发布输出时间分开。不要仅凭 `data.json` 的更新时间判断 X 刚刚读取成功。

状态接口是只读接口，刷新不会强制请求 X 或 Codex。采集每轮完成后至少等待 120 秒；模型失败按队列退避重试，详见私有 `.data/ai-analysis/state.json`。等待过久会提示任务未更新。公开状态不包含异常全文、服务器文件路径、代理地址、账号或密钥。

如果部署环境有自己的 HTTP/HTTPS 出站代理，Python HTTP 抓取和 Codex 子进程可使用 `HTTPS_PROXY` / `HTTP_PROXY` 环境变量。它们需要配置在**实际运行服务的环境**里。Playwright 浏览器单独使用 `CAPTURE_PROXY`，支持 `http://`、`https://`、`socks5://`，URL 中不能内嵌用户名密码；认证需单独使用 `CAPTURE_PROXY_USERNAME` / `CAPTURE_PROXY_PASSWORD`。仅设置 HTTP 环境代理不保证截图可访问。Docker 容器里的 `127.0.0.1` 指向容器自身；默认 Compose 不传递这些私有设置，有需要时自行配置 override。代理凭据不要提交 GitHub。

## 仓库联系方式

作者的小程序码、微信联系码、公众号 aicodexxx、抖音链接和二维码统一放在仓库 README，素材目录为 `docs/assets/`。这些素材不会复制到网站静态输出中，网站默认不展示作者联系区域。

部署者如需添加自己的小程序码或联系码，可使用原有的 `lib/site-config.ts` 可选配置，图片放入 `public/` 后填写 `/radar/文件名.png` 并重新构建。默认配置留空。

自愿支持说明目前只在 README 中展示，未开放打赏、未上传收款码，也没有网页支付入口。

## 公共 API

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `/health` | GET | 服务存活检查，不代表 X 采集成功 |
| `/data.json` | GET | 公告列表、原文、截图清单、事件统计、采集时间和来源覆盖 |
| `/api/collection-status` | GET | 本实例的采集开关、采集 / 模型阶段状态与安全错误码 |
| `/api/reactions` | GET / POST | 当前公告的本实例求重置计数 |
| `/api/watch` | GET / POST | 当前观察窗和本实例投票 |
| `/post-images/{id}-{hash}.jpg` | GET | 本地截图或缩略图 |

上述数据/API/图片路径支持 `/radar` 前缀。POST 必须为 JSON。求重置参数为 `request_id`（8–64 位字母数字、下划线或短横线）、`n`（1–10）；观察投票参数为 `episode_id`、`voter_id`（16–64 位）和 `vote`（`yes` / `no`）。已结束、来源检查陈旧或不再匹配当前观察的投票返回 409；旧固定窗口仍有过期校验。匿名浏览器标识只用于去重，不等同于实名用户身份。公共 API 不提供任意提示词提交、CLI 执行或账号凭据读取功能。
