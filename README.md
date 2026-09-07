# Tibo重置助手 / Tibo Reset Assistant

一个可以自行部署的 Codex 重置公告追踪网站。支持中英文切换、深色模式、重置日历、公告状态、原文截图、中文阅读、分享链接和社区投票。

[在线示例](https://codex-reset.top/) · [更新日志](CHANGELOG.md) · [部署与数据说明](docs/DEPLOYMENT.md)

![页面风格](public/share-cover.jpg)

## 下载后启动

需要 **Node.js 22.13+（自带 npm）和 Python 3.10+**。首次启动联网安装锁定的依赖并构建页面；之后运行网页和本地 API 不需要第三方账号、密钥或在线示例的接口。

```sh
git clone https://github.com/fehuing/tibo-reset-assistant.git
cd tibo-reset-assistant
npm start
```

打开 **http://localhost:8080/**。按 Ctrl+C 停止。

也可以运行 `python run.py`（Linux/macOS 使用 `python3 run.py`）。已有构建时用 `npm start -- --no-build` 跳过安装和构建。

**Docker 一条命令：** 安装 Docker Compose 后，在仓库目录运行：

```sh
docker compose up --build -d
```

同样打开 http://localhost:8080/。数据保存在 `tibo-data` volume；普通重启和更新不会清空计数。默认仅绑定本机地址。

## 默认数据与实时采集

默认展示仓库内的 **2026-09-07 历史快照**，页面会明确标注。包含 52 条公告记录，以及对应的原图和缩略图；保留原始采集时间。**它不是当前实时结果。** 互动计数从当前实例的 0 开始，不导入在线站点的用户投票。

启用实时采集：

```sh
npm start -- --live
```

每轮尝试读取 Tibo 的公开 X 页面和回复，完成后至少等待 120 秒。X 页面可能要求登录、限制访问或改变结构，**不保证实时性或完整覆盖**；失败保留旧数据，不把缓存时间冒充成功采集时间。无需 API Key 的公开页面采集只是目前提供的一种适配器，可以在 `ops/collector.py`、`ops/reset_watch.py` 中替换为自己有权限使用的数据源。

参考站公开接口回退默认关闭。需要时设置 `ALLOW_REFERENCE_FALLBACK=1`。重置观察的参考链接发现是独立选项，见部署文档；不会引入参考站概率或投票数。

## 功能

- 中文 / English 一键切换，浅色 / 深色模式，手机宽度适配。
- 公告分为预告、已宣布发放和待确认；统计与日历只按已宣布事件去重计算。
- “重置观察”展示经过来源核对的暗示和回复上下文，投票独立于公告统计。
- 观察窗为原帖发布后 24 小时，这是站点规则，不是官方发放承诺。比例只是本实例用户的投票比例。
- 原文全文、哈希绑定的中文翻译、截图缩略图与原图预览。
- SQLite 持久化“求重置”计数和观察投票，带重复请求去重、来源检查和基本限流。

不读取任何人的 Codex 账户额度；“已宣布发放”只表示公开文字有明确宣布，不能证明某个账户已经到账。规则分类不调用大模型；可选翻译服务仅处理正文，不改变状态判定。

## 截图和翻译（可选）

快照截图已包含在仓库中。**采集未来的新截图**需要额外安装浏览器依赖，在与启动脚本相同的 Python 环境中执行：

```sh
python -m pip install -r requirements-capture.txt
python -m playwright install chromium
npm start -- --live --capture
```

Linux 可使用 `python3 -m playwright install --with-deps chromium` 安装系统库。默认 Docker 镜像提供网页、API 和文字采集；不包含 Chromium。完整截图镜像见 [Docker 截图配置](docs/DEPLOYMENT.md#docker-截图镜像)。

新正文的自动翻译需要你自己配置翻译服务，可能产生该服务的费用。将 `docs/translation.example.json` 复制到 `.data/translation.json`，填写自己的配置后执行 `npm start -- --live --capture --translate`。未配置时不发起付费请求，仍可阅读英文全文和快照中已有翻译。

## 定制与开发

- 复制 `.env.example` 为 `.env` 配置端口、站点地址和采集选项；修改构建参数后重新运行 `npm start`。
- `lib/site-config.ts`：可选小程序码、联系二维码和名称。默认不显示；请放入自己的素材。
- `public/tibo-avatar.jpg`、`public/tibo-favicon.png`：头像和标签页图标。
- `app/globals.css`：页面样式；`lib/i18n.ts`：中英文文案。
- `app/page.tsx`、`components/`：页面与组件；`ops/`：完整网页后端和采集逻辑。
- `.data/`：运行数据、SQLite 数据库和私有配置，不提交 Git。

```sh
npm ci
npm test
npm run typecheck
npm run build
python scripts/smoke.py
```

热更新开发：先运行 `npm start -- --no-build` 保持本地 API，然后在另一个终端运行 `npm run dev`，访问 http://localhost:4175/radar/。开发服务器将数据、截图和投票请求转发到本机 8080 端口。

依赖通过 `package-lock.json` 和 `requirements-capture.txt` 锁定，脚本自动安装；不上传体积大且与操作系统相关的 `node_modules`、虚拟环境和浏览器二进制文件。

这是**网页版开源仓库**，包含网页和独立运行所需的后端。微信小程序、线上服务器凭据、运行数据库、个人二维码和内部部署记录不在此仓库中。

## English quick start

Install Node.js 22.13+ and Python 3.10+, clone this repository, then run `npm start`. The launcher installs locked npm dependencies, builds the web app and starts the local Python/SQLite API at http://localhost:8080/. Alternatively, run `docker compose up --build -d`.

The default mode uses an explicitly labelled historical snapshot. Counters belong to your own instance and start at zero. `npm start -- --live` enables best-effort public X collection. New screenshots require the optional Python packages and Chromium; new translations require your own configured provider. X access can fail or omit replies. No personal Codex balance is read, and a forecast/hint is never proof of delivery.

## 许可与致谢

本项目代码采用 [MIT License](LICENSE)。公开推文、截图、头像和第三方标识不纳入本项目的 MIT 授权，权利属于其原权利人，详见 [NOTICE](NOTICE.md)。页面风格参考 [Codex Resets](https://codex-resets.com/)。本项目不是 OpenAI、X 或 Tibo 的官方产品。
