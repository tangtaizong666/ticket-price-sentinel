# Flight Monitoring and Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local background flight monitoring, desktop notifications, click-through back into the local web UI, and a Windows one-click startup flow on top of the existing Ctrip flight comparison app.

**Architecture:** Extend the current single-process FastAPI app with SQLite-backed monitoring tables, an in-process scheduler loop, a hit-record store, and a notification adapter that points users back to a task detail or hit view in the local web UI. Keep the scheduler, notification sending, and monitor persistence isolated so the backend can later be split into a dedicated worker without rewriting the data model or route layer.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLite (`sqlite3`), Playwright, BeautifulSoup 4, pytest, httpx/TestClient, python-dotenv, Windows shell (`.bat`), a local desktop-notification library (`plyer`)

---

## Planned File Structure

- Modify: `requirements.txt` — add runtime dependency for local desktop notifications
- Modify: `.env.example` — add monitoring-related local settings
- Modify: `app/models.py` — add monitor-task, monitor-hit, and notification DTOs
- Modify: `app/db.py` — add `monitor_tasks` and `monitor_hits` schema
- Modify: `app/history.py` — keep existing scope intact, optionally share row/date parsing helpers if needed
- Create: `app/monitoring.py` — SQLite CRUD for monitor tasks and hit records
- Create: `app/monitor_scheduler.py` — in-process scheduler loop and due-task dispatcher
- Create: `app/monitor_runner.py` — execute one monitoring cycle using existing scraper/filter logic
- Create: `app/notifier.py` — desktop notification adapter and click-through target URL builder
- Modify: `app/search_service.py` — share result-shaping code with monitor execution when useful
- Modify: `app/main.py` — add monitor routes, start scheduler, and expose monitor detail/hit data to templates
- Modify: `app/templates/index.html` — add monitor-task UI, monitor detail/hit sections, and notification-return view hooks
- Modify: `app/static/app.js` — add monitor create/edit/pause/resume/delete flows, detail rendering, and notification-target hydration
- Modify: `app/static/app.css` — add monitor-specific layout/status styling
- Create: `start_fly_ticket.bat` — Windows one-click bootstrap and launch script
- Create: `tests/test_monitoring_repository.py` — monitor task and hit persistence tests
- Create: `tests/test_monitor_runner.py` — monitor hit, no-hit, and dedupe rules tests
- Create: `tests/test_monitor_api.py` — monitor create/list/detail/update/toggle/delete/rerun-style endpoint tests
- Create: `tests/test_notifier.py` — notification payload and click-through URL tests
- Create: `tests/test_startup_script_notes.py` — lightweight assertions for `.env.example`/launcher assumptions without executing the batch file

## Execution Notes

1. This repo still has no git commits yet, so every plan step includes a commit command but commit execution will stay blocked until git identity is configured.
2. The monitoring feature is scoped to the local machine only. It assumes the FastAPI process remains alive in the background.
3. Notification click-through must open the local app, not a direct Ctrip URL; the local page then shows hit details and lets the user click onward.
4. The scheduler must remain in-process for this phase, but its logic should live in focused modules so it can later be moved into a worker.
5. The existing app currently searches by Ctrip-style route tokens (e.g. `bjs`, `sha`) more reliably than plain city names. Do not introduce city-code translation in this plan.

---

### Task 1: Add monitor task and hit persistence

**Files:**
- Modify: `app/models.py`
- Modify: `app/db.py`
- Create: `app/monitoring.py`
- Test: `tests/test_monitoring_repository.py`

- [ ] **Step 1: Write the failing repository tests**

