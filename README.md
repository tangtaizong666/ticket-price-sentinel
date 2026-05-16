# 票价哨兵

票价哨兵是一个本地运行的机票监控工作台。它可以搜索携程国内单程机票，保存目标价监控任务，并在价格达到目标时通过本机提醒、页面高亮和声音提示把你叫回来。

它适合这些场景：

- 想长期盯一条航线的低价机票
- 不想每天重复手动搜索
- 希望数据和登录状态保存在自己电脑上
- 想先用本地工具，不接入外部账号或消息服务

## 普通用户路径

你可以直接从 GitHub 项目页下载源码：

1. 点击 `Code → Download ZIP`。
2. 解压下载到的 zip。
3. 双击根目录里的 `start_fly_ticket.bat`。

首次运行会联网下载内置 Python、安装运行依赖和 Playwright Chromium，不需要提前安装 Python。之后再次双击会复用本地 `runtime/` 和 `.env`，启动会更快。

也可以从 GitHub Release 下载已经打包好的便携版：

`FlyTicket-Windows-<version>.zip`

解压后双击：

`启动机票监控.bat`

Release 发布包自带 Python 运行环境、依赖和 Playwright Chromium。普通用户不需要手动安装 Python、pip 依赖或浏览器组件。压缩包体积较大是因为内置了这些运行环境。

启动后按这个顺序使用：

1. 在首页查看“登录状态”。
2. 点击“去登录”或“重新登录”，在携程页面完成登录。
3. 回到本地页面，先做一次快速搜索。
4. 设置目标价和检查间隔，保存一个监控任务。
5. 保持启动窗口运行，后台会按间隔定时检查。
6. 如果价格命中目标价，页面会显示命中记录，并尽量弹出本机提醒。

## 首页能看什么

首页是清爽仪表盘，优先展示：

- 登录状态
- 监控状态
- 最近命中
- 快速搜索
- 创建监控任务
- 搜索结果
- 监控列表和命中详情

如果你是第一次使用，先完成登录，再创建监控任务。

## 搜索和监控说明

当前版本优先支持：

- 国内单程
- 固定出发日期
- 目标价监控
- 本机长期运行

搜索字段可以使用携程风格的城市/机场代码，例如：

- `bjs` = 北京
- `sha` = 上海
- `can` = 广州
- `szx` = 深圳
- `ctu` = 成都
- `ckg` = 重庆

示例：

- 出发地：`bjs`
- 到达地：`sha`
- 日期：`2026-05-20`

> 这一版优先保证真实搜索链路稳定，因此城市代码通常比中文城市名更稳。

## 提醒规则

当最低价小于或等于目标价时，系统会记录一条命中结果。

为了避免刷屏，提醒不会在短时间内无限重复。默认规则是：

- 第一次命中会提醒
- 如果价格继续下降，会再次提醒
- 如果价格一直命中但没有更低，会在冷却时间后再次提醒

默认开启重复提醒冷却，冷却时间是 6 小时，可通过 `.env` 调整：

```env
MONITOR_REALERT_COOLDOWN_ENABLED=1
MONITOR_REALERT_COOLDOWN_HOURS=6
```

如果希望每次检查到目标价都提醒，把冷却开关关掉：

```env
MONITOR_REALERT_COOLDOWN_ENABLED=0
```

关闭后，重复提醒频率会跟监控任务的检查间隔一致。例如任务每 30 分钟检查一次，只要每次检查仍命中目标价，就会约每 30 分钟提醒一次。

即使桌面通知没有弹出，命中记录仍会写入本地数据库，你可以在网页里查看。任务栏提醒依赖系统通知能力，当前以页面高亮、桌面通知和声音提示为主。

## 开发者路径

如果你要从源码运行，推荐 Windows 直接双击：

`start_fly_ticket.bat`

它会自动尝试：

1. 使用已有 Python 3.10+ 创建 `.venv`，或在没有 Python 时下载内置 Python
2. 安装运行依赖
3. 安装 Playwright Chromium
4. 从 `.env.example` 生成 `.env`
5. 启动本地网页服务
6. 自动打开浏览器

手动运行方式（Windows PowerShell）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

手动运行方式（macOS / Linux）：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

测试：

```bash
.venv/bin/python -m pytest
```

## 构建 Windows 便携版

