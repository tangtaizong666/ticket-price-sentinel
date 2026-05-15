# 提醒可见性增强设计

## 背景

`fly_ticket_test` 当前的命中提醒由三条通道组成：页面横幅、浏览器声音 + 系统通知（Web Audio + `Notification`）、Python 桌面通知（`plyer`）。用户反馈实际命中时三条通道都没响：

- 浏览器声音和 `Notification` 必须先点首页 "启用提醒" 按钮才会响，因此从未点过的用户永远收不到。
- 即使用户点过 "启用提醒"，`pollMonitorAlerts` 里有 `!document.hidden` 短路，浏览器在前台被别的窗口遮挡时仍不会调 `Notification`，所以 Windows 任务栏图标不会闪烁。
- `plyer` 在用户的 Windows 环境下没弹出。

目标：默认情况下命中即提醒，且包含两条独立的 "桌面角落弹窗 + 任务栏闪烁" 路径——浏览器在跑用浏览器，浏览器没开就靠 `.bat` 后台 Python 进程。

## 范围

仅修改提醒呈现层：

- `app/notifier.py` 的桌面通知后端
- `app/static/app.js` 中提醒触发条件和默认行为
- `app/templates/index.html` 增加 "提醒方式" 下拉，监控任务表单增加同款下拉
- `app/static/app.css` 加最低限度的下拉样式
- `app/settings.py` 增加一个声音开关
- `app/models.py` / `app/monitoring.py` / `app/db.py` / `app/main.py` 增加任务级 `notification_channels` 字段、全局 `notification_settings` 表和对应 REST 接口
- 对应的单元测试

不在范围：

- 不调整 `monitor_runner.should_notify_for_price` 的冷却策略
- 不改 `<title>` 和 favicon（用户选择只闪任务栏）
- 不为每个通道做 "测试一下" 按钮

## 目标行为

| 场景 | 期望 |
|------|------|
| 浏览器在前台、聚焦 | 横幅显示 + 三连音 + Notification 触发任务栏短暂闪烁 + 右下角原生 toast |
| 浏览器在前台、被别的窗口遮住 | 同上；任务栏图标橙色闪烁起到主要 attention 作用 |
| 浏览器最小化或在别的标签页 | Notification 触发任务栏闪烁 + 右下角 toast；点击 toast 聚焦窗口并跳到对应命中页 |
| 浏览器没开、`.bat` 在跑 | Python 端 winrt toast 在右下角弹出；点击 toast 打开浏览器到 `APP_BASE_URL/?monitor_task_id=…&monitor_hit_id=…` |
| Windows 通知权限尚未授权 | 横幅 + 声音仍然有；横幅文案旁边提示用户点 "启用提醒" 以打开任务栏闪烁 |
| 非 Windows | 浏览器侧不变；Python 侧回落 `plyer` |

## 设计

### 1. Python 通知后端（`app/notifier.py`）

`send_monitor_hit_alert` 增加 `channels: set[str]` 参数（默认 `{"banner","sound","browser","toast"}`，使旧调用方/测试不破）。

引入 `_send_windows_toast(title, message, launch_url)`：

- 仅当 `os.name == "nt"` 时尝试。
- 通过 `winrt.windows.ui.notifications` + `winrt.windows.data.xml.dom` 加载一份 `<toast><visual>…</visual></toast>` XML 模板，标题、正文、`launch` 属性各填一项。`launch` 设为 `launch_url`，使用户点击 toast 后能由系统通过 protocol handler 打开（HTTP URL 在 Windows 上由默认浏览器处理）。
- 用 `ToastNotificationManager.create_toast_notifier_with_id("Fly Ticket")` 拿 notifier，然后 `notifier.show(ToastNotification(xml))`。AUMID 在新版 Windows 不强制注册也能显示，注册失败的异常向上抛。
- 任意异常（导入失败、winrt 不可用、API 报错）都返回 `False`。

`send_monitor_hit_alert` 重构：

```
desktop_sent = False
if "toast" in channels:
    if os.name == "nt":
        desktop_sent = _send_windows_toast(title, message_with_url, launch_url=target_url)
    if not desktop_sent:
        desktop_sent = _send_desktop_notification(title, message_with_url, timeout=20)
sound_started = False
if "sound" in channels and _should_play_sound():
    sound_started = _start_monitor_hit_sound_thread()
return desktop_sent or sound_started
```