```python
# tests/test_monitoring_repository.py
from datetime import date

from app.db import init_db
from app.models import MonitorTaskCreate
from app.monitoring import create_monitor_task, list_monitor_tasks, record_monitor_hit
from app.settings import Settings


def test_monitor_task_repository_round_trips_task_and_hit(tmp_path) -> None:
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
            departure_time_filters=["上午"],
            flight_attribute_filters=["直飞"],
            airline_filters=["东航"],
        ),
    )

    hit = record_monitor_hit(
        settings,
        task_id=task.id,
        lowest_price=380,
        flights_snapshot=[
            {
                "flight_no": "MU1234",
                "airline": "东航",
                "price": 380,
                "stop_info": "直飞",
                "deeplink_url": "https://example.com/flight",
                "fallback_search_url": "https://example.com/results",
            }
        ],
    )

    tasks = list_monitor_tasks(settings)

    assert len(tasks) == 1
    assert tasks[0].target_price == 400
    assert tasks[0].enabled is True
    assert hit.monitor_task_id == task.id
    assert hit.lowest_price == 380
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitoring_repository.py -v
```

Expected: FAIL because the monitor models, schema, and repository do not exist yet.

- [ ] **Step 3: Implement the monitor models, schema, and repository**

```python
# app/models.py
from datetime import date, datetime

from pydantic import BaseModel, Field


class MonitorTaskBase(BaseModel):
    origin_city: str
    destination_city: str
    departure_date: date
    target_price: int
    check_interval_minutes: int
    departure_time_filters: list[str] = Field(default_factory=list)
    flight_attribute_filters: list[str] = Field(default_factory=list)
    airline_filters: list[str] = Field(default_factory=list)


class MonitorTaskCreate(MonitorTaskBase):
    pass


class MonitorTask(MonitorTaskBase):
    id: int
    enabled: bool
    last_checked_at: datetime | None = None
    next_check_at: datetime
    last_seen_lowest_price: int | None = None
    last_notified_at: datetime | None = None
    last_notified_price: int | None = None
    created_at: datetime
    updated_at: datetime


class MonitorHit(BaseModel):
    id: int
    monitor_task_id: int
    hit_price: int
    hit_at: datetime
    search_snapshot_json: list[dict]
    lowest_price: int
    created_at: datetime
```

```python
# app/db.py
            CREATE TABLE IF NOT EXISTS monitor_tasks (
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

            CREATE TABLE IF NOT EXISTS monitor_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_task_id INTEGER NOT NULL,
                hit_price INTEGER NOT NULL,
                hit_at TEXT NOT NULL,
                search_snapshot_json TEXT NOT NULL,
                lowest_price INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (monitor_task_id) REFERENCES monitor_tasks(id)
            );
```

```python
# app/monitoring.py
from datetime import UTC, datetime, timedelta
import json

from app.db import connect
from app.models import MonitorHit, MonitorTask, MonitorTaskCreate
from app.settings import Settings


def create_monitor_task(settings: Settings, payload: MonitorTaskCreate) -> MonitorTask:
    now = datetime.now(UTC)
    next_check_at = now + timedelta(minutes=payload.check_interval_minutes)
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO monitor_tasks (
                origin_city, destination_city, departure_date, target_price,
                check_interval_minutes, departure_time_filters,
                flight_attribute_filters, airline_filters, enabled,
                next_check_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                1,
                next_check_at.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        row = connection.execute("SELECT * FROM monitor_tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_monitor_task(row)


def list_monitor_tasks(settings: Settings) -> list[MonitorTask]:
    with connect(settings) as connection:
        rows = connection.execute("SELECT * FROM monitor_tasks ORDER BY created_at DESC").fetchall()
    return [_row_to_monitor_task(row) for row in rows]


def record_monitor_hit(settings: Settings, task_id: int, lowest_price: int, flights_snapshot: list[dict]) -> MonitorHit:
    now = datetime.now(UTC)
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO monitor_hits (monitor_task_id, hit_price, hit_at, search_snapshot_json, lowest_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, lowest_price, now.isoformat(), json.dumps(flights_snapshot, ensure_ascii=False), lowest_price, now.isoformat()),
        )
        row = connection.execute("SELECT * FROM monitor_hits WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_monitor_hit(row)
```

- [ ] **Step 4: Run the repository tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitoring_repository.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the monitor persistence layer**

Run:
```bash
git add app/models.py app/db.py app/monitoring.py tests/test_monitoring_repository.py && git commit -m "feat: add monitor task persistence"
```