维护者可以在 Windows PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_portable.ps1 -Version dev
```

构建结果会输出到：

- `dist/FlyTicket-Windows/`
- `dist/FlyTicket-Windows-dev.zip`

发布 GitHub Release 时，建议同时在 Release 说明里提供压缩包 SHA256，方便用户确认文件没有损坏或被替换。

## 配置说明

项目读取根目录下的 `.env`。

常用配置：

```env
APP_DB_PATH=data/app.db
PLAYWRIGHT_PROFILE_DIR=data/playwright-profile
PLAYWRIGHT_BROWSERS_PATH=runtime/ms-playwright
CTRIP_SNAPSHOT_DIR=data/debug
CTRIP_SAVE_DEBUG_SNAPSHOT=0
CTRIP_DEBUG_SNAPSHOT_DIR=data/debug
CTRIP_SEARCH_URL_TEMPLATE=
CTRIP_SESSION_URL=
APP_BASE_URL=http://127.0.0.1:8000
MONITOR_REALERT_COOLDOWN_ENABLED=1
MONITOR_REALERT_COOLDOWN_HOURS=6
```

最重要的两个携程配置：

```env
CTRIP_SEARCH_URL_TEMPLATE=https://flights.ctrip.com/online/list/oneway-{origin}-{destination}?depdate={departure_date}&cabin=y_s_c_f&adult=1&child=0&infant=0&containstax=1
CTRIP_SESSION_URL=https://flights.ctrip.com/online/channel/domestic
```

## 数据保存在哪里

本地数据默认保存在：

- `data/app.db`：搜索历史、监控任务、命中记录
- `data/playwright-profile`：携程登录状态
- `.env`：本地配置

升级新版本时，保留 `data/` 和 `.env` 即可继续使用原来的数据。

## 隐私和本地数据

本项目默认只在本机保存数据，不会把你的搜索历史、监控任务或携程登录状态上传到项目作者的服务器。

但是请注意：

- `data/playwright-profile/` 可能包含携程登录态、Cookie、浏览历史、Local Storage 等敏感信息。
- `data/app.db` 可能包含你的搜索历史、监控任务、目标价和命中记录。
- `.env` 可能包含你的本地配置。
- 如果开启 `CTRIP_SAVE_DEBUG_SNAPSHOT=1`，`data/debug/` 里可能保存携程页面 HTML，里面可能包含个人化内容。

不要把这些文件上传到 GitHub、网盘、论坛、Issue 或发给别人：

```text
.env
data/
runtime/
dist/
.venv/
*.log
*.err.log
```

## 安全边界

票价哨兵是本地工具，默认只监听 `127.0.0.1`。

请不要把服务改成 `0.0.0.0` 后暴露到公网或局域网。如果你确实需要远程访问，请自行增加登录认证、防火墙和网络安全措施。

## 免责声明

本项目仅供个人本地学习和自用。

- 不提供自动购票、抢票、下单功能。
- 不提供绕过验证码、绕过风控或批量抓取能力。
- 用户应自行遵守相关网站的服务条款以及所在地法律法规。
- 携程页面结构、登录策略或风控策略变化时，本工具可能无法正常搜索。
- 使用本项目产生的账号、网络、数据或法律风险由使用者自行承担。

## 问题排查

### 双击后页面没打开

先看启动窗口里的中文提示。常见原因是端口被占用、运行环境被安全软件拦截，或发布包没有完整解压。

### 页面打开了，但搜索失败

请检查：

- 是否已经登录携程
- 网络是否正常
- `.env` 里的 `CTRIP_SEARCH_URL_TEMPLATE` 是否正确
- 是否使用了 `bjs`、`sha` 这类城市代码

### 登录失效

首页会提示“携程登录已失效”。点击“重新登录”，在打开的携程页面完成登录后再回来搜索。

### 监控任务没有马上命中

监控任务按你设置的检查间隔运行，不是保存后马上无限刷新。你可以在监控详情里查看最近检查时间和最近最低价。

### 没看到桌面通知

不同系统环境的桌面通知后端表现不完全一致。即使通知没弹出，命中记录仍会保存，页面里也会显示最近命中。

### Windows 或杀毒软件提示风险

请确认压缩包来自你信任的 GitHub Release，并优先核对 Release 页面提供的 SHA256。便携版内置 Python 和浏览器运行环境，部分安全软件可能对未知压缩包或脚本启动器给出提示。

## 目录说明

- `app/`：后端代码、模板、静态资源
- `tests/`：自动化测试
- `data/`：本地数据库和浏览器登录状态，默认不应提交
- `scripts/`：启动和构建脚本
- `docs/superpowers/`：设计和实现计划文档

## 当前限制

- 只优先支持国内单程、固定日期
- 更推荐使用城市/机场代码
- 不做自动购票或自动下单
- 不接入邮件、微信、Telegram 等外部通知
- 不做云端长期运行；程序关闭后不会继续监控

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
