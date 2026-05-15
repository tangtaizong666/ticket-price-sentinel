# 提醒可见性增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让命中提醒默认就响，并在前后端都加上四通道（横幅、声音、浏览器通知、桌面 toast）的下拉开关，全局 + 任务级双层独立存储。

**Architecture:** Python 通知层用 winrt 优先 / plyer 回落；新增 `notification_settings` 单行表 + `monitor_tasks.notification_channels` JSON 列；FastAPI 增 `/api/notification-settings` REST；前端用 `<details>` 原生折叠面板做下拉，pollMonitorAlerts 改成按任务×全局通道交集分发。

**Tech Stack:** Python 3.11, FastAPI, SQLite, Pydantic, pytest, plyer, winrt（运行时可选）, 原生 HTML/CSS/JS。

---

## 全局规则

- 项目工作目录是 `/mnt/c/my_pycharm/fly_ticket_test`。所有相对路径都基于此。
- 不要修改 `.env`（用户本地文件）。只更新 `.env.example` 或新建说明性变量在源代码默认值上。本项目当前没有 `.env.example`，跳过。
- 测试用 `python -m pytest tests/<file>::<test> -v` 运行。所有测试要能在非 Windows 上跑通，winrt 相关测试必须用 monkeypatch 替换函数，而不是真的 import winrt。
- 频繁提交：每一个 Task 末尾都有 commit 步骤。
- 不要在前端 JS 写 emoji。
- 注意 sqlite3 `connect(...)` 是 context manager，提交自动；显式提交不需要。

## 文件结构

| 文件 | 责任 | 操作 |
|------|------|------|
| `app/settings.py` | 全局 `.env` 配置 | Modify：加 `monitor_notification_sound_enabled` 字段 |
| `app/models.py` | Pydantic 模型 | Modify：加 `NotificationChannel`、`ALL_NOTIFICATION_CHANNELS`、`MonitorTaskBase.notification_channels`、`NotificationSettings` |
| `app/db.py` | SQLite schema 与迁移 | Modify：在 `init_db` 里加 `notification_settings` 表，加 `monitor_tasks.notification_channels` 列 |
| `app/monitoring.py` | monitor_tasks CRUD | Modify：读写 `notification_channels`；新增 `get_notification_settings` / `set_notification_settings` |
| `app/notifier.py` | 桌面通知 + 声音 | Modify：加 `_send_windows_toast`、`_should_play_sound`，`send_monitor_hit_alert` 接受 `channels` 参数 |
| `app/monitor_scheduler.py` | 调度命中 → 提醒分发 | Modify：把 `task.notification_channels` 传给 `send_monitor_hit_alert` |
| `app/main.py` | FastAPI 路由 | Modify：加 `/api/notification-settings` GET/PUT；`/api/monitor-alerts` 返回 `notification_channels` |
| `app/templates/index.html` | 页面 HTML | Modify：顶部加全局通道下拉；任务表单里加任务级通道下拉 |
| `app/static/app.js` | 前端逻辑 | Modify：删除 `monitorAlertsAreEnabled` 门 + `document.hidden` 短路；新增全局/任务通道读写；按通道交集分发 |
| `app/static/app.css` | 样式 | Modify：给下拉面板加最低限度样式 |
| `tests/test_notifier.py` | 通知测试 | Modify：新增 6 个场景 |
| `tests/test_monitor_runner.py` | 评估测试 | Modify：`_capture_monitor_alerts` 断言加 `channels` |
| `tests/test_monitoring_repository.py` | repository 测试 | Modify：覆盖 `notification_channels` 往返 + 全局设置 |
| `tests/test_monitor_api.py` | monitor API 测试 | Modify：创建/更新/读取覆盖 `notification_channels`；非法值 422 |
| `tests/test_notification_settings_api.py` | 全局设置 API 测试 | Create：4 个测试覆盖 GET/PUT/422/403 |

---

## Task 1: 引入 `NotificationChannel` 枚举与模型字段

**Files:**
- Modify: `app/models.py`
- Test: `tests/test_monitoring_repository.py`（沿用既有套件，下一个 Task 会扩展）

- [ ] **Step 1: 写一个失败的测试，验证 `MonitorTaskCreate` 的默认 `notification_channels`**

在 `tests/test_monitoring_repository.py` 顶部 import 区下方加：

```python
from app.models import ALL_NOTIFICATION_CHANNELS, MonitorTaskCreate, NotificationChannel
```

文件末尾追加：

```python
def test_monitor_task_create_defaults_to_all_notification_channels() -> None:
    payload = MonitorTaskCreate(
        origin_city="bjs",
        destination_city="sha",
        departure_date=date(2026, 5, 20),
        target_price=400,
        check_interval_minutes=30,
    )

    assert payload.notification_channels == list(ALL_NOTIFICATION_CHANNELS)


def test_monitor_task_create_rejects_unknown_channel() -> None:
    with pytest.raises(ValueError):
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
            notification_channels=["banner", "telegram"],
        )
```

（如该文件没 `from datetime import date`、`import pytest`，请补上。）

- [ ] **Step 2: 运行测试，确认它失败**

```bash
cd /mnt/c/my_pycharm/fly_ticket_test
python -m pytest tests/test_monitoring_repository.py -k notification_channels -v
```

Expected: ImportError 或 AttributeError（`ALL_NOTIFICATION_CHANNELS` / `NotificationChannel` 不存在）。

- [ ] **Step 3: 修改 `app/models.py` 添加枚举与字段**

在文件顶部 `from typing import Literal` 已存在，无需重复 import。

在 `class MonitorTaskBase(BaseModel)` 定义之前加：

```python
NotificationChannel = Literal["banner", "sound", "browser", "toast"]
ALL_NOTIFICATION_CHANNELS: tuple[NotificationChannel, ...] = (
    "banner",
    "sound",
    "browser",
    "toast",
)
```

在 `MonitorTaskBase` 的字段区（与 `unchanged_reminder_interval_minutes` 同一块）加：

```python
    notification_channels: list[NotificationChannel] = Field(
        default_factory=lambda: list(ALL_NOTIFICATION_CHANNELS)
    )
```

在文件末尾追加：

```python
class NotificationSettings(BaseModel):
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: list(ALL_NOTIFICATION_CHANNELS)
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_monitoring_repository.py -k notification_channels -v
```

Expected: 2 passed。

- [ ] **Step 5: 跑完整 models / repository 测试，确认没有回归**

```bash
python -m pytest tests/test_monitoring_repository.py -v
```

Expected: 全部通过（含旧用例）。

- [ ] **Step 6: 提交**

```bash
git add app/models.py tests/test_monitoring_repository.py
git commit -m "feat: introduce NotificationChannel enum and task field default"
```

---