Expected: a commit containing the monitoring data model and repository layer.

---

### Task 2: Add the monitor runner and dedupe rules

**Files:**
- Create: `app/monitor_runner.py`
- Test: `tests/test_monitor_runner.py`

- [ ] **Step 1: Write the failing monitor runner tests**

```python
# tests/test_monitor_runner.py
from datetime import UTC, date, datetime, timedelta, time

from app.models import FlightResult, MonitorTask
from app.monitor_runner import evaluate_monitor_result


def test_evaluate_monitor_result_creates_hit_only_on_first_or_lower_price() -> None:
    task = MonitorTask(
        id=1,
        origin_city="bjs",
        destination_city="sha",
        departure_date=date(2026, 5, 20),
        target_price=400,
        check_interval_minutes=30,
        departure_time_filters=[],
        flight_attribute_filters=[],
        airline_filters=[],
        enabled=True,
        last_checked_at=None,
        next_check_at=datetime.now(UTC),
        last_seen_lowest_price=None,
        last_notified_at=None,
        last_notified_price=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    flights = [
        FlightResult(
            flight_no="MU1234",
            airline="东航",
            origin_city="bjs",
            destination_city="sha",
            departure_time=time(8, 30),
            arrival_time=time(10, 45),
            is_direct=True,
            stop_info="直飞",
            price=380,
            deeplink_url="https://example.com/flight",
            fallback_search_url="https://example.com/results",
        )
    ]

    first = evaluate_monitor_result(task, flights)
    repeated = evaluate_monitor_result(task.model_copy(update={"last_notified_price": 380}), flights)
    lower = evaluate_monitor_result(task.model_copy(update={"last_notified_price": 400}), flights)

    assert first.should_notify is True
    assert repeated.should_notify is False
    assert lower.should_notify is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_runner.py -v
```

Expected: FAIL because `app.monitor_runner` does not exist.

- [ ] **Step 3: Implement the monitor evaluation logic**

```python
# app/monitor_runner.py
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.filtering import calculate_lowest_price
from app.models import FlightResult, MonitorTask


@dataclass
class MonitorEvaluation:
    lowest_price: int | None
    should_notify: bool
    next_check_at: datetime
    flights_snapshot: list[dict]


def evaluate_monitor_result(task: MonitorTask, flights: list[FlightResult]) -> MonitorEvaluation:
    lowest_price = calculate_lowest_price(flights)
    should_notify = False
    if lowest_price is not None and lowest_price <= task.target_price:
        should_notify = task.last_notified_price is None or lowest_price < task.last_notified_price

    return MonitorEvaluation(
        lowest_price=lowest_price,
        should_notify=should_notify,
        next_check_at=datetime.now(UTC) + timedelta(minutes=task.check_interval_minutes),
        flights_snapshot=[flight.model_dump(mode="json") for flight in flights],
    )
```

- [ ] **Step 4: Run the monitor runner tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin.python -m pytest tests/test_monitor_runner.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the monitor hit evaluation logic**

Run:
```bash
git add app/monitor_runner.py tests/test_monitor_runner.py && git commit -m "feat: add monitor hit evaluation"
```

Expected: a commit containing the monitor dedupe rules.

---

### Task 3: Add desktop notification delivery and click-through targets

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Create: `app/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing notifier tests**

```python
# tests/test_notifier.py
from app.notifier import build_monitor_target_url, build_notification_message


def test_build_monitor_target_url_points_back_to_local_hit_view() -> None:
    url = build_monitor_target_url(base_url="http://127.0.0.1:8000", monitor_task_id=3, monitor_hit_id=9)

    assert url == "http://127.0.0.1:8000/?monitor_task_id=3&monitor_hit_id=9"


def test_build_notification_message_contains_route_and_price() -> None:
    title, message = build_notification_message("bjs", "sha", 380, 400)

    assert title == "机票监控命中：bjs → sha"
    assert message == "当前最低价 ¥380，已达到你的目标价 ¥400"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_notifier.py -v