`channels` 里只有 `"toast"` 和 `"sound"` 影响 Python 行为；`"banner"` 和 `"browser"` 由前端处理，但参数保留四元集合，方便测试参数完整性、并使日志和未来扩展统一。

调度器侧：`monitor_scheduler.tick_once` 把 `task.notification_channels` 直接转成 `set` 传入。

`_should_play_sound()` 读 `MONITOR_NOTIFICATION_SOUND_ENABLED`（默认 `1`）。读取在 `notifier` 内部即时进行：私有函数 `_should_play_sound() -> bool`，内部 `return Settings().monitor_notification_sound_enabled`。注意：这一层是 "全局静音快捷键"，跟用户在 UI 里勾的 `sound` 通道是 AND 关系——两者都要为真才会响。

`_send_desktop_notification` 保持现状（plyer + winsound 兜底声音），它仍然作为非 Windows 平台和 winrt 失败时的回落。

### 2. 配置（`app/settings.py`）

新增字段：

```python
monitor_notification_sound_enabled: bool = field(
    default_factory=lambda: _env_flag("MONITOR_NOTIFICATION_SOUND_ENABLED", "1")
)
```

`notifier.py` 读取时通过 `Settings()` 单例，但当前 notifier 模块函数都是无状态的纯函数式调用。为不破坏现有签名，把读取放在 `_should_play_sound()` 私有函数里，每次调用 `Settings()` 即读 `.env`（`Settings` 已用 `dotenv` 加载）。`Settings()` 实例化非常便宜，不缓存。

### 3. 前端默认行为（`app/static/app.js`）

变更点：

- **去掉 `monitorAlertsAreEnabled()` 门**：`showBrowserMonitorNotification` 不再要求 localStorage 标志位，只要 `Notification.permission === "granted"` 且任务+全局都勾选了 `browser` 通道就发。
- **去掉 `!document.hidden` 短路**：前台被遮挡时也要能闪任务栏。
- **声音默认开**：`pollMonitorAlerts` 命中时按通道交集决定是否 `playMonitorAlertTone()`，不再先检查 `monitorAlertsAreEnabled()`。
- **`requireInteraction: true`**：在 `new Notification(...)` 选项里加上，让通知不会 5 秒消失。
- **`renotify: true`**：连续两次命中（hit_id 不同）时即便 tag 相同也再次提示。给 `tag` 保留为 `fly-ticket-hit-${hit_id}`，所以正常情况下不会冲突；`renotify` 只是保险。
- **首次进站没授权时给提示**：在初始化阶段如果 `Notification.permission === "default"`，把 `searchSummaryElement` 文案改为 "点击上方 '启用提醒' 后任务栏会闪烁，命中时会同时弹出系统通知"。这条提示只在尚未授权时显示一次，不重复打扰。
- **`requestMonitorAlertPermission`** 保留，但成功授权后的提示更明确："已开启系统通知，命中时浏览器图标会在任务栏闪烁。"它内部不再写 `monitorAlertsEnabledStorageKey`。
- **新增 `effectiveChannelsFor(alert)`**：取 `alert.notification_channels`（任务级）与 localStorage 全局设置的交集；任一缺失视作四元全集。
- **`pollMonitorAlerts` 命中分发**：
  ```js
  const effective = effectiveChannelsFor(latestAlert);
  if (effective.has("banner")) showMonitorAlertBanner(latestAlert);
  if (effective.has("sound")) playMonitorAlertTone();
  if (effective.has("browser")) showBrowserMonitorNotification(latestAlert);
  // toast 由后端处理
  ```

`enableMonitorAlertStorage()` / `monitorAlertsAreEnabled()` / `monitorAlertsEnabledStorageKey` 这三个废弃符号一起删除，避免理解成本。

### 4. 模板和 CSS

- 顶部把 `#enable-monitor-alerts` 旁边加一个新的 "提醒方式 ▾" 控件，用 `<details><summary>` 原生折叠，`<summary>` 是按钮样式，展开内容是 4 个 `<label><input type="checkbox" />…</label>`。无需 JS 框架。
- 监控任务表单里也加同款 `<details>`，标题为 "提醒方式（仅这个监控）"。`<input>` 命名 `notification_channels[]`，提交时序列化成 JSON 数组。
- CSS 给 `<summary>` 一些和现有 `secondary-action` 一致的内边距、边框；展开面板用现有 `panel` 模式背景色。无新动画。

