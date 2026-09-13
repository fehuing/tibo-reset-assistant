# 用自己的 Codex 账号处理 Tibo 动态

适用于 **1.2.0 及之后包含 AI 管线的版本**。安装与认证说明核对日期：2026-09-13。本指南不需要在线示例站的私有接口、账号凭据或内部部署文件。

网页、API、SQLite 和归档运行在自己的机器上；Codex CLI 把分析请求发给云端模型，使用账号可用的权限和额度。默认 `npm start` 只运行历史示例；只有显式启用 `--ai` 或 `AI_ANALYSIS=1` 才启动模型任务。

## 1. 准备项目与截图环境

需要 Node.js 22.13+ 和 Python 3.10+。在项目目录执行：

```sh
python -m venv .venv
```

激活环境：Linux/macOS 使用 `source .venv/bin/activate`；Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1`。之后在这个环境中执行：

```sh
python -m pip install -r requirements-capture.txt
python -m playwright install chromium
```

Linux 若提示缺少浏览器系统库，按 Playwright 提示安装，或使用 `python -m playwright install --with-deps chromium`；安装系统库可能需要管理员权限。完成后仍由自己的普通运行用户启动项目。

截图保存 X 原页面，不经过网页自动翻译。公开入口的原文和截图可能分别失败：完整文字可以先进入分析队列，截图之后重试。

## 2. 安装官方 Codex CLI

Linux/macOS 可使用官方安装方式：

```sh
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex --version
```

Windows 或其他安装方式见 [官方 Codex CLI 安装文档](https://learn.chatgpt.com/docs/codex/cli)。若 `codex` 不在 `PATH` 中，将 `.env` 的 `CODEX_EXECUTABLE` 改为自己机器上可执行文件的路径。该值是可执行文件路径，不是附带参数的 shell 命令。

## 3. 用运行后台的同一个系统用户登录

有浏览器的本机：

```sh
codex login
```

远程服务器或无桌面环境：

```sh
codex login --device-auth
```

设备码方式需要先在 **ChatGPT 网页的设置 → 安全** 中开启设备代码登录；组织账号可能还需要管理员允许。按终端给出的官方链接，在自己的浏览器登录并输入一次性代码。以终端显示完成授权为准，单独登录浏览器账号不代表 CLI 已获授权。参见 [官方认证文档](https://learn.chatgpt.com/docs/auth)。

检查：

```sh
codex login status
```

账号登录模式应显示使用 ChatGPT 登录。这个命令检查认证状态，不验证某个模型的可用性或剩余额度。

**登录用户和后台运行用户必须一致。** 不要先用管理员 / root 登录，再让另一用户启动后台。Codex 使用当前用户的私有登录缓存；若配置了 `CODEX_HOME`，登录和运行进程必须使用同一个目录。不要把登录缓存、`auth.json`、一次性代码或账号页面提交 GitHub。

`codex exec` 可以复用 CLI 认证。ChatGPT 登录和 API key 是不同认证方式；API key 使用相应 API 计费。官方对一般自动化建议优先使用 API key。本指南的个人 Codex 账号方式适用于自己的可信私有运行环境，不提供让公众提交任意提示词或执行命令的入口。参见 [官方非交互模式说明](https://learn.chatgpt.com/docs/non-interactive-mode)。

## 4. 配置并启动 AI 模式

将 `.env.example` 复制为 `.env`，按自己的环境修改：

```dotenv
CODEX_EXECUTABLE=codex
CODEX_MODEL=gpt-6-astra
AI_ANALYSIS=0
AI_MAX_JOBS=3
AI_TIMEOUT_SECONDS=150
AI_BUDGET_SECONDS=240
```

这里的模型是项目默认值，**需要自己账号有相应权限**；有其他兼容模型时可改 `CODEX_MODEL`。模型选择变化可能影响分析结果，应检查实际返回是否符合项目 Schema。并非所有账号都能使用同一模型。

在已激活 Python 环境、已登录 Codex 的终端中运行：

```sh
npm start -- --ai
```

`--ai` 自动打开实时采集和原页面截图，不必再附加 `--live --capture`。之后打开 http://localhost:8080/。若希望启动器每次默认使用 AI，可在 `.env` 设置 `AI_ANALYSIS=1`；恢复示例模式时设回 `0`，并关闭 `LIVE_COLLECTION` 与相关采集选项。

每轮模型请求按顺序执行，默认最多处理 3 条；单条超时 150 秒，每次运行预算 240 秒。这些是项目配置，不是模型响应时间或费用保证。首轮可能有待分析的已采集正文，后续相同输入和角色 / Schema 指纹复用已有结果；失败会按退避策略重试。

启动器不会替你完成登录。找不到 CLI、模型无权限、额度不足、网络不可达或结果校验失败时，应按错误排查；AI 模式不会悄悄切回旧规则来更新重置状态。

## 5. 确认网络作用于实际进程

需要运行项目的机器能访问 X 公开入口和 Codex 服务。电脑浏览器能访问不代表服务器、后台服务或容器能访问。

- Python HTTP 采集和 Codex 子进程使用实际运行环境中的 `HTTP_PROXY` / `HTTPS_PROXY` 等配置。
- Playwright 浏览器代理通过 `CAPTURE_PROXY` 单独配置，可使用 `http://`、`https://` 或 `socks5://` 地址；仅有 `HTTPS_PROXY` 不保证截图可访问。代理 URL 不能内嵌用户名密码，需认证时单独使用 `CAPTURE_PROXY_USERNAME`、`CAPTURE_PROXY_PASSWORD`。
- 后台服务需要显式继承自己的网络配置；不要假定交互终端中的设置会自动进入 systemd、计划任务或 Docker。
- 保持 TLS 证书校验开启；代理凭据只存私有配置，不上传仓库。