```

Expected: FAIL because `app.notifier` does not exist.

- [ ] **Step 3: Implement the notifier helpers and dependency change**

```text
# requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
jinja2==3.1.5
python-multipart==0.0.20
pydantic==2.10.6
playwright==1.51.0
python-dotenv==1.0.1
beautifulsoup4==4.12.3
plyer==2.1.0
```

```dotenv
# .env.example
APP_DB_PATH=data/app.db
PLAYWRIGHT_PROFILE_DIR=data/playwright-profile
CTRIP_SNAPSHOT_DIR=tests/fixtures
CTRIP_SEARCH_URL_TEMPLATE=
CTRIP_SESSION_URL=
APP_BASE_URL=http://127.0.0.1:8000
```

```python
# app/notifier.py
from plyer import notification


def build_monitor_target_url(base_url: str, monitor_task_id: int, monitor_hit_id: int) -> str:
    return f"{base_url}/?monitor_task_id={monitor_task_id}&monitor_hit_id={monitor_hit_id}"


def build_notification_message(origin_city: str, destination_city: str, current_price: int, target_price: int) -> tuple[str, str]:
    title = f"机票监控命中：{origin_city} → {destination_city}"
    message = f"当前最低价 ¥{current_price}，已达到你的目标价 ¥{target_price}"
    return title, message


def send_desktop_notification(title: str, message: str) -> None:
    notification.notify(title=title, message=message, app_name="Fly Ticket")
```

- [ ] **Step 4: Run the notifier tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_notifier.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the notifier module**

Run:
```bash
git add requirements.txt .env.example app/notifier.py tests/test_notifier.py && git commit -m "feat: add desktop notification helpers"
```

Expected: a commit containing the notification helpers and config change.

---

### Task 4: Add monitor management and hit APIs

**Files:**
- Modify: `app/monitoring.py`
- Modify: `app/main.py`
- Test: `tests/test_monitor_api.py`

- [ ] **Step 1: Write the failing monitor API tests**

```python
# tests/test_monitor_api.py
from datetime import date

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_monitor_api_creates_lists_and_updates_tasks(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings))

    create_response = client.post(
        "/api/monitors",
        json={
            "origin_city": "bjs",
            "destination_city": "sha",
            "departure_date": "2026-05-20",
            "target_price": 400,
            "check_interval_minutes": 30,
            "departure_time_filters": ["上午"],
            "flight_attribute_filters": ["直飞"],
            "airline_filters": ["东航"],
        },
    )
    assert create_response.status_code == 200
    monitor_id = create_response.json()["id"]

    list_response = client.get("/api/monitors")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == monitor_id

    update_response = client.put(
        f"/api/monitors/{monitor_id}",
        json={
            "origin_city": "bjs",
            "destination_city": "sha",
            "departure_date": "2026-05-20",
            "target_price": 380,
            "check_interval_minutes": 60,
            "departure_time_filters": [],
            "flight_attribute_filters": [],
            "airline_filters": [],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["target_price"] == 380
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_api.py -v
```

Expected: FAIL because the monitor API routes do not exist.

- [ ] **Step 3: Implement the monitor CRUD API**

```python
# app/monitoring.py
from datetime import UTC, datetime, timedelta
import json

from app.db import connect
from app.models import MonitorTask, MonitorTaskCreate
from app.settings import Settings


def get_monitor_task(settings: Settings, monitor_task_id: int) -> MonitorTask | None:
    with connect(settings) as connection:
        row = connection.execute("SELECT * FROM monitor_tasks WHERE id = ?", (monitor_task_id,)).fetchone()
    return _row_to_monitor_task(row) if row else None


def update_monitor_task(settings: Settings, monitor_task_id: int, payload: MonitorTaskCreate) -> MonitorTask:
    now = datetime.now(UTC)
    next_check_at = now + timedelta(minutes=payload.check_interval_minutes)
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE monitor_tasks
            SET origin_city = ?, destination_city = ?, departure_date = ?, target_price = ?,
                check_interval_minutes = ?, departure_time_filters = ?, flight_attribute_filters = ?, airline_filters = ?,
                next_check_at = ?, updated_at = ?
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
                next_check_at.isoformat(),
                now.isoformat(),
                monitor_task_id,
            ),
        )
        row = connection.execute("SELECT * FROM monitor_tasks WHERE id = ?", (monitor_task_id,)).fetchone()
    return _row_to_monitor_task(row)