### 5. 全局提醒通道 API（`app/main.py`）

- `GET /api/notification-settings` → `{ "channels": ["banner","sound","browser","toast"] }`
- `PUT /api/notification-settings` body `{ "channels": [...] }`，只接受四元枚举值的子集；空数组合法（用户主动全关）。同 `UNSAFE_HTTP_METHODS`，受 `X-FlyTicket-Token` 校验。
- 写入时 `INSERT INTO notification_settings(id, channels) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET channels=excluded.channels, updated_at=?`。

### 6. 数据模型

`models.py`：

```python
NotificationChannel = Literal["banner", "sound", "browser", "toast"]
ALL_NOTIFICATION_CHANNELS: tuple[NotificationChannel, ...] = (
    "banner", "sound", "browser", "toast",
)

class MonitorTaskBase(BaseModel):
    ...
    notification_channels: list[NotificationChannel] = Field(
        default_factory=lambda: list(ALL_NOTIFICATION_CHANNELS)
    )

class NotificationSettings(BaseModel):
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: list(ALL_NOTIFICATION_CHANNELS)
    )
```

`MonitorTask`、`MonitorTaskCreate`、`MonitorTaskUpdate` 透过继承获得新字段。

### 7. 数据库迁移（`app/db.py`）

`init_db` 增加：

```sql
CREATE TABLE IF NOT EXISTS notification_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    channels TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO notification_settings(id, channels, updated_at)
VALUES (1, '["banner","sound","browser","toast"]', '...');
```

对 `monitor_tasks`：先 `PRAGMA table_info(monitor_tasks)`，若没有 `notification_channels` 列则 `ALTER TABLE monitor_tasks ADD COLUMN notification_channels TEXT NOT NULL DEFAULT '["banner","sound","browser","toast"]'`。`INSERT/UPDATE` 路径在 `monitoring.py` 中显式 `json.dumps` 该字段。

### 8. 调度器 / API 集成

- `monitor_scheduler.tick_once`：调 `send_monitor_hit_alert(..., channels=set(task.notification_channels))`。
- `list_monitor_alerts_after` SQL 增加 `t.notification_channels`，`_monitor_alert_payload` 把 `notification_channels=json.loads(row["notification_channels"])` 放进 payload。
- 创建/更新 monitor task 接口接受新字段；`monitoring._row_to_monitor_task` 反序列化。

### 9. 错误处理

- winrt 导入失败 → 自动回落 plyer，日志 `logger.exception`。
- winrt `show()` 失败 → 同上。
- plyer 也失败 → 函数返回 `False`，但 `send_monitor_hit_alert` 仍然返回 `True`（声音线程派发成功），保持现有 "声音也算发出去了" 的语义。
- 浏览器 `Notification.permission === "denied"` → 静默跳过，仅显示横幅 + 声音。
- 浏览器构造 `Notification` 抛异常 → 用 `try/catch` 包住，`console.warn` 不打断后续 alert 处理。
- `PUT /api/notification-settings` 收到非法 channel 值 → 422，前端不更新 localStorage。
- 加载 `monitor_tasks` 行时 `notification_channels` JSON 为非法字符串 → 兜底为四元全集，并 `logger.warning`。

### 10. 测试

`tests/test_notifier.py` 新增：

1. `test_send_monitor_hit_alert_uses_winrt_toast_on_windows`：
   - `monkeypatch` 让 `os.name == "nt"`；
   - `monkeypatch` `_send_windows_toast` 为 recorder 返回 `True`；
   - 断言 plyer 后端**没**被调用，winrt 后端被调用，参数包含 `launch_url`。
2. `test_send_monitor_hit_alert_falls_back_to_plyer_when_winrt_fails`：
   - `_send_windows_toast` 返回 `False`，断言 plyer 后端被调用。
3. `test_send_monitor_hit_alert_skips_winrt_on_non_windows`：
   - `os.name != "nt"`；
   - `_send_windows_toast` 是 spy，断言未被调用。