没有代理也可能正常访问；配置代理也不能保证绕过 X 的登录要求、限流或公开内容缺失。具体错误见 [部署排查表](DEPLOYMENT.md#采集失败提示与排查)。

## 6. 看什么算运行成功

打开 `/api/collection-status`，区分 X 采集状态与 `stages.analysis` 的分析状态；返回 HTTP 200 只说明自己的服务正常返回，不能代替采集成功。新发布的数据在 `/data.json`，X 覆盖情况见 `source.coverage`。

模型队列保存在私有 `.data/ai-analysis/state.json`，包括每条任务的 `state`、`error_code` 和重试时间。输入副本在 `.data/ai-input/`，有效结果在 `.data/ai-analysis/` 下。排查时可看状态和安全错误码，不需要输出账号认证文件。

| 错误码 / 状态 | 处理方法 |
| --- | --- |
| `model_unavailable` | 检查 `CODEX_EXECUTABLE` 和后台进程的 `PATH` |
| `model_auth_required` | 用后台同一用户执行 `codex login status`，确有失效再重新授权 |
| `model_rate_limited` | 检查账号额度 / 限制，等待重试，减少单轮任务量 |
| `model_timeout` | 检查模型进程网络和服务可用性，结合实际需求调整超时 |
| `model_network` | 检查模型进程实际继承的网络 / 代理配置 |
| `model_request_failed` | 检查模型名称、账号权限和网络；保留旧数据后重试 |
| `pending_content` | 正文或必要上下文尚不完整，先排查采集阶段 |
| `invalid_result_schema`、`evidence_not_in_source` | 输出未通过校验，不能发布；检查模型兼容性与原始内容 |

普通动态成功分析后只归档与翻译，**没有新增重置公告也是正常结果**。公开页面可能遗漏最新帖和回复，不应由某次无更新得出“没有新公告”。

## 管线如何判断并更新

```text
公开 X 入口 → 正文 / 上下文 / 原页面截图归档
                     ↓
                 白名单输入
                     ↓
         Codex CLI：翻译、摘要、语义分析
                     ↓
          Schema + 来源哈希 + 原文依据校验
                     ↓
       公告列表 / 观察窗口 / 已确认事件投影
```

模型角色在 [`ops/ai_role.md`](../ops/ai_role.md)，字段结构在 [`ops/ai_analysis.schema.json`](../ops/ai_analysis.schema.json)。它返回完整中文翻译、双语摘要、相关性、信号、范围、重置类型、原文依据、明确关联和有依据的时间 / 定性预测，不直接写网站数据。

调用由 [`ops/ai_analysis.py`](../ops/ai_analysis.py) 管理：使用 `codex exec`、只读沙箱、临时会话与工具限制，`--output-schema` 约束最终结构，`-o` 保存最终 JSON。`--json` 是执行过程 JSONL 日志，不是业务结果文件。项目不会把账号登录 token 当作普通 HTTP API key。

发布逻辑由 [`ops/ai_publication.py`](../ops/ai_publication.py) 执行：无关或个人事件不改变全局重置；线索 / 预告开启观察；确认或明确取消后关闭。时间过去、模型预测和网友投票都不能单独证明发放。公开文字有明确完成声明时可作为公开事件依据，但实际到账时间仍需可靠来源，不把公告发布时间自动替代实际时间。

## 从旧版升级

先停止服务并备份整个 `.data/`（尤其 SQLite），拉取新代码、重新构建，再安装本指南中的额外依赖。旧实例数据不会被新版示例快照自动覆盖；如果想单独查看新快照，使用新的 `DATA_DIR` 启动一个独立实例，避免清空自己的历史与投票。

旧 `--live` 规则模式仍可显式运行，旧翻译服务配置只供旧模式使用。新 AI 模式不需要配置 `translation.json`，保留旧记录已归档的翻译与 X 原始截图。

本指南推荐直接在宿主机使用 Codex CLI。默认 Docker 和旧截图镜像不包含已配置的 Codex 账号环境，本版本不提供已经验证的 Docker AI 一键部署承诺。