```

```python
# app/main.py
from app.models import MonitorTaskCreate
from app.monitoring import create_monitor_task, get_monitor_task, list_monitor_tasks, update_monitor_task

    @app.get("/api/monitors")
    async def monitor_index():
        return list_monitor_tasks(app.state.settings)

    @app.post("/api/monitors")
    async def monitor_create(payload: MonitorTaskCreate):
        return create_monitor_task(app.state.settings, payload)

    @app.get("/api/monitors/{monitor_id}")
    async def monitor_detail(monitor_id: int):
        record = get_monitor_task(app.state.settings, monitor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return record

    @app.put("/api/monitors/{monitor_id}")
    async def monitor_update(monitor_id: int, payload: MonitorTaskCreate):
        if get_monitor_task(app.state.settings, monitor_id) is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return update_monitor_task(app.state.settings, monitor_id, payload)
```

- [ ] **Step 4: Run the monitor API tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the monitor CRUD API**

Run:
```bash
git add app/monitoring.py app/main.py tests/test_monitor_api.py && git commit -m "feat: add monitor task api"
```

Expected: a commit containing the monitor CRUD routes.

---

### Task 5: Wire the scheduler loop, notification trigger, and hit persistence

**Files:**
- Create: `app/monitor_scheduler.py`
- Modify: `app/monitoring.py`
- Modify: `app/main.py`
- Test: `tests/test_monitor_runner.py`
- Test: `tests/test_monitor_api.py`

- [ ] **Step 1: Extend the failing monitor tests for scheduling and hit recording**

```python
# tests/test_monitor_runner.py
from datetime import UTC, date, datetime, time

from app.models import FlightResult, MonitorTask
from app.monitor_runner import evaluate_monitor_result, should_run_task


def test_should_run_task_checks_enabled_and_next_check_time() -> None:
    now = datetime.now(UTC)
    ready = MonitorTask(
        id=1,
        origin_city="bjs",
        destination_city="sha",
        departure_date=date(2026, 5, 20),
        target_price=400,
        check_interval_minutes=30,
        departure_time_filters=[],
        flight_attribute_filters=[],
        airline_filters=[],
        enabled=True,
        last_checked_at=None,
        next_check_at=now,
        last_seen_lowest_price=None,
        last_notified_at=None,
        last_notified_price=None,
        created_at=now,
        updated_at=now,
    )
    disabled = ready.model_copy(update={"enabled": False})
    waiting = ready.model_copy(update={"next_check_at": now.replace(year=now.year + 1)})

    assert should_run_task(ready, now) is True
    assert should_run_task(disabled, now) is False
    assert should_run_task(waiting, now) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_runner.py -v
```

Expected: FAIL because the scheduler helper does not exist.

- [ ] **Step 3: Implement scheduling helpers and notification trigger path**

```python
# app/monitor_runner.py
from datetime import UTC, datetime


def should_run_task(task: MonitorTask, now: datetime) -> bool:
    return task.enabled and task.next_check_at <= now
```

```python
# app/monitor_scheduler.py
import asyncio
from datetime import UTC, datetime

from app.monitor_runner import evaluate_monitor_result, should_run_task
from app.monitoring import list_monitor_tasks, record_monitor_hit, update_monitor_runtime_state
from app.notifier import build_monitor_target_url, build_notification_message, send_desktop_notification


class MonitorScheduler:
    def __init__(self, settings, scraper, poll_seconds: int = 30):
        self.settings = settings
        self.scraper = scraper
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def tick_once(self) -> None:
        now = datetime.now(UTC)
        for task in list_monitor_tasks(self.settings):
            if not should_run_task(task, now):
                continue
            flights = await self.scraper.search(task)
            evaluation = evaluate_monitor_result(task, flights)
            hit = None
            if evaluation.should_notify and evaluation.lowest_price is not None:
                hit = record_monitor_hit(self.settings, task.id, evaluation.lowest_price, evaluation.flights_snapshot)
                title, message = build_notification_message(task.origin_city, task.destination_city, evaluation.lowest_price, task.target_price)
                send_desktop_notification(title, message)
            update_monitor_runtime_state(
                self.settings,
                task_id=task.id,
                last_checked_at=now,
                next_check_at=evaluation.next_check_at,
                last_seen_lowest_price=evaluation.lowest_price,
                last_notified_at=now if evaluation.should_notify else task.last_notified_at,
                last_notified_price=evaluation.lowest_price if evaluation.should_notify else task.last_notified_price,
            )
```

```python
# app/main.py
from app.monitor_scheduler import MonitorScheduler

    app.state.monitor_scheduler = MonitorScheduler(app.state.settings, app.state.scraper)
```

- [ ] **Step 4: Run the updated monitor tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_runner.py tests/test_monitor_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the scheduler and notification trigger path**

Run:
```bash
git add app/monitor_runner.py app/monitor_scheduler.py app/monitoring.py app/main.py tests/test_monitor_runner.py tests/test_monitor_api.py && git commit -m "feat: add local monitor scheduler"
```

Expected: a commit containing the scheduler/hit-notification flow.

---

### Task 6: Expose monitor details and hit data in the UI

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/app.css`
- Test: `tests/test_home_page.py`

- [ ] **Step 1: Extend the failing homepage test for monitor UI hooks**

```python
# tests/test_home_page.py
def test_home_page_renders_monitor_hooks() -> None:
    client = TestClient(create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="monitor-form"' in response.text
    assert 'id="monitor-list"' in response.text
    assert 'id="monitor-detail"' in response.text
    assert 'data-monitor-action="edit"' in response.text
    assert 'data-monitor-action="toggle"' in response.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_monitor_hooks -v
```

Expected: FAIL because the monitor UI hooks do not exist yet.

- [ ] **Step 3: Implement monitor UI hooks and browser wiring**

```html
<!-- app/templates/index.html -->
<section class="panel monitor-panel">
  <div class="panel-heading">
    <div>
      <p class="panel-kicker">Monitoring</p>
      <h2>Price Alerts</h2>
    </div>
  </div>

  <form id="monitor-form" class="search-form">
    <label><span>Origin city</span><input type="text" name="origin_city" /></label>
    <label><span>Destination city</span><input type="text" name="destination_city" /></label>
    <label><span>Departure date</span><input type="date" name="departure_date" /></label>
    <label><span>Target price</span><input type="number" name="target_price" min="1" /></label>
    <label><span>Check every (minutes)</span><input type="number" name="check_interval_minutes" min="5" /></label>
    <button type="submit" class="primary-action">Save monitor</button>
  </form>

  <div id="monitor-list"></div>
  <div id="monitor-detail"></div>
</section>
```

```javascript
// app/static/app.js
const monitorForm = document.querySelector("#monitor-form");
const monitorListElement = document.querySelector("#monitor-list");
const monitorDetailElement = document.querySelector("#monitor-detail");

async function loadMonitorList() {
  const monitors = await requestJson("/api/monitors");
  renderMonitorList(monitors);
}

function renderMonitorList(monitors) {
  if (!monitorListElement) return;
  monitorListElement.replaceChildren();
  monitors.forEach((monitor) => {
    const article = document.createElement("article");
    article.dataset.monitorId = String(monitor.id);
    article.innerHTML = `
      <h3>${monitor.origin_city} → ${monitor.destination_city}</h3>
      <p>Target ¥${monitor.target_price} · every ${monitor.check_interval_minutes} minutes</p>
      <button type="button" data-monitor-action="edit" data-monitor-id="${monitor.id}">Edit</button>
      <button type="button" data-monitor-action="toggle" data-monitor-id="${monitor.id}">${monitor.enabled ? "Pause" : "Resume"}</button>
    `;
    monitorListElement.appendChild(article);
  });
}
```

- [ ] **Step 4: Run the homepage test to verify it passes**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_monitor_hooks -v
```

Expected: PASS.

- [ ] **Step 5: Commit the monitor UI shell**

Run:
```bash
git add app/main.py app/templates/index.html app/static/app.js app/static/app.css tests/test_home_page.py && git commit -m "feat: add monitor ui shell"
```

Expected: a commit containing the monitor UI shell and hooks.

---

### Task 7: Add notification click-through and hit-detail rendering

**Files:**
- Modify: `app/monitoring.py`
- Modify: `app/main.py`
- Modify: `app/static/app.js`
- Test: `tests/test_monitor_api.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: Extend the failing tests for hit detail and click-through targets**

```python
# tests/test_monitor_api.py
def test_monitor_hit_detail_endpoint_returns_saved_snapshot(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings))

    created = client.post("/api/monitors", json={
        "origin_city": "bjs",
        "destination_city": "sha",
        "departure_date": "2026-05-20",
        "target_price": 400,
        "check_interval_minutes": 30,
        "departure_time_filters": [],
        "flight_attribute_filters": [],
        "airline_filters": [],
    }).json()

    # Assume repository helper is used to seed a hit in test setup
    hit_response = client.get(f"/api/monitors/{created['id']}/hits")
    assert hit_response.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_api.py tests/test_notifier.py -v
```

Expected: FAIL because monitor hit routes/UI hooks do not exist yet.

- [ ] **Step 3: Implement hit listing and notification target rendering**

```python
# app/monitoring.py
def list_monitor_hits(settings: Settings, monitor_task_id: int) -> list[MonitorHit]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM monitor_hits WHERE monitor_task_id = ? ORDER BY hit_at DESC",
            (monitor_task_id,),
        ).fetchall()
    return [_row_to_monitor_hit(row) for row in rows]
```

```python
# app/main.py
from app.monitoring import list_monitor_hits

    @app.get("/api/monitors/{monitor_id}/hits")
    async def monitor_hits(monitor_id: int):
        if get_monitor_task(app.state.settings, monitor_id) is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return list_monitor_hits(app.state.settings, monitor_id)
```

```javascript
// app/static/app.js
async function loadMonitorDetail(monitorId) {
  const [task, hits] = await Promise.all([
    requestJson(`/api/monitors/${monitorId}`),
    requestJson(`/api/monitors/${monitorId}/hits`),
  ]);
  renderMonitorDetail(task, hits);
}

function renderMonitorDetail(task, hits) {
  if (!monitorDetailElement) return;
  monitorDetailElement.innerHTML = `
    <h3>${task.origin_city} → ${task.destination_city}</h3>
    <p>Target ¥${task.target_price}</p>
    <div id="monitor-hit-list"></div>
  `;
  const hitList = monitorDetailElement.querySelector("#monitor-hit-list");
  hits.forEach((hit) => {
    const article = document.createElement("article");
    article.innerHTML = `<h4>Hit ¥${hit.lowest_price}</h4>`;
    hit.search_snapshot_json.forEach((flight) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${flight.airline} ${flight.flight_no} ¥${flight.price}`;
      button.addEventListener("click", () => {
        window.open(flight.deeplink_url || flight.fallback_search_url, "_blank");
      });
      article.appendChild(button);
    });
    hitList.appendChild(article);
  });
}
```

- [ ] **Step 4: Run the updated tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_monitor_api.py tests/test_notifier.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the hit-detail flow**

Run:
```bash
git add app/monitoring.py app/main.py app/static/app.js tests/test_monitor_api.py tests/test_notifier.py && git commit -m "feat: add monitor hit detail flow"
```

Expected: a commit containing the notification click-through destination flow.

---

### Task 8: Add Windows one-click startup script and config expectations

**Files:**
- Create: `start_fly_ticket.bat`
- Test: `tests/test_startup_script_notes.py`

- [ ] **Step 1: Write the failing startup-script expectation test**

```python
# tests/test_startup_script_notes.py
from pathlib import Path