## Task 2: 数据库迁移——任务级 JSON 列 + 全局单行表

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_monitoring_repository.py`

- [ ] **Step 1: 写两个失败的测试**

在 `tests/test_monitoring_repository.py` 末尾追加：

```python
def test_init_db_adds_notification_channels_column_to_existing_database(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    settings.app_db_path.parent.mkdir(parents=True, exist_ok=True)

    legacy = sqlite3.connect(settings.app_db_path)
    legacy.executescript(
        """
        CREATE TABLE monitor_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin_city TEXT NOT NULL,
            destination_city TEXT NOT NULL,
            departure_date TEXT NOT NULL,
            target_price INTEGER NOT NULL,
            check_interval_minutes INTEGER NOT NULL,
            departure_time_filters TEXT NOT NULL,
            flight_attribute_filters TEXT NOT NULL,
            airline_filters TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            last_checked_at TEXT,
            next_check_at TEXT NOT NULL,
            last_seen_lowest_price INTEGER,
            last_notified_at TEXT,
            last_notified_price INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO monitor_tasks (
            origin_city, destination_city, departure_date, target_price,
            check_interval_minutes, departure_time_filters, flight_attribute_filters,
            airline_filters, enabled, next_check_at, created_at, updated_at
        ) VALUES (
            'bjs', 'sha', '2026-05-20', 400,
            30, '[]', '[]',
            '[]', 1, '2026-05-15T08:00:00+00:00',
            '2026-05-15T08:00:00+00:00', '2026-05-15T08:00:00+00:00'
        );
        """
    )
    legacy.commit()
    legacy.close()

    init_db(settings)

    with sqlite3.connect(settings.app_db_path) as connection:
        connection.row_factory = sqlite3.Row
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(monitor_tasks)")}
        row = connection.execute(
            "SELECT notification_channels FROM monitor_tasks LIMIT 1"
        ).fetchone()

    assert "notification_channels" in columns
    assert json.loads(row["notification_channels"]) == list(ALL_NOTIFICATION_CHANNELS)


def test_init_db_creates_notification_settings_with_default_row(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")

    init_db(settings)

    with sqlite3.connect(settings.app_db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, channels FROM notification_settings WHERE id = 1"
        ).fetchone()

    assert row is not None
    assert json.loads(row["channels"]) == list(ALL_NOTIFICATION_CHANNELS)
```

文件顶部如果没有 `import json`、`import sqlite3`、`from app.db import init_db`、`from app.settings import Settings`，请补齐。

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_monitoring_repository.py -k "notification_channels_column or notification_settings_with_default_row" -v
```

Expected: `sqlite3.OperationalError: no such column: notification_channels` 与 `no such table: notification_settings`。

- [ ] **Step 3: 修改 `app/db.py`**

在 `init_db` 函数 `executescript` 的 SQL 中追加新表（放在最后一条语句之后、`"""`之前）：

```sql

            CREATE TABLE IF NOT EXISTS notification_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                channels TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
```

在 `executescript` 调用之后、`_ensure_column` 两个调用之后，新增：

```python
        _ensure_column(
            connection,
            "monitor_tasks",
            "notification_channels",
            "TEXT NOT NULL DEFAULT '[\"banner\",\"sound\",\"browser\",\"toast\"]'",
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO notification_settings(id, channels, updated_at)
            VALUES (1, '["banner","sound","browser","toast"]', ?)
            """,
            (_now_iso(),),
        )
```

在文件顶部加：

```python
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_monitoring_repository.py -k "notification_channels_column or notification_settings_with_default_row" -v
```

Expected: 2 passed。

- [ ] **Step 5: 跑整套 repository 测试，确保旧测试也过**

```bash
python -m pytest tests/test_monitoring_repository.py -v
```

Expected: 所有 passed。

- [ ] **Step 6: 提交**

```bash
git add app/db.py tests/test_monitoring_repository.py
git commit -m "feat: migrate monitor_tasks and add notification_settings table"
```

---

## Task 3: 在 `monitoring.py` 持久化 `notification_channels` + 全局设置 CRUD

**Files:**
- Modify: `app/monitoring.py`
- Test: `tests/test_monitoring_repository.py`

- [ ] **Step 1: 写四个失败测试**

在 `tests/test_monitoring_repository.py` 末尾追加：

```python
def test_create_monitor_task_persists_notification_channels(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    task = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
            notification_channels=["banner", "sound"],
        ),
    )

    fetched = get_monitor_task(settings, task.id)
    assert fetched is not None
    assert fetched.notification_channels == ["banner", "sound"]


def test_update_monitor_task_overwrites_notification_channels(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    task = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
        ),
    )

    updated = update_monitor_task(
        settings,
        task.id,
        MonitorTaskUpdate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
            notification_channels=["toast"],
        ),
        existing_monitor=task,
    )

    assert updated.notification_channels == ["toast"]


def test_get_notification_settings_returns_defaults_when_missing(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    result = get_notification_settings(settings)

    assert result.channels == list(ALL_NOTIFICATION_CHANNELS)


def test_set_notification_settings_persists_and_round_trips(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    set_notification_settings(settings, NotificationSettings(channels=["banner", "browser"]))

    result = get_notification_settings(settings)
    assert result.channels == ["banner", "browser"]
```

并补 import：

```python
from app.models import (
    ALL_NOTIFICATION_CHANNELS,
    MonitorTaskCreate,
    MonitorTaskUpdate,
    NotificationSettings,
)
from app.monitoring import (
    create_monitor_task,
    get_monitor_task,
    get_notification_settings,
    set_notification_settings,
    update_monitor_task,
)
```

如已有同 import，合并；不要重复 import。

- [ ] **Step 2: 跑测试，确认全部失败**

```bash
python -m pytest tests/test_monitoring_repository.py -k "notification_channels or notification_settings" -v
```

Expected: `ImportError` 或 `AttributeError`（`get_notification_settings` 等不存在）。

- [ ] **Step 3: 修改 `app/monitoring.py`**

在文件顶部 import 区加：

```python
from app.models import (
    ALL_NOTIFICATION_CHANNELS,
    MonitorCheckResult,
    MonitorHit,
    MonitorTask,
    MonitorTaskCreate,
    MonitorTaskUpdate,
    NotificationChannel,
    NotificationSettings,
)
```

（以现有 import 为基础合并）。

`create_monitor_task` 的 INSERT SQL 修改：

把 `airline_filters,` 那一段的 SQL 拓展：

```python
        cursor = connection.execute(
            """
            INSERT INTO monitor_tasks (
                origin_city,
                destination_city,
                departure_date,
                target_price,
                check_interval_minutes,
                departure_time_filters,
                flight_attribute_filters,
                airline_filters,
                reminder_policy,
                unchanged_reminder_interval_minutes,
                notification_channels,
                enabled,
                next_check_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.origin_city,
                payload.destination_city,
                payload.departure_date.isoformat(),
                payload.target_price,
                payload.check_interval_minutes,
                json.dumps(payload.departure_time_filters, ensure_ascii=False),
                json.dumps(payload.flight_attribute_filters, ensure_ascii=False),
                json.dumps(payload.airline_filters, ensure_ascii=False),
                payload.reminder_policy,
                payload.unchanged_reminder_interval_minutes,
                json.dumps(payload.notification_channels, ensure_ascii=False),
                1,
                next_check_at.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
```

`update_monitor_task` 同理，在 SET 子句加 `notification_channels = ?,`，对应 tuple 项 `json.dumps(payload.notification_channels, ensure_ascii=False),`：

```python
        connection.execute(
            """
            UPDATE monitor_tasks
            SET origin_city = ?,
                destination_city = ?,
                departure_date = ?,
                target_price = ?,
                check_interval_minutes = ?,
                departure_time_filters = ?,
                flight_attribute_filters = ?,
                airline_filters = ?,
                reminder_policy = ?,
                unchanged_reminder_interval_minutes = ?,
                notification_channels = ?,
                enabled = ?,
                next_check_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                payload.origin_city,
                payload.destination_city,
                payload.departure_date.isoformat(),
                payload.target_price,
                payload.check_interval_minutes,
                json.dumps(payload.departure_time_filters, ensure_ascii=False),
                json.dumps(payload.flight_attribute_filters, ensure_ascii=False),
                json.dumps(payload.airline_filters, ensure_ascii=False),
                payload.reminder_policy,
                payload.unchanged_reminder_interval_minutes,
                json.dumps(payload.notification_channels, ensure_ascii=False),
                int(enabled),
                next_check_at.isoformat(),
                now.isoformat(),
                monitor_task_id,
            ),
        )
```

`_row_to_monitor_task` 增加字段读取，放在 `reminder_policy=` 之后：

```python
        notification_channels=_parse_notification_channels(
            _row_value(row, "notification_channels", None)
        ),
```

文件末尾追加两个工具函数：

```python
def _parse_notification_channels(raw: str | None) -> list[NotificationChannel]:
    if not raw:
        return list(ALL_NOTIFICATION_CHANNELS)
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return list(ALL_NOTIFICATION_CHANNELS)
    if not isinstance(decoded, list):
        return list(ALL_NOTIFICATION_CHANNELS)
    cleaned = [item for item in decoded if item in ALL_NOTIFICATION_CHANNELS]
    return cleaned


def get_notification_settings(settings: Settings) -> NotificationSettings:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT channels FROM notification_settings WHERE id = 1"
        ).fetchone()

    if row is None:
        return NotificationSettings()
    parsed = _parse_notification_channels(row["channels"])
    return NotificationSettings(channels=parsed)


def set_notification_settings(
    settings: Settings,
    payload: NotificationSettings,
) -> NotificationSettings:
    now = datetime.now(UTC)
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO notification_settings(id, channels, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                channels = excluded.channels,
                updated_at = excluded.updated_at
            """,
            (
                json.dumps(payload.channels, ensure_ascii=False),
                now.isoformat(),
            ),
        )
    return get_notification_settings(settings)
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
python -m pytest tests/test_monitoring_repository.py -v
```

Expected: 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add app/monitoring.py tests/test_monitoring_repository.py
git commit -m "feat: persist notification_channels and notification_settings"
```

---

## Task 4: REST 接口 `/api/notification-settings`

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_notification_settings_api.py` (create)

- [ ] **Step 1: 创建新的测试文件**

`tests/test_notification_settings_api.py` 内容：

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


class _StubScraper:
    async def search(self, *_args, **_kwargs):
        return []


class _StubSessionManager:
    async def close(self):
        return None

    async def open_relogin_window(self):
        return {"status": "noop"}

    async def close_login_window(self):
        return None


@pytest.fixture
def client(tmp_path):
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(
        settings=settings,
        scraper=_StubScraper(),
        session_manager=_StubSessionManager(),
    )
    with TestClient(app) as test_client:
        token = app.state.local_request_token
        test_client.headers.update({"X-FlyTicket-Token": token})
        yield test_client


def test_get_notification_settings_returns_all_channels_by_default(client) -> None:
    response = client.get("/api/notification-settings")

    assert response.status_code == 200
    assert response.json() == {"channels": ["banner", "sound", "browser", "toast"]}


def test_put_notification_settings_persists_subset(client) -> None:
    response = client.put(
        "/api/notification-settings",
        json={"channels": ["banner", "browser"]},
    )

    assert response.status_code == 200
    assert response.json() == {"channels": ["banner", "browser"]}

    follow_up = client.get("/api/notification-settings")
    assert follow_up.json() == {"channels": ["banner", "browser"]}


def test_put_notification_settings_rejects_unknown_channel(client) -> None:
    response = client.put(
        "/api/notification-settings",
        json={"channels": ["banner", "sms"]},
    )

    assert response.status_code == 422


def test_put_notification_settings_requires_local_token(client) -> None:
    client.headers.pop("X-FlyTicket-Token", None)

    response = client.put(
        "/api/notification-settings",
        json={"channels": ["banner"]},
    )

    assert response.status_code == 403
```

- [ ] **Step 2: 跑测试，确认全失败**

```bash
python -m pytest tests/test_notification_settings_api.py -v
```

Expected: 4 个 404 / 405（路由不存在）。

- [ ] **Step 3: 修改 `app/main.py`**

在 import 区加：

```python
from app.models import (
    MonitorTaskCreate,
    MonitorTaskUpdate,
    NotificationSettings,
    SearchRequest,
    SearchResponse,
)
from app.monitoring import (
    create_monitor_task,
    get_monitor_task,
    get_notification_settings,
    list_monitor_alerts_after,
    list_monitor_checks,
    list_monitor_hits,
    list_monitor_tasks,
    set_notification_settings,
    update_monitor_task,
)
```

（合并已有 import。）

在 `create_app` 的路由区，紧挨 `get_monitor_list` 下方加：

```python
    @app.get("/api/notification-settings")
    async def get_notification_settings_endpoint() -> NotificationSettings:
        return get_notification_settings(app.state.settings)

    @app.put("/api/notification-settings")
    async def update_notification_settings_endpoint(payload: NotificationSettings) -> NotificationSettings:
        return set_notification_settings(app.state.settings, payload)
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
python -m pytest tests/test_notification_settings_api.py -v
```

Expected: 4 passed。

- [ ] **Step 5: 跑邻近 API 套件防回归**

```bash
python -m pytest tests/test_monitor_api.py tests/test_search_api.py tests/test_history_api.py tests/test_session_api.py -v
```

Expected: 全部通过。

- [ ] **Step 6: 提交**

```bash
git add app/main.py tests/test_notification_settings_api.py
git commit -m "feat: add /api/notification-settings GET and PUT"
```

---

## Task 5: Monitor API 透传 `notification_channels`

**Files:**
- Modify: `tests/test_monitor_api.py`（仅当未覆盖时）
- Modify: `app/main.py`（如有需要的额外字段）
- Modify: `app/monitoring.py`（已在 Task 3 完成的话此 Task 主要在测试与 API 上验证）

- [ ] **Step 1: 写测试，覆盖创建、读取、PUT、422**

打开 `tests/test_monitor_api.py`，文件末尾追加：

```python
def test_create_monitor_task_persists_notification_channels(client) -> None:
    payload = {
        "origin_city": "bjs",
        "destination_city": "sha",
        "departure_date": "2026-05-20",
        "target_price": 400,
        "check_interval_minutes": 30,
        "notification_channels": ["banner", "browser"],
    }
    response = client.post("/api/monitors", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["notification_channels"] == ["banner", "browser"]

    fetched = client.get(f"/api/monitors/{body['id']}").json()
    assert fetched["notification_channels"] == ["banner", "browser"]


def test_update_monitor_task_persists_notification_channels(client) -> None:
    payload = {
        "origin_city": "bjs",
        "destination_city": "sha",
        "departure_date": "2026-05-20",
        "target_price": 400,
        "check_interval_minutes": 30,
    }
    created = client.post("/api/monitors", json=payload).json()

    update = dict(payload, notification_channels=["toast"])
    response = client.put(f"/api/monitors/{created['id']}", json=update)

    assert response.status_code == 200
    assert response.json()["notification_channels"] == ["toast"]


def test_monitor_task_rejects_unknown_notification_channel(client) -> None:
    payload = {
        "origin_city": "bjs",
        "destination_city": "sha",
        "departure_date": "2026-05-20",
        "target_price": 400,
        "check_interval_minutes": 30,
        "notification_channels": ["banner", "email"],
    }
    response = client.post("/api/monitors", json=payload)

    assert response.status_code == 422
```

（如该测试文件没 `client` fixture，参考 `test_notification_settings_api.py` 写一个相同的；多数情况下文件已有 fixture）。

- [ ] **Step 2: 跑测试**

```bash
python -m pytest tests/test_monitor_api.py -v
```

Expected: 新增 3 个全部 passed（在 Task 1-4 完成后，模型与 SQL 都通了，应直接通过）。如有失败，查看错误内容并定位是模型还是 SQL 漏改。

- [ ] **Step 3: 提交**

```bash
git add tests/test_monitor_api.py
git commit -m "test: cover monitor task notification_channels in API"
```

---

## Task 6: `_monitor_alert_payload` 暴露 `notification_channels`

**Files:**
- Modify: `app/main.py` (`_monitor_alert_payload`)
- Modify: `app/monitoring.py` (`list_monitor_alerts_after` SQL)
- Test: `tests/test_monitor_api.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_monitor_api.py` 末尾追加：

```python
def test_monitor_alerts_endpoint_includes_notification_channels(client) -> None:
    payload = {
        "origin_city": "bjs",
        "destination_city": "sha",
        "departure_date": "2026-05-20",
        "target_price": 400,
        "check_interval_minutes": 30,
        "notification_channels": ["banner", "toast"],
    }
    created = client.post("/api/monitors", json=payload).json()

    # 手动制造一条 hit，绕过调度器
    from datetime import UTC, datetime
    import json as _json
    import sqlite3

    settings = client.app.state.settings
    with sqlite3.connect(settings.app_db_path) as connection:
        connection.execute(
            """
            INSERT INTO monitor_hits (
                monitor_task_id, hit_price, hit_at, search_snapshot_json,
                lowest_price, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created["id"],
                380,
                datetime.now(UTC).isoformat(),
                _json.dumps([], ensure_ascii=False),
                380,
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()

    response = client.get("/api/monitor-alerts?after_id=0")
    body = response.json()
    assert response.status_code == 200
    assert len(body["alerts"]) == 1
    assert body["alerts"][0]["notification_channels"] == ["banner", "toast"]
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
python -m pytest tests/test_monitor_api.py::test_monitor_alerts_endpoint_includes_notification_channels -v
```

Expected: `KeyError` 或 `assert ... != ["banner","toast"]`。

- [ ] **Step 3: 修改 `app/monitoring.py` 的 `list_monitor_alerts_after`**

SELECT 加 `t.notification_channels AS notification_channels`，整体改成：

```python
            """
            SELECT
                h.id AS hit_id,
                h.monitor_task_id AS monitor_task_id,
                t.origin_city AS origin_city,
                t.destination_city AS destination_city,
                t.departure_date AS departure_date,
                h.lowest_price AS lowest_price,
                t.target_price AS target_price,
                h.hit_at AS hit_at,
                t.notification_channels AS notification_channels
            FROM monitor_hits h
            JOIN monitor_tasks t ON t.id = h.monitor_task_id
            WHERE h.id > ?
            ORDER BY h.id ASC
            LIMIT 50
            """
```

- [ ] **Step 4: 修改 `app/main.py` 的 `_monitor_alert_payload`**

```python
def _monitor_alert_payload(settings: Settings, row: dict[str, object]) -> dict[str, object]:
    title, message = build_notification_message(
        str(row["origin_city"]),
        str(row["destination_city"]),
        int(row["lowest_price"]),
        int(row["target_price"]),
        departure_date=str(row["departure_date"]),
    )
    raw_channels = row.get("notification_channels")
    channels = _parse_alert_channels(raw_channels)
    return {
        "hit_id": int(row["hit_id"]),
        "monitor_task_id": int(row["monitor_task_id"]),
        "origin_city": row["origin_city"],
        "destination_city": row["destination_city"],
        "departure_date": row["departure_date"],
        "lowest_price": row["lowest_price"],
        "target_price": row["target_price"],
        "hit_at": _serialize_datetime_for_api(row["hit_at"]),
        "title": title,
        "message": message,
        "url": build_monitor_target_url(
            settings.app_base_url,
            int(row["monitor_task_id"]),
            int(row["hit_id"]),
        ),
        "notification_channels": channels,
    }
```

在文件靠上的工具区加：

```python
def _parse_alert_channels(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    if isinstance(raw, str) and raw:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return ["banner", "sound", "browser", "toast"]
        if isinstance(decoded, list):
            return [item for item in decoded if isinstance(item, str)]
    return ["banner", "sound", "browser", "toast"]
```

并在 import 区加 `import json`（如果还没有的话）。

- [ ] **Step 5: 跑测试**

```bash
python -m pytest tests/test_monitor_api.py -v
```

Expected: 全部通过。

- [ ] **Step 6: 提交**

```bash
git add app/main.py app/monitoring.py tests/test_monitor_api.py
git commit -m "feat: surface notification_channels in monitor alert payload"
```

---

## Task 7: `Settings.monitor_notification_sound_enabled`

**Files:**
- Modify: `app/settings.py`
- Test: 暂不增加单独测试，下一 Task 在 notifier 测试里覆盖

- [ ] **Step 1: 修改 `app/settings.py`**

在 `Settings` 数据类里加：

```python
    monitor_notification_sound_enabled: bool = field(
        default_factory=lambda: _env_flag("MONITOR_NOTIFICATION_SOUND_ENABLED", "1")
    )
```

放在 `monitor_realert_cooldown_enabled` 之后。

- [ ] **Step 2: 简单验证**

```bash
python -c "from app.settings import Settings; print(Settings().monitor_notification_sound_enabled)"
```

Expected: `True`（环境没设置时默认开）。

- [ ] **Step 3: 提交**

```bash
git add app/settings.py
git commit -m "feat: add MONITOR_NOTIFICATION_SOUND_ENABLED setting"
```

---

## Task 8: `send_monitor_hit_alert(channels=...)` + winrt 优先

**Files:**
- Modify: `app/notifier.py`
- Modify: `tests/test_notifier.py`

- [ ] **Step 1: 写测试 (6 个)**

文件顶部 import 加：

```python
from app.notifier import (
    build_monitor_target_url,
    build_notification_message,
    send_desktop_notification,
    send_monitor_hit_alert,
)
import app.notifier as notifier_module
```

文件末尾追加：

```python
class RecordingWindowsToast:
    def __init__(self, return_value: bool = True) -> None:
        self.calls: list[dict[str, object]] = []
        self.return_value = return_value

    def __call__(self, title, message, launch_url):
        self.calls.append({"title": title, "message": message, "launch_url": launch_url})
        return self.return_value


def test_send_monitor_hit_alert_uses_winrt_toast_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(notifier_module.os, "name", "nt")
    winrt = RecordingWindowsToast(return_value=True)
    monkeypatch.setattr(notifier_module, "_send_windows_toast", winrt)
    plyer_calls: list[dict] = []
    monkeypatch.setattr(notifier_module, "notification", type("P", (), {
        "notify": classmethod(lambda cls, **kw: plyer_calls.append(kw)),
    }))
    sound_calls: list[bool] = []
    monkeypatch.setattr(
        notifier_module,
        "_start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert result is True
    assert plyer_calls == []
    assert len(winrt.calls) == 1
    assert winrt.calls[0]["launch_url"].endswith("monitor_task_id=3&monitor_hit_id=9")
    assert sound_calls == [True]


def test_send_monitor_hit_alert_falls_back_to_plyer_when_winrt_fails(monkeypatch) -> None:
    monkeypatch.setattr(notifier_module.os, "name", "nt")
    monkeypatch.setattr(notifier_module, "_send_windows_toast", RecordingWindowsToast(return_value=False))
    plyer_calls: list[dict] = []
    monkeypatch.setattr(notifier_module, "notification", type("P", (), {
        "notify": classmethod(lambda cls, **kw: plyer_calls.append(kw)),
    }))
    monkeypatch.setattr(notifier_module, "_start_monitor_hit_sound_thread", lambda: True)

    send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert len(plyer_calls) == 1


def test_send_monitor_hit_alert_skips_winrt_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(notifier_module.os, "name", "posix")
    winrt = RecordingWindowsToast(return_value=True)
    monkeypatch.setattr(notifier_module, "_send_windows_toast", winrt)
    plyer_calls: list[dict] = []
    monkeypatch.setattr(notifier_module, "notification", type("P", (), {
        "notify": classmethod(lambda cls, **kw: plyer_calls.append(kw)),
    }))
    monkeypatch.setattr(notifier_module, "_start_monitor_hit_sound_thread", lambda: True)

    send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert winrt.calls == []
    assert len(plyer_calls) == 1


def test_send_monitor_hit_alert_skips_sound_when_globally_disabled(monkeypatch) -> None:
    monkeypatch.setattr(notifier_module.os, "name", "posix")
    monkeypatch.setattr(notifier_module, "notification", type("P", (), {
        "notify": classmethod(lambda cls, **kw: None),
    }))
    sound_calls: list[bool] = []
    monkeypatch.setattr(
        notifier_module,
        "_start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )
    monkeypatch.setattr(notifier_module, "_should_play_sound", lambda: False)

    send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert sound_calls == []


def test_send_monitor_hit_alert_skips_sound_when_channel_off(monkeypatch) -> None:
    monkeypatch.setattr(notifier_module.os, "name", "posix")
    monkeypatch.setattr(notifier_module, "notification", type("P", (), {
        "notify": classmethod(lambda cls, **kw: None),
    }))
    sound_calls: list[bool] = []
    monkeypatch.setattr(
        notifier_module,
        "_start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
        channels={"banner", "browser", "toast"},
    )

    assert sound_calls == []


def test_send_monitor_hit_alert_skips_toast_when_channel_off(monkeypatch) -> None:
    monkeypatch.setattr(notifier_module.os, "name", "nt")
    winrt = RecordingWindowsToast(return_value=True)
    monkeypatch.setattr(notifier_module, "_send_windows_toast", winrt)
    plyer_calls: list[dict] = []
    monkeypatch.setattr(notifier_module, "notification", type("P", (), {
        "notify": classmethod(lambda cls, **kw: plyer_calls.append(kw)),
    }))
    sound_calls: list[bool] = []
    monkeypatch.setattr(
        notifier_module,
        "_start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
        channels={"banner", "sound", "browser"},
    )

    assert winrt.calls == []
    assert plyer_calls == []
    assert sound_calls == [True]
```

- [ ] **Step 2: 跑测试，确认全失败**

```bash
python -m pytest tests/test_notifier.py -v
```

Expected: 旧 4 个仍通过；新 6 个失败（`_send_windows_toast` / `_should_play_sound` 不存在，或 `channels` 参数不被识别）。

- [ ] **Step 3: 修改 `app/notifier.py`**

import 区加：

```python
from app.models import ALL_NOTIFICATION_CHANNELS, NotificationChannel
from app.settings import Settings
```

`send_monitor_hit_alert` 重写：

```python
def send_monitor_hit_alert(
    *,
    base_url: str,
    monitor_task_id: int,
    monitor_hit_id: int,
    origin_city: str,
    destination_city: str,
    departure_date: str | date | datetime,
    current_price: int,
    target_price: int,
    channels: set[str] | None = None,
) -> bool:
    effective_channels = (
        set(channels) if channels is not None else set(ALL_NOTIFICATION_CHANNELS)
    )
    target_url = build_monitor_target_url(base_url, monitor_task_id, monitor_hit_id)
    title, message = build_notification_message(
        origin_city,
        destination_city,
        current_price,
        target_price,
        departure_date=departure_date,
    )
    message_with_url = f"{message}\n打开本地页面查看：{target_url}"

    desktop_sent = False
    if "toast" in effective_channels:
        if os.name == "nt":
            desktop_sent = _send_windows_toast(title, message_with_url, target_url)
        if not desktop_sent:
            desktop_sent = _send_desktop_notification(
                title,
                message_with_url,
                timeout=20,
            )

    sound_started = False
    if "sound" in effective_channels and _should_play_sound():
        sound_started = _start_monitor_hit_sound_thread()

    return desktop_sent or sound_started
```

并在文件末尾追加：

```python
def _send_windows_toast(title: str, message: str, launch_url: str) -> bool:
    try:
        from winrt.windows.data.xml.dom import XmlDocument  # type: ignore[import-not-found]
        from winrt.windows.ui.notifications import (  # type: ignore[import-not-found]
            ToastNotification,
            ToastNotificationManager,
        )
    except Exception:
        try:
            from winsdk.windows.data.xml.dom import XmlDocument  # type: ignore[import-not-found]
            from winsdk.windows.ui.notifications import (  # type: ignore[import-not-found]
                ToastNotification,
                ToastNotificationManager,
            )
        except Exception:
            logger.exception("Windows toast backend unavailable")
            return False

    try:
        xml = XmlDocument()
        xml.load_xml(
            "<toast launch=\"{url}\"><visual><binding template=\"ToastGeneric\">"
            "<text>{title}</text><text>{message}</text>"
            "</binding></visual></toast>".format(
                url=_xml_escape(launch_url),
                title=_xml_escape(title),
                message=_xml_escape(message),
            )
        )
        notifier = ToastNotificationManager.create_toast_notifier_with_id("Fly Ticket")
        notifier.show(ToastNotification(xml))
        return True
    except Exception:
        logger.exception("Windows toast failed")
        return False


def _xml_escape(raw: str) -> str:
    return (
        raw.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
    )


def _should_play_sound() -> bool:
    return Settings().monitor_notification_sound_enabled
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest tests/test_notifier.py -v
```

Expected: 全部 passed（含原 4 个 + 新 6 个）。

- [ ] **Step 5: 跑 scheduler 测试，确认旧调用兼容**

```bash
python -m pytest tests/test_monitor_runner.py -v
```

Expected: 全部 passed（`send_monitor_hit_alert` 因为 `channels=None` 兜底为全集，原 monkeypatch 的 `fake_alert(**kwargs)` 仍兼容）。

- [ ] **Step 6: 提交**

```bash
git add app/notifier.py tests/test_notifier.py
git commit -m "feat: route monitor hits through winrt + channels filter"
```

---

## Task 9: 调度器透传任务 channels

**Files:**
- Modify: `app/monitor_scheduler.py`
- Modify: `tests/test_monitor_runner.py`

- [ ] **Step 1: 写失败测试**

`tests/test_monitor_runner.py` 末尾追加：

```python
def test_monitor_scheduler_passes_task_channels_to_alert(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)
    task = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
            notification_channels=["banner"],
        ),
    )
    update_monitor_runtime_state(
        settings,
        task.id,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )

    scraper = _StubScraper(_build_flights(380, 420))
    captured: list[dict] = []

    def fake_alert(**kwargs) -> bool:
        captured.append(kwargs)
        return True

    monkeypatch.setattr("app.monitor_scheduler.send_monitor_hit_alert", fake_alert)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    assert len(captured) == 1
    assert captured[0]["channels"] == {"banner"}
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
python -m pytest tests/test_monitor_runner.py::test_monitor_scheduler_passes_task_channels_to_alert -v
```

Expected: `KeyError: 'channels'`（调度器未传）。

- [ ] **Step 3: 修改 `app/monitor_scheduler.py`**

定位 `send_monitor_hit_alert(...)` 调用（约 91 行），在最后一个参数 `target_price=task.target_price,` 之后加：

```python
                            channels=set(task.notification_channels),
```

调用最终类似：

```python
                    notification_sent = (
                        send_monitor_hit_alert(
                            base_url=self.settings.app_base_url,
                            monitor_task_id=task.id,
                            monitor_hit_id=hit.id,
                            origin_city=task.origin_city,
                            destination_city=task.destination_city,
                            departure_date=task.departure_date,
                            current_price=evaluation.lowest_price,
                            target_price=task.target_price,
                            channels=set(task.notification_channels),
                        )
                        is not False
                    )
```

- [ ] **Step 4: 跑全部 scheduler 测试**

由于旧测试里 `_capture_monitor_alerts` 的 fake 接受 `**kwargs`，不需要改它们的断言。但 `test_monitor_scheduler_records_first_hit_and_updates_runtime_state` 里有完整 `assert alerts == [{...}]` 字典等值断言，需要加 `"channels": {"banner","sound","browser","toast"}` 一项。

修改 `tests/test_monitor_runner.py` 中所有形如：

```python
    assert alerts == [
        {
            "base_url": "http://127.0.0.1:8000",
            "monitor_task_id": task.id,
            ...
            "target_price": 400,
        }
    ]
```

的字面量断言，在 `"target_price": 400,` 之后追加：

```python
            "channels": {"banner", "sound", "browser", "toast"},
```

涉及位置：`test_monitor_scheduler_records_first_hit_and_updates_runtime_state` 周围以及任何形如 `assert alerts == [...]` 的字面量。其它 `assert len(alerts) == 1` 等不需要改。

跑：

```bash
python -m pytest tests/test_monitor_runner.py -v
```

Expected: 全部 passed。

- [ ] **Step 5: 提交**

```bash
git add app/monitor_scheduler.py tests/test_monitor_runner.py
git commit -m "feat: pass task notification_channels to alert sender"
```

---

## Task 10: 前端默认行为修复（去门控、去 hidden 短路、按通道分发）

**Files:**
- Modify: `app/static/app.js`

- [ ] **Step 1: 删除 `enableMonitorAlertStorage`、`monitorAlertsAreEnabled`、`monitorAlertsEnabledStorageKey`**

把 `app/static/app.js` 中的这三行常量声明（25-26 行附近）：

```js
const lastSeenMonitorHitStorageKey = "flyTicketLastSeenMonitorHitId";
const monitorAlertsEnabledStorageKey = "flyTicketMonitorAlertsEnabled";
```

改为：

```js
const lastSeenMonitorHitStorageKey = "flyTicketLastSeenMonitorHitId";
const notificationChannelsStorageKey = "flyTicketNotificationChannels";
const ALL_NOTIFICATION_CHANNELS = ["banner", "sound", "browser", "toast"];
```

删除以下函数（173-187 行附近）：

```js
function enableMonitorAlertStorage() { ... }
function monitorAlertsAreEnabled() { ... }
```

- [ ] **Step 2: 替换 `requestMonitorAlertPermission`**

把整个 `requestMonitorAlertPermission` 函数替换为：

```js
async function requestMonitorAlertPermission() {
    playMonitorAlertTone();

    if (!("Notification" in window)) {
        searchSummaryElement.textContent = "浏览器不支持系统通知，仍会保留页面提醒和本机声音。";
        return;
    }

    if (Notification.permission === "default") {
        await Notification.requestPermission();
    }

    searchSummaryElement.textContent = Notification.permission === "granted"
        ? "已开启系统通知，命中时浏览器图标会在任务栏闪烁。"
        : "浏览器通知未开启，查到票后仍会显示页面横幅和本机声音。";
}
```

- [ ] **Step 3: 替换 `showBrowserMonitorNotification`**

```js
function showBrowserMonitorNotification(alert) {
    if (
        !("Notification" in window)
        || Notification.permission !== "granted"
    ) {
        return;
    }

    try {
        const notification = new Notification(alert.title, {
            body: alert.message,
            tag: `fly-ticket-hit-${alert.hit_id}`,
            renotify: true,
            requireInteraction: true,
        });
        notification.onclick = () => {
            window.focus();
            window.location.href = alert.url;
        };
    } catch (error) {
        console.warn("Browser notification failed", error);
    }
}
```

- [ ] **Step 4: 新增通道存取工具与交集函数**

在 `playMonitorAlertTone` 函数定义之前插入：

```js
function readGlobalNotificationChannels() {
    try {
        const raw = localStorage.getItem(notificationChannelsStorageKey);
        if (!raw) {
            return new Set(ALL_NOTIFICATION_CHANNELS);
        }
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) {
            return new Set(ALL_NOTIFICATION_CHANNELS);
        }
        const filtered = parsed.filter((item) => ALL_NOTIFICATION_CHANNELS.includes(item));
        return new Set(filtered);
    } catch (error) {
        return new Set(ALL_NOTIFICATION_CHANNELS);
    }
}

function writeGlobalNotificationChannels(channels) {
    try {
        localStorage.setItem(
            notificationChannelsStorageKey,
            JSON.stringify(Array.from(channels))
        );
    } catch (error) {
        // localStorage 不可用时仅放弃，不打断。
    }
}

function effectiveChannelsFor(alert) {
    const taskChannels = Array.isArray(alert.notification_channels) && alert.notification_channels.length > 0
        ? alert.notification_channels
        : ALL_NOTIFICATION_CHANNELS;
    const taskSet = new Set(taskChannels);
    const globalSet = readGlobalNotificationChannels();
    return new Set(taskChannels.filter((item) => taskSet.has(item) && globalSet.has(item)));
}
```

- [ ] **Step 5: 替换 `pollMonitorAlerts` 的分发逻辑**

把现有 `pollMonitorAlerts` 替换为：

```js
async function pollMonitorAlerts() {
    try {
        const payload = await requestJson("/api/monitor-alerts?after_id=" + encodeURIComponent(String(getLastSeenMonitorHitId())));
        const alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
        if (alerts.length === 0) {
            return;
        }

        const latestAlert = alerts[alerts.length - 1];
        const maxHitId = alerts.reduce((maxId, alert) => Math.max(maxId, Number(alert.hit_id) || 0), getLastSeenMonitorHitId());
        setLastSeenMonitorHitId(maxHitId);
        const effective = effectiveChannelsFor(latestAlert);
        if (effective.has("banner")) {
            showMonitorAlertBanner(latestAlert);
        }
        if (effective.has("sound")) {
            playMonitorAlertTone();
        }
        if (effective.has("browser")) {
            showBrowserMonitorNotification(latestAlert);
        }
        searchSummaryElement.textContent = latestAlert.message;
    } catch (error) {
        // Polling should stay quiet so normal searching and editing are not interrupted.
    }
}
```

- [ ] **Step 6: 浏览器手动验收**

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，确认：
- 首页能正常打开
- `console` 无报错

按 Ctrl+C 终止。

- [ ] **Step 7: 提交**

```bash
git add app/static/app.js
git commit -m "fix: drop browser alert gating and dispatch by channel intersection"
```

---

## Task 11: 顶部全局通道下拉 + 任务级通道下拉

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/app.css`
- Modify: `app/static/app.js`

- [ ] **Step 1: 在模板里加全局下拉**

打开 `app/templates/index.html`，把 `guide-actions` 这一段：

```html
                <div class="guide-actions">
                    <button type="button" class="secondary-action" data-dashboard-action="search">去搜索</button>
                    <button type="button" class="primary-action" id="enable-monitor-alerts" data-dashboard-action="enable-alerts">启用提醒</button>
                </div>
```

改为：

```html
                <div class="guide-actions">
                    <button type="button" class="secondary-action" data-dashboard-action="search">去搜索</button>
                    <button type="button" class="primary-action" id="enable-monitor-alerts" data-dashboard-action="enable-alerts">启用提醒</button>
                    <details class="notification-channels-dropdown" id="global-notification-channels">
                        <summary class="secondary-action">提醒方式</summary>
                        <div class="notification-channels-panel" role="group" aria-label="全局提醒方式">
                            <label><input type="checkbox" value="banner" data-channel="banner"><span>页面横幅</span></label>
                            <label><input type="checkbox" value="sound" data-channel="sound"><span>网页声音</span></label>
                            <label><input type="checkbox" value="browser" data-channel="browser"><span>浏览器通知 / 任务栏闪烁</span></label>
                            <label><input type="checkbox" value="toast" data-channel="toast"><span>桌面 toast</span></label>
                        </div>
                    </details>
                </div>
```

- [ ] **Step 2: 在监控表单里加任务级下拉**

打开 `app/templates/index.html`，在监控表单 `<form id="monitor-form" ...>` 内 `unchanged_reminder_interval_minutes` 那一段 `<label>...</label>` 之后、`<div class="form-actions">` 之前，插入：

```html
                        <details class="notification-channels-dropdown notification-channels-inline">
                            <summary class="secondary-action">提醒方式（仅这个监控）</summary>
                            <div class="notification-channels-panel" role="group" aria-label="任务提醒方式">
                                <label><input type="checkbox" name="notification_channels" value="banner"><span>页面横幅</span></label>
                                <label><input type="checkbox" name="notification_channels" value="sound"><span>网页声音</span></label>
                                <label><input type="checkbox" name="notification_channels" value="browser"><span>浏览器通知 / 任务栏闪烁</span></label>
                                <label><input type="checkbox" name="notification_channels" value="toast"><span>桌面 toast</span></label>
                            </div>
                        </details>
```

- [ ] **Step 3: 加 CSS**

在 `app/static/app.css` 末尾追加：

```css
.notification-channels-dropdown {
    position: relative;
    display: inline-block;
}

.notification-channels-dropdown > summary {
    list-style: none;
    cursor: pointer;
    user-select: none;
}

.notification-channels-dropdown > summary::-webkit-details-marker {
    display: none;
}

.notification-channels-panel {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    z-index: 10;
    min-width: 220px;
    padding: 12px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.12);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.notification-channels-panel label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9rem;
}

.notification-channels-inline {
    grid-column: 1 / -1;
}

.notification-channels-inline .notification-channels-panel {
    position: static;
    box-shadow: none;
    border: none;
    padding: 0;
}
```

- [ ] **Step 4: 在 JS 里连接全局下拉**

打开 `app/static/app.js`，在文件底部 `pollMonitorAlerts();` 之前，但在 `setMonitorDetail(null);` 之后插入：

```js
function syncGlobalNotificationChannelsUI() {
    const channels = readGlobalNotificationChannels();
    document.querySelectorAll("#global-notification-channels input[data-channel]").forEach((input) => {
        input.checked = channels.has(input.dataset.channel);
    });
}

async function persistGlobalNotificationChannels(channels) {
    try {
        await requestJson("/api/notification-settings", {
            method: "PUT",
            body: JSON.stringify({ channels: Array.from(channels) }),
        });
    } catch (error) {
        // 静默失败：localStorage 仍能保留本机选择
    }
}

(function initializeGlobalNotificationChannels() {
    const root = document.querySelector("#global-notification-channels");
    if (!root) {
        return;
    }
    syncGlobalNotificationChannelsUI();

    root.addEventListener("change", (event) => {
        const input = event.target.closest("input[data-channel]");
        if (!input) {
            return;
        }
        const channels = readGlobalNotificationChannels();
        if (input.checked) {
            channels.add(input.dataset.channel);
        } else {
            channels.delete(input.dataset.channel);
        }
        writeGlobalNotificationChannels(channels);
        persistGlobalNotificationChannels(channels);
    });

    requestJson("/api/notification-settings").then((payload) => {
        const serverChannels = Array.isArray(payload?.channels) ? payload.channels : null;
        if (!serverChannels) {
            return;
        }
        const local = readGlobalNotificationChannels();
        if (local.size === ALL_NOTIFICATION_CHANNELS.length && local.size === serverChannels.length) {
            return;
        }
        writeGlobalNotificationChannels(new Set(serverChannels));
        syncGlobalNotificationChannelsUI();
    }).catch(() => {});
})();
```

- [ ] **Step 5: 在 JS 里连接任务级下拉**

修改 `getMonitorPayload`：

```js
function getMonitorPayload() {
    if (!monitorForm) {
        return null;
    }

    const formData = new FormData(monitorForm);
    const checkedChannels = Array.from(
        monitorForm.querySelectorAll('input[name="notification_channels"]:checked')
    ).map((input) => input.value);
    return {
        origin_city: String(formData.get("origin_city") || "").trim(),
        destination_city: String(formData.get("destination_city") || "").trim(),
        departure_date: String(formData.get("departure_date") || ""),
        target_price: Number(formData.get("target_price") || 0),
        check_interval_minutes: Number(formData.get("check_interval_minutes") || 30),
        reminder_policy: String(formData.get("reminder_policy") || "interval"),
        unchanged_reminder_interval_minutes: Number(formData.get("unchanged_reminder_interval_minutes") || 360),
        departure_time_filters: Array.from(activeFilters.departure_time_filters),
        flight_attribute_filters: Array.from(activeFilters.flight_attribute_filters),
        airline_filters: Array.from(activeFilters.airline_filters),
        notification_channels: checkedChannels.length > 0 ? checkedChannels : ALL_NOTIFICATION_CHANNELS.slice(),
    };
}
```

修改 `resetMonitorForm`，在 `delete monitorForm.dataset.monitorId;` 之前加：

```js
    monitorForm.querySelectorAll('input[name="notification_channels"]').forEach((input) => {
        input.checked = true;
    });
```

修改 `fillMonitorForm`，在 `replaceFilters(...)` 之前加：

```js
    const taskChannels = Array.isArray(record.notification_channels) && record.notification_channels.length > 0
        ? new Set(record.notification_channels)
        : new Set(ALL_NOTIFICATION_CHANNELS);
    monitorForm.querySelectorAll('input[name="notification_channels"]').forEach((input) => {
        input.checked = taskChannels.has(input.value);
    });
```

修改 `handleMonitorAction` 中 `toggle` 分支构造的 PUT 体——找到 `airline_filters: record.airline_filters || [],`，在它后面加：

```js
                    notification_channels: record.notification_channels || ALL_NOTIFICATION_CHANNELS.slice(),
```

最后，确保表单初次加载时所有任务级 checkbox 默认勾上：直接给模板里每个 checkbox 加 `checked` 属性。

回到 `app/templates/index.html` 表单 checkbox 那段，把 4 行 `<input type="checkbox" name="notification_channels" value="...">` 都改成：

```html
                                <input type="checkbox" name="notification_channels" value="banner" checked>
                                <input type="checkbox" name="notification_channels" value="sound" checked>
                                <input type="checkbox" name="notification_channels" value="browser" checked>
                                <input type="checkbox" name="notification_channels" value="toast" checked>
```

（保持 label 文案不变。）

- [ ] **Step 6: 浏览器手动验收**

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 顶部点开"提醒方式"，4 个 checkbox 都勾上。
- 取消"网页声音"，刷新页面后仍然是未勾。
- 监控任务表单展开"提醒方式（仅这个监控）"，新建任务保存后 GET `/api/monitors/<id>` 看 `notification_channels` 是表单勾选。

Ctrl+C 终止。

- [ ] **Step 7: 跑全部测试**

```bash
python -m pytest -v
```

Expected: 所有通过。

- [ ] **Step 8: 提交**

```bash
git add app/templates/index.html app/static/app.css app/static/app.js
git commit -m "feat: add global and per-task notification channel dropdowns"
```

---

## Task 12: 文档与验收手动测试

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 修改 README "提醒规则" 一节**

把 README "提醒规则" 这一节末尾追加：

```markdown
### 选择提醒方式

页面顶部"提醒方式"下拉里可以勾选四种通道：

- 页面横幅
- 网页声音
- 浏览器通知（命中时 Windows 任务栏图标橙色闪烁 + 右下角原生 toast）
- 桌面 toast（启动窗口在后台跑也会弹，由 Windows winrt 优先发送，不可用时自动回落 plyer）

每个监控任务的"提醒方式（仅这个监控）"下拉与全局设置取交集。如果想暂时让所有任务都不响声音，只需顶部取消"网页声音"；这条全局开关不会改你每个监控的勾选。

另有一个 `.env` 开关用于全局静音：

```env
MONITOR_NOTIFICATION_SOUND_ENABLED=0
```

设为 0 时即便上面两层都勾上声音，也不会响——适合需要彻底安静的场景。
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: describe notification channel dropdown and sound override"
```

---

## 自检 / 全套测试

最后跑：

```bash
python -m pytest -v
```

Expected: 全部通过。

手动浏览器验收清单：

- [ ] 顶部新增"提醒方式"按钮可展开 4 个 checkbox
- [ ] 任务表单新增"提醒方式（仅这个监控）"折叠面板
- [ ] 新建任务默认 4 项全勾
- [ ] 取消全局某一项，刷新页面仍保持
- [ ] 任务 PUT 后回读 `notification_channels` 与勾选一致
- [ ] `GET /api/monitor-alerts` 返回 `notification_channels` 字段
- [ ] Windows 上命中时浏览器任务栏闪烁（前提：曾点过"启用提醒"授权）
- [ ] 取消全局"桌面 toast" → 命中时 Python 端不弹 toast
- [ ] 取消任务"网页声音" → 命中时只静默命中横幅 + 浏览器通知
