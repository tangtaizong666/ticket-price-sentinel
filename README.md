# Fly Ticket

一个本地运行的机票搜索与价格监控工具。

它可以：
- 搜索携程上的国内单程机票
- 显示当前最低价和符合条件的航班
- 保存搜索历史
- 保存价格监控任务
- 在价格达到目标价时进行本地提醒
- 点击命中结果后跳转到携程继续操作

## 适合谁

- 想自己盯机票价格的人
- 不想反复手动搜索同一条航线的人
- 希望在本机上运行，不依赖云服务的人

## 运行方式

### Windows 用户：推荐

直接双击项目根目录里的：

`start_fly_ticket.bat`

它会自动尝试做这些事：
1. 检查 Python 是否存在
2. 创建虚拟环境 `.venv`
3. 安装依赖
4. 安装 Playwright 和 Chromium
5. 如果 `.env` 不存在，就从 `.env.example` 生成
6. 启动本地网页服务
7. 自动打开浏览器

默认会打开：

`http://127.0.0.1:8000`

---

### 手动启动（适合熟悉命令行的人）

在项目目录运行：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell 类似，只是路径会变成：

```powershell
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 第一次使用怎么做

建议按这个顺序：

1. 打开首页
2. 点击“去登录”或“重新登录”
3. 在打开的携程页面完成登录
4. 回到本地页面
5. 先试一次搜索
6. 再创建一个监控任务

## 首页能做什么

首页现在是“首次使用仪表盘”，会优先展示：

- 登录状态
- 监控状态
- 最近一次命中
- 快速搜索入口
- 快速创建监控入口

如果你是第一次打开，它会先告诉你下一步该做什么。

## 搜索说明

当前搜索更适合使用携程风格的城市/机场代码，例如：

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

> 目前这一版优先保证真实搜索链路可用，所以代码模式比中文城市名更稳。

## 监控说明

你可以保存一个监控任务，设置：

- 出发地
- 到达地
- 日期
- 目标价
- 检查频率

程序运行时，后台会定时检查。

当最低价小于或等于目标价时：
- 会记录一条命中结果
- 你可以在网页里查看命中详情
- 再点击具体机票跳去携程

## `.env` 配置说明

项目会读取根目录下的 `.env` 文件。

如果你没有这个文件，可以把 `.env.example` 复制为 `.env`。

当前可用字段：

```env
APP_DB_PATH=data/app.db
PLAYWRIGHT_PROFILE_DIR=data/playwright-profile
CTRIP_SNAPSHOT_DIR=tests/fixtures
CTRIP_SEARCH_URL_TEMPLATE=
CTRIP_SESSION_URL=
APP_BASE_URL=http://127.0.0.1:8000
```

### 最重要的两个字段

#### `CTRIP_SEARCH_URL_TEMPLATE`
真实搜索结果页模板。

例如：

```env
CTRIP_SEARCH_URL_TEMPLATE=https://flights.ctrip.com/online/list/oneway-{origin}-{destination}?depdate={departure_date}&cabin=y_s_c_f&adult=1&child=0&infant=0&containstax=1
```

#### `CTRIP_SESSION_URL`
用来重新打开携程登录页。

例如：

```env
CTRIP_SESSION_URL=https://flights.ctrip.com/online/channel/domestic
```

## 当前已实现的能力

- 本地 Web 页面
- 携程登录复用
- 真实搜索机票
- 价格过滤
- 搜索历史
- 监控任务创建/更新
- 后台监控调度
- 命中记录保存
- 命中详情查看
- Windows 一键启动脚本
- 首页首次使用仪表盘

## 当前限制

这是一版本地可用工具，不是安装包软件，所以有这些限制：

- 需要本机安装 Python
- 更适合在 Windows 上本地运行
- 目前优先支持国内单程、固定日期
- 目前更推荐使用城市代码而不是中文名
- 外部通知（邮箱、微信、Telegram）还没做
- 真正的 exe / 安装包还没做

## 常见问题

### 1. 双击脚本没反应
先确认：
- 已安装 Python 3
- Python 已加入 PATH

可以在命令行试：

```bash
py -3 --version
```

或：

```bash
python --version
```

### 2. 页面能打开，但搜索失败
先检查：
- 你是否已经登录携程
- `.env` 里的 `CTRIP_SEARCH_URL_TEMPLATE` 是否正确
- 是否使用了像 `bjs`、`sha` 这样的城市代码

### 3. 点击“重新登录”后没成功
可能原因：
- 另一个运行中的程序实例还占着同一个浏览器 profile
- 携程页面本身要求你重新验证

建议：
- 先关闭旧的程序实例
- 再重新点击登录

### 4. 监控任务创建了，但没有马上命中
监控是按你设置的频率在后台检查，不是保存后立刻无限次刷新。

### 5. 命中提醒没有弹出来
当前版本已经接好了提醒路径，但不同系统环境的桌面通知后端行为可能不同。

即使提醒没有成功弹出：
- 命中记录仍然会写入系统
- 你仍然可以在网页里查看命中详情

## 开发与测试

如果你是开发者，可以运行：

```bash
cd /mnt/c/my_pycharm/fly_ticket
.venv/bin/python -m pytest -v
```

当前完整测试集已经通过。

## 目录说明

- `app/`：后端代码、模板、静态资源
- `tests/`：测试
- `data/`：本地数据库和浏览器 profile 数据
- `scripts/`：辅助脚本
- `docs/superpowers/`：设计和实现计划文档

## 后续可以继续做的事

- 更友好的中文城市名支持
- 更完整的监控详情页
- 外部通知渠道
- exe / 安装包
- 更完整的新手引导

如果你只是普通用户，建议你先从这条路径开始：

**双击 `start_fly_ticket.bat` → 登录携程 → 搜一次 → 保存一个监控任务**