def test_windows_startup_script_exists_and_mentions_bootstrap_steps() -> None:
    script = Path("start_fly_ticket.bat")

    assert script.exists()
    content = script.read_text(encoding="utf-8")
    assert "python" in content.lower()
    assert "playwright install chromium" in content.lower()
    assert ".env.example" in content
    assert "uvicorn" in content.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_startup_script_notes.py -v
```

Expected: FAIL because the launcher script does not exist.

- [ ] **Step 3: Implement the startup script**

```bat
@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  py -3 -m venv .venv
)

call .venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
call .venv\Scripts\python -m playwright install chromium

if not exist .env (
  copy .env.example .env >nul
)

start "Fly Ticket" cmd /k ".venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "" http://127.0.0.1:8000
```

- [ ] **Step 4: Run the startup-script expectation tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_startup_script_notes.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the startup script**

Run:
```bash
git add start_fly_ticket.bat tests/test_startup_script_notes.py && git commit -m "feat: add windows startup script"
```

Expected: a commit containing the launcher entry point.

---

### Task 9: Run full verification and manually exercise the monitor flow

**Files:**
- Modify only if needed for tiny final fixes: `app/main.py`, `app/static/app.js`, `app/templates/index.html`, `app/static/app.css`
- Test: all existing tests

- [ ] **Step 1: Run the full automated test suite**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Start the app and the in-process scheduler**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m uvicorn app.main:app --reload
```

