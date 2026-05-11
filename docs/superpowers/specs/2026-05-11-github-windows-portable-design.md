# GitHub Windows 便携版发布设计

## 1. 目标

把项目整理成面向普通 Windows 用户的 GitHub 发布包。用户从 GitHub Release 下载 zip，解压后双击启动脚本即可打开本地机票监控页面；不要求用户额外安装 Python、pip 依赖或 Playwright 浏览器。

第一版只支持 Windows。macOS、Linux、正式安装包和系统服务不纳入本次范围。

## 2. 用户体验

目标用户拿到发布包后的流程：

1. 下载 `FlyTicket-Windows-<version>.zip`。
2. 解压到一个普通目录。
3. 双击 `启动机票监控.bat`。
4. 程序自动启动本地服务并打开浏览器。
5. 用户在网页里登录携程、搜索机票、创建监控任务。

启动失败时，命令行窗口必须停留，并用中文说明问题和下一步建议，避免双击后一闪而过。

## 3. 发布包结构

发布包目录建议如下：

```text
FlyTicket-Windows/
  启动机票监控.bat
  README_使用说明.txt
  app/
  runtime/
    python/
    ms-playwright/
  data/
  .env.example
```

职责划分：

- `启动机票监控.bat`：普通用户唯一需要双击的入口。
- `README_使用说明.txt`：面向普通用户的离线说明。
- `app/`：后端代码、模板和静态资源。
- `runtime/python/`：内置 Python 运行环境和项目运行依赖。
- `runtime/ms-playwright/`：内置 Playwright Chromium 浏览器。
- `data/`：用户本地数据库、浏览器 profile 和登录状态。
- `.env.example`：首次运行时复制为 `.env`。

发布包不包含开发测试依赖、本地 `.env`、本地数据库、真实浏览器 profile、临时截图或未清理的真实页面快照。

## 4. 启动流程

`启动机票监控.bat` 负责：

1. 切换到发布包目录。
2. 检查 `runtime\python\python.exe` 是否存在。
3. 如果 `.env` 不存在，从 `.env.example` 复制生成。
4. 设置 `PLAYWRIGHT_BROWSERS_PATH` 指向 `runtime\ms-playwright`。
5. 自动寻找可用端口，优先使用 `8000`，被占用时尝试后续端口。
6. 将本次启动的本地访问地址传给应用或启动命令。
7. 使用包内 Python 启动 `uvicorn app.main:app`。
8. 打开浏览器访问实际端口。
9. 出错时停留窗口并输出中文错误。

启动脚本不能调用系统 `python`、`py` 或联网安装依赖。发布包应在构建阶段完成依赖准备。

## 5. 构建流程

仓库新增维护者使用的构建脚本：

```text
scripts/build_windows_portable.ps1
```

构建脚本负责生成 `dist/FlyTicket-Windows/` 和 zip：

1. 创建干净的发布目录。
2. 准备 Windows Python embeddable 或指定的便携 Python 运行环境。
3. 安装项目运行依赖到发布包内。
4. 安装 Playwright Chromium 到 `runtime/ms-playwright`。
5. 复制 `app/`、必要配置、README 和启动脚本。
6. 排除 `.env`、`data/` 中的本地状态、测试缓存、开发依赖和敏感测试快照。
7. 生成 `FlyTicket-Windows-<version>.zip`。

构建脚本是维护者工具，不是普通用户启动入口。它可以要求维护者本机有 PowerShell、网络和构建所需工具。

## 6. 现有修复纳入发布范围

发布前需要先纳入已发现的稳定性和安全修复：

- 搜索共享 context 时关闭临时 page，避免资源泄漏。
- 应用关闭时释放 Ctrip session manager、browser context 和 Playwright。
- 监控失败时记录日志，并推进 `last_checked_at` 和 `next_check_at`，避免任务卡在同一时间重复失败。
- 搜索成功后保存 session `ready` 状态；登录过期后保存 `expired` 状态。
- Dashboard 正确展示 `ready` 和 `expired` 登录状态。
- 前端避免使用不安全的 `innerHTML`。
- 外部打开链接使用 `noopener,noreferrer`。
- 清理测试 fixture 中来自真实页面的敏感内容。
- 保留对应回归测试。

这些修复先于便携版打包完成，否则发布包会继承已知缺陷。

## 7. 配置和首次使用

`.env.example` 应尽量包含可运行的默认值：

- `APP_DB_PATH=data/app.db`
- `PLAYWRIGHT_PROFILE_DIR=data/playwright-profile`
- `PLAYWRIGHT_BROWSERS_PATH=runtime/ms-playwright`
- `APP_BASE_URL` 可由启动脚本按实际端口覆盖或写入。

对仍需用户确认的携程 URL 配置，页面或 README 必须说明用途。若能提供稳定默认值，应放入 `.env.example`，降低首次使用门槛。

首次运行不会覆盖已有 `.env`、数据库或登录状态。用户升级时可保留 `data/` 和 `.env`。

## 8. 文档调整

README 分为普通用户和开发者两条路径：

- 普通用户：下载 Release zip、解压、双击启动、登录携程、搜索、创建监控。
- 开发者：从源码安装依赖、运行测试、本地启动、构建 Windows 便携包。

发布包内增加 `README_使用说明.txt`，内容保持短而具体，避免要求普通用户理解虚拟环境、pip 或 Playwright。

常见问题至少覆盖：

- Windows 安全提示或杀毒软件拦截。
- 端口占用。
- 登录状态失效。
- 搜索配置缺失。
- 数据和登录状态保存在哪里。
- 如何升级到新版本。

## 9. 测试和验证

实现时需要保留原有后端测试，并新增面向交付形态的测试或脚本检查：

- 启动脚本不依赖系统 Python。
- 启动脚本设置包内 Playwright 浏览器路径。
- 启动脚本会处理端口占用。
- 构建脚本不会复制 `.env`、本地数据库或浏览器 profile。
- 构建脚本生成的发布目录包含启动所需文件。
- 清理后的 fixture 不含明显真实 cookie、token 或用户状态片段。

最终验证至少包括：

1. 主分支完整测试通过。
2. 已合入稳定性修复后的测试通过。
3. 在本机执行一次 Windows 便携包构建。
4. 用构建产物启动应用并确认首页可访问。

## 10. 不纳入本次范围

- macOS 或 Linux 便携包。
- PyInstaller exe。
- Windows 安装器。
- 开机自启动。
- 后台系统服务。
- 自动更新器。
- 自动购票或自动下单。
