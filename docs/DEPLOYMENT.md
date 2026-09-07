# 部署和维护

## 运行模型

```text
浏览器 → 本实例的 Python HTTP 服务 → 静态页面 / SQLite / .data
                                 ↑
                     可选 X 采集、截图、翻译
```

Node.js 只用于安装、构建和前端开发；正式服务由 Python 提供。默认使用标准库 SQLite，不需要 Redis、MySQL 或在线示例站的 API。前端请求与当前站点同源，`/` 和 `/radar/` 两个路径都可访问。

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

上线自己的域名时填写 `PUBLIC_SITE_URL` 和 `ALLOWED_ORIGINS`，重新构建。Python 端口放在提供 HTTPS 的反向代理后面，公共请求在代理处限流。服务本身不信任请求中的 `X-Real-IP`，代理后的请求会共享服务端限额；有较大访问量时请在可信代理层按客户端限流并调整服务方案。该轻量服务适合单实例，不提供多节点共享数据库或管理员后台。

Docker 映射端口由 `PORT` 控制，但容器内仍是 8080。改为宿主机 9000 时，同步配置 `ALLOWED_ORIGINS=http://localhost:9000` 和 `PUBLIC_SITE_URL=http://localhost:9000`。需要直接对外监听时显式设置 `BIND_ADDRESS=0.0.0.0`；有同机反向代理时保持默认回环绑定。

## 数据来源与失败处理

`ops/collector.py` 解析公开页面中可见的结构化数据；`ops/reset_watch.py` 对回复独立核对作者和上下文。没有登录 cookie、付费 X API Key 或绕过访问限制的代码。公开页面没有提供目标内容时会失败并保留旧结果，界面根据最后成功时间提示延迟。

公告判定在 `ops/announcement_semantics.py` 中按规则执行；翻译不会改变状态。隐喻、否定、将来时和已经宣布发放分别处理，但自然语言规则不可能覆盖所有措辞。它们不能查询某个用户的实际到账情况。

可选 `.data/watch-config.json`：

```json
{
  "source_urls": [],
  "reference_discovery": false
}
```

`source_urls` 可放入你已知的 Tibo 原帖链接。`reference_discovery=true` 只从参考站取候选链接，仍需独立核对原帖；不复制其预测、投票数或截止时间。

截图通过 Playwright 访问公开原帖页面，只在采集成功后生成原图和缩略图。首次运行浏览器如果缺少系统库，会显示处理失败；安装 Chromium 和系统依赖后重试即可。翻译使用 `docs/translation.example.json` 中的 HTTPS 兼容接口配置，密钥仅保存在 `.data/translation.json`。

## Docker 截图镜像

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

# 单次采集；先正常启动一次以初始化 .data
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
| `disabled` | 未启用实时采集 | 需要更新时设置 `LIVE_COLLECTION=1` 或启动加 `--live` |
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
| 顶层 `stale` | 采集进程长时间未报告状态 | 检查采集进程是否停止或卡住 |

`stages.feed` 与 `stages.watch` 分别记录公告和回复观察，包含 `state`、`code`、可选 `http_status`、`checked_at` 和 `last_success_at`。成功时间指**本次服务启动后**成功读取相应来源的时间；实例重启后会重新验证。回退数据取回成功时，公告状态仍为 `degraded`，保留 X 的错误原因。请求失败不会把 `data.json.checked_at` 改成当前时间，也不会清空历史记录或假装“没有新公告”。

状态接口是只读接口，刷新不会强制请求 X，避免公共访问触发大量外部采集。自动重试每轮完成后至少等待 120 秒；等待过久会提示任务未更新。公开状态不包含异常全文、服务器文件路径、代理地址、账号或密钥。

如果部署环境有自己的 HTTP/HTTPS 出站代理，Python 的 HTTP 抓取可使用 `HTTPS_PROXY` / `HTTP_PROXY` 环境变量。它们需要配置在**实际运行服务的环境**里；Docker 容器里的 `127.0.0.1` 指向容器自身，不是宿主机。默认 Compose 不传递这些私有设置，如有需要在自己的 Compose override 中配置。Playwright 浏览器网络需要单独设置其代理；仅设置 Python 的 HTTP 代理不保证浏览器子资源也能访问。请不要把含有账号密码的代理 URL 提交 GitHub。

## 联系方式与自愿支持配置

`lib/site-config.ts` 中的小程序码和微信码是项目原作者已授权公开的素材。可以替换成自己的图片路径，或设置为空字符串隐藏。抖音设置 `douyin.name`、`douyin.url` 和/或 `douyin.qrCode`；未配置的项目不显示。

自愿支持需要同时设置 `support.enabled=true`、`support.recipient`（公开展示的收款方名称），并提供 `support.wechatPayCode` 或 `support.alipayCode`。收款图放入 `public/` 后填写 `/radar/文件名.png`，再重新构建。未配置完整时不显示打赏入口。联系二维码不会自动用作支付二维码。

弹窗明确自愿、金额自选、免费使用不受影响。它仅展示收款码，不发起或验证交易，不存储支付信息，也不显示虚构的收款金额或付款成功提示。

## 公共 API

| 路径 | 方法 | 用途 |
| --- | --- | --- |
| `/health` | GET | 服务存活检查，不代表 X 采集成功 |
| `/data.json` | GET | 公告、原文、截图清单、事件统计和采集时间 |
| `/api/collection-status` | GET | 本实例的采集开关、公告/回复状态与安全错误码 |
| `/api/reactions` | GET / POST | 当前公告的本实例求重置计数 |
| `/api/watch` | GET / POST | 当前观察窗和本实例投票 |
| `/post-images/{id}-{hash}.jpg` | GET | 本地截图或缩略图 |

上述数据/API/图片路径支持 `/radar` 前缀。POST 必须为 JSON。求重置参数为 `request_id`（8–64 位字母数字、下划线或短横线）、`n`（1–10）；观察投票参数为 `episode_id`、`voter_id`（16–64 位）和 `vote`（`yes` / `no`）。过期、来源检查陈旧或已出现新公告的观察窗返回 409。匿名浏览器标识只用于去重，不等同于实名用户身份。