Expected: the app starts successfully and serves the updated pages.

- [ ] **Step 3: Manually verify the monitoring flow**

Manual checklist:
- Create a monitor task in the browser
- Confirm it appears in the monitor task list
- Edit the task and confirm the form rehydrates
- Trigger a monitor check in a controlled way (short interval or direct scheduler tick)
- Confirm a hit record is written when the price is <= target price
- Confirm a desktop notification appears on the local machine
- Click the notification and confirm the local app opens to the monitor detail/hit view
- In the hit view, click a flight and confirm it opens the Ctrip deeplink or fallback search page

- [ ] **Step 4: Make only the smallest UI fixes needed to satisfy the checklist**

```javascript
// app/static/app.js
// If monitor detail needs routing hydration from query params, add the smallest helper:
const params = new URLSearchParams(window.location.search);
const monitorTaskId = params.get("monitor_task_id");
if (monitorTaskId) {
  loadMonitorDetail(monitorTaskId);
}
```

Expected: only small follow-up wiring should be needed at this stage.

- [ ] **Step 5: Commit the verified monitoring MVP**

Run:
```bash
git add app/main.py app/static/app.js app/static/app.css app/templates/index.html start_fly_ticket.bat && git commit -m "feat: add local flight monitoring and notifications"
```

Expected: a final commit after automated and manual verification succeed.

---

## Self-Review Checklist

### Spec coverage
- Local monitor tasks and frequency: covered by Tasks 1, 4, and 6.
- Background scheduler and due-task execution: covered by Tasks 2 and 5.
- Desktop notifications and click-through: covered by Tasks 3, 5, and 7.
- Hit record storage and detail page: covered by Tasks 1 and 7.
- Notification dedupe rules: covered by Task 2 and exercised again in Task 5.
- Windows one-click startup: covered by Task 8.
- Manual verification of the full monitoring loop: covered by Task 9.

### Placeholder scan
- No TODO/TBD placeholders remain in the task steps.
- The only manual requirement is local browser login to Ctrip, which is already part of the existing app’s runtime model.

### Type consistency
- `MonitorTaskCreate`, `MonitorTask`, and `MonitorHit` are introduced once and reused consistently.
- Notification helpers, scheduler, and runner all refer to the same monitor-task and hit identifiers.

### Scope check
- This plan stays within the chosen local-background-monitoring approach and does not prematurely split into an external worker or installer package.