4. `test_send_monitor_hit_alert_skips_sound_when_globally_disabled`：
   - `MONITOR_NOTIFICATION_SOUND_ENABLED=0`；
   - 断言 `_start_monitor_hit_sound_thread` 未被调用。
5. `test_send_monitor_hit_alert_skips_sound_when_channel_off`：
   - `channels={"banner","browser","toast"}`；
   - 断言 `_start_monitor_hit_sound_thread` 未被调用。
6. `test_send_monitor_hit_alert_skips_toast_when_channel_off`：
   - `channels={"banner","sound","browser"}`；
   - 断言 winrt 与 plyer 都未被调用，但声音线程被派发。

`tests/test_monitor_runner.py` 不变（评估层不读 channels）。

`tests/test_monitor_scheduler.py` 修改/新增：

- 现有 `_capture_monitor_alerts` 断言里加上 `channels=...` 字段。
- 新增 `test_monitor_scheduler_passes_task_channels_to_alert`：任务保存为 `["banner"]`，断言 `send_monitor_hit_alert` 收到的 `channels == {"banner"}`。

`tests/test_monitor_api.py` 新增：

- 创建 monitor 时携带 `notification_channels=["banner","sound"]`，GET 回读一致。
- PUT 修改通道。
- 非法值返回 422。

`tests/test_search_api.py` 不受影响（不读这一列）。

新增 `tests/test_notification_settings_api.py`：

- 默认 `GET` 返回四元全集。
- `PUT` 后 `GET` 回读一致。
- 非法 channel 422。
- 无 token 403。

由于 `winrt` 在 CI 和 Linux 上没装，所有针对 `_send_windows_toast` 的测试都用 monkeypatch 替换该函数本身，不直接 import winrt。`_send_windows_toast` 内部的 winrt 调用走 try/except，导入失败即返回 `False`，已被测试 2 覆盖。

前端 JS 没有自动化测试覆盖，依赖手动验证。

## 验收清单

- [ ] 浏览器在前台被遮挡，命中时任务栏图标橙色闪烁
- [ ] 浏览器最小化，命中时右下角弹原生 toast，点击聚焦浏览器并跳到对应命中
- [ ] 浏览器关闭，`.bat` 在跑，命中时 Action Center 弹 toast，点击打开浏览器跳到对应命中
- [ ] 用户从未点过 "启用提醒" 也能听到三连音、看到横幅
- [ ] `MONITOR_NOTIFICATION_SOUND_ENABLED=0` 时不响声音，但仍出 toast
- [ ] 顶部 "提醒方式" 下拉勾选状态在浏览器刷新后保留（localStorage + 后端双写）
- [ ] 任务级 "提醒方式" 与全局取交集决定本次命中行为
- [ ] 任务级勾掉 "桌面 toast" 后，命中时 Python 端不弹 toast；勾掉 "网页声音" 后不响三连音
- [ ] 旧测试全部通过；新测试全部通过

## 依赖与配置

- 无新 PyPI 依赖。`winrt` 通过 `winrt-runtime`/`winrt-Windows.UI.Notifications` 这种命名空间包提供；当前 `requirements.txt` 不显式加它，因为：
  - 大多数 Windows Python 3.9+ 安装可以单独 `pip install winrt-runtime winrt-Windows.UI.Notifications winrt-Windows.Data.Xml.Dom` 拿到，但版本和包名近年变动较多。
  - 如果未来打包发现部分用户系统缺这些包，再补 `requirements.txt`；当前实现保证缺失时无声回落 plyer，不会崩溃。
- `.env` / `.env.example` 增加 `MONITOR_NOTIFICATION_SOUND_ENABLED=1`。

## 风险

- **winrt 包导入路径不稳定**：不同 winrt 版本的 import path 不同（旧版 `winrt.windows.ui.notifications`，新版 `winsdk.windows.ui.notifications`）。实现时同时尝试两条 import 路径，全部失败即回落。这一点要在测试 2 里覆盖。
- **AUMID（应用 ID）**：不注册的 AUMID 在 Windows 11 上会显示 "Python" 之类的默认名，但仍能弹出。我们不引入额外的 quickstart 注册步骤；如果用户希望显示 "Fly Ticket"，后续可在便携包里加注册脚本。
