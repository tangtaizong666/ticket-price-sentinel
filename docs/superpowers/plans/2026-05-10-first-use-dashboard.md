# First-Use Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the homepage into a first-use dashboard that tells non-technical users what to do next, shows login/monitor/latest-hit status clearly, and keeps the existing search and monitoring entry points easy to find.

**Architecture:** Add a small dashboard view-model layer that aggregates existing session, monitor, and latest-hit state into copy-ready cards, then rebuild the homepage template around that model. Keep the browser-side work minimal and focused on primary dashboard actions like relogin, jump-to-search, jump-to-monitor, and latest-hit focus, reusing the existing search and monitor detail flows instead of inventing a second UI path.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLite (`sqlite3`), pytest, httpx/TestClient, python-dotenv, existing browser-side JavaScript/CSS

---

## Planned File Structure

- Create: `app/dashboard.py` — aggregate login status, monitor status, latest hit summary, and first-use guide copy for the homepage
- Modify: `app/history.py` — add a read helper for current session state
- Modify: `app/monitoring.py` — add dashboard-oriented helper queries for enabled-monitor count and latest hit lookup
- Modify: `app/main.py` — build the dashboard model and pass it into the homepage template
- Modify: `app/templates/index.html` — replace the current top-of-page structure with a first-use guide, status cards, and clearer primary actions
- Modify: `app/static/app.js` — add dashboard action handlers (relogin, focus search, focus monitor, view latest hit)
- Modify: `app/static/app.css` — add first-use guide, dashboard card, and latest-hit highlight styling
- Create: `tests/test_dashboard_view.py` — verify dashboard aggregation and copy decisions from real SQLite-backed state
- Modify: `tests/test_home_page.py` — verify rendered first-use dashboard hooks and the new JS source-level wiring checks

## Execution Notes

1. The repository still has no commit history and git identity is not configured, so commit commands are included for completeness but may fail until identity is configured.
2. This plan intentionally does **not** add new backend product features; it only repackages and clarifies already-built capabilities.
3. The homepage should remain usable even when login is missing, no monitor exists, or no hit has ever been recorded.
4. The existing monitor detail and hit-detail flow already exists; the dashboard should point into it rather than duplicate it.

---

### Task 1: Add the homepage dashboard view model

**Files:**
- Create: `app/dashboard.py`
- Modify: `app/history.py`
- Modify: `app/monitoring.py`
- Test: `tests/test_dashboard_view.py`

- [ ] **Step 1: Write the failing dashboard aggregation tests**

```python
# tests/test_dashboard_view.py
from datetime import UTC, date, datetime

from app.dashboard import load_home_dashboard
from app.db import init_db
from app.history import save_session_state
from app.models import MonitorTaskCreate
from app.monitoring import create_monitor_task, record_monitor_hit
from app.settings import Settings


def test_home_dashboard_guides_first_use_when_no_session_or_monitors(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    dashboard = load_home_dashboard(settings)

    assert dashboard.guide_title == "只要 3 步就能开始"
    assert dashboard.login_card.status == "未登录"
    assert dashboard.login_card.action_label == "去登录"
    assert dashboard.monitor_card.status == "还没有监控任务"
    assert dashboard.latest_hit_card.status == "还没有命中记录"


def test_home_dashboard_surfaces_login_monitor_and_latest_hit_state(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    save_session_state(settings, "login_started")
    monitor = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
            departure_time_filters=[],
            flight_attribute_filters=[],
            airline_filters=[],
        ),
    )
    hit = record_monitor_hit(
        settings,
        task_id=monitor.id,
        lowest_price=380,
        flights_snapshot=[
            {
                "flight_no": "CA8341",
                "airline": "中国国航",
                "price": 380,
                "stop_info": "直飞",
                "deeplink_url": "https://example.com/flight",
                "fallback_search_url": "https://example.com/results",
            }
        ],
    )

    dashboard = load_home_dashboard(settings)

    assert dashboard.login_card.status == "已登录"
    assert dashboard.monitor_card.status == "1 个任务正在运行"
    assert dashboard.latest_hit_card.status == "bjs → sha"
    assert dashboard.latest_hit_card.detail == "最低价 ¥380"
    assert dashboard.latest_hit_card.monitor_task_id == monitor.id
    assert dashboard.latest_hit_card.monitor_hit_id == hit.id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_dashboard_view.py -v
```

Expected: FAIL because `app.dashboard`, `get_session_state`, and the dashboard helper queries do not exist yet.

- [ ] **Step 3: Implement the dashboard model and data loaders**

```python
# app/dashboard.py
from dataclasses import dataclass

from app.history import get_session_state
from app.monitoring import count_enabled_monitor_tasks, get_latest_monitor_hit
from app.settings import Settings


@dataclass(slots=True)
class DashboardCard:
    title: str
    status: str
    detail: str
    action_label: str
    action_kind: str
    monitor_task_id: int | None = None
    monitor_hit_id: int | None = None


@dataclass(slots=True)
class HomeDashboard:
    guide_title: str
    guide_steps: list[str]
    login_card: DashboardCard
    monitor_card: DashboardCard
    latest_hit_card: DashboardCard


def load_home_dashboard(settings: Settings) -> HomeDashboard:
    session_state = get_session_state(settings)
    enabled_count = count_enabled_monitor_tasks(settings)
    latest_hit = get_latest_monitor_hit(settings)

    if session_state is not None and session_state.session_status == "login_started":
        login_card = DashboardCard(
            title="登录状态",
            status="已登录",
            detail="携程会话可用",
            action_label="重新登录",
            action_kind="relogin",
        )
    else:
        login_card = DashboardCard(
            title="登录状态",
            status="未登录",
            detail="首次使用请先登录携程",
            action_label="去登录",
            action_kind="relogin",
        )

    if enabled_count == 0:
        monitor_card = DashboardCard(
            title="监控状态",
            status="还没有监控任务",
            detail="保存一个目标价，程序会在后台帮你定时检查",
            action_label="创建第一个监控",
            action_kind="create-monitor",
        )
    else:
        suffix = "任务" if enabled_count == 1 else "个任务"
        monitor_card = DashboardCard(
            title="监控状态",
            status=f"{enabled_count} {suffix}正在运行",
            detail="后台监控已启用",
            action_label="创建监控任务",
            action_kind="create-monitor",
        )

    if latest_hit is None:
        latest_hit_card = DashboardCard(
            title="最近命中",
            status="还没有命中记录",
            detail="当价格达到你的目标价时，最新命中结果会显示在这里",
            action_label="创建监控任务",
            action_kind="create-monitor",
        )
    else:
        task, hit = latest_hit
        latest_hit_card = DashboardCard(
            title="最近命中",
            status=f"{task.origin_city} → {task.destination_city}",
            detail=f"最低价 ¥{hit.lowest_price}",
            action_label="查看命中结果",
            action_kind="view-hit",
            monitor_task_id=task.id,
            monitor_hit_id=hit.id,
        )

    return HomeDashboard(
        guide_title="只要 3 步就能开始",
        guide_steps=[
            "先确认携程是否已登录",
            "做一次搜索看看现在的价格",
            "保存一个监控任务，后台自动帮你检查",
        ],
        login_card=login_card,
        monitor_card=monitor_card,
        latest_hit_card=latest_hit_card,
    )
```

```python
# app/history.py
from app.models import SessionState


def get_session_state(settings: Settings) -> SessionState | None:
    with connect(settings) as connection:
        row = connection.execute("SELECT * FROM session_state WHERE id = 1").fetchone()
    if row is None:
        return None
    return SessionState(
        id=row["id"],
        session_status=row["session_status"],
        last_successful_scrape_at=(
            datetime.fromisoformat(row["last_successful_scrape_at"])
            if row["last_successful_scrape_at"]
            else None
        ),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
```

```python
# app/monitoring.py
def count_enabled_monitor_tasks(settings: Settings) -> int:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM monitor_tasks WHERE enabled = 1"
        ).fetchone()
    return int(row["count"])


def get_latest_monitor_hit(settings: Settings) -> tuple[MonitorTask, MonitorHit] | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM monitor_hits ORDER BY hit_at DESC, id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    hit = _row_to_monitor_hit(row)
    task = get_monitor_task(settings, hit.monitor_task_id)
    if task is None:
        return None
    return task, hit
```

- [ ] **Step 4: Run the dashboard tests to verify they pass**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_dashboard_view.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the dashboard data layer**

Run:
```bash
git add app/dashboard.py app/history.py app/monitoring.py tests/test_dashboard_view.py && git commit -m "feat: add first-use dashboard view model"
```

Expected: a commit containing the homepage dashboard aggregation layer.

---

### Task 2: Rebuild the homepage template around the first-use dashboard

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/index.html`
- Modify: `tests/test_home_page.py`

- [ ] **Step 1: Extend the failing homepage test for the new dashboard structure**

```python
# tests/test_home_page.py
def test_home_page_renders_first_use_dashboard() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="first-use-guide"' in html
    assert 'id="login-status-card"' in html
    assert 'id="monitor-status-card"' in html
    assert 'id="latest-hit-card"' in html
    assert 'data-dashboard-action="relogin"' in html
    assert 'data-dashboard-action="search"' in html
    assert 'data-dashboard-action="create-monitor"' in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_first_use_dashboard -v
```

Expected: FAIL because the first-use dashboard markup does not exist yet.

- [ ] **Step 3: Pass dashboard data into the homepage and rebuild the template**

```python
# app/main.py
from app.dashboard import load_home_dashboard

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "history": list_history(app.state.settings),
                "monitors": list_monitor_tasks(app.state.settings),
                "dashboard": load_home_dashboard(app.state.settings),
            },
        )
```

```html
<!-- app/templates/index.html -->
<section id="first-use-guide" class="panel guide-panel">
  <div class="panel-heading">
    <div>
      <p class="panel-kicker">开始使用</p>
      <h2>{{ dashboard.guide_title }}</h2>
    </div>
  </div>
  <ol class="guide-steps">
    {% for step in dashboard.guide_steps %}
    <li>{{ step }}</li>
    {% endfor %}
  </ol>
</section>

<section class="dashboard-status-grid">
  <article id="login-status-card" class="panel status-card">
    <p class="panel-kicker">{{ dashboard.login_card.title }}</p>
    <h3>{{ dashboard.login_card.status }}</h3>
    <p>{{ dashboard.login_card.detail }}</p>
    <button type="button" class="primary-action" data-dashboard-action="{{ dashboard.login_card.action_kind }}">{{ dashboard.login_card.action_label }}</button>
  </article>

  <article id="monitor-status-card" class="panel status-card">
    <p class="panel-kicker">{{ dashboard.monitor_card.title }}</p>
    <h3>{{ dashboard.monitor_card.status }}</h3>
    <p>{{ dashboard.monitor_card.detail }}</p>
    <button type="button" class="primary-action" data-dashboard-action="{{ dashboard.monitor_card.action_kind }}">{{ dashboard.monitor_card.action_label }}</button>
  </article>

  <article id="latest-hit-card" class="panel status-card" data-monitor-task-id="{{ dashboard.latest_hit_card.monitor_task_id or '' }}" data-monitor-hit-id="{{ dashboard.latest_hit_card.monitor_hit_id or '' }}">
    <p class="panel-kicker">{{ dashboard.latest_hit_card.title }}</p>
    <h3>{{ dashboard.latest_hit_card.status }}</h3>
    <p>{{ dashboard.latest_hit_card.detail }}</p>
    <button type="button" class="primary-action" data-dashboard-action="{{ dashboard.latest_hit_card.action_kind }}" data-monitor-task-id="{{ dashboard.latest_hit_card.monitor_task_id or '' }}" data-monitor-hit-id="{{ dashboard.latest_hit_card.monitor_hit_id or '' }}">{{ dashboard.latest_hit_card.action_label }}</button>
  </article>
</section>
```

- [ ] **Step 4: Run the homepage test to verify it passes**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_home_page.py::test_home_page_renders_first_use_dashboard -v
```

Expected: PASS.

- [ ] **Step 5: Commit the first-use dashboard template structure**

Run:
```bash
git add app/main.py app/templates/index.html tests/test_home_page.py && git commit -m "feat: rebuild homepage as first-use dashboard"
```

Expected: a commit containing the new homepage structure.

---

### Task 3: Add dashboard action wiring and latest-hit focus behavior

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/app.css`
- Modify: `tests/test_home_page.py`

- [ ] **Step 1: Extend the failing tests for dashboard action wiring**

```python
# tests/test_home_page.py
from pathlib import Path


def test_dashboard_js_wires_primary_actions_and_latest_hit_focus() -> None:
    script = Path("app/static/app.js").read_text(encoding="utf-8")

    assert "handleDashboardAction" in script
    assert 'data-dashboard-action' in Path("app/templates/index.html").read_text(encoding="utf-8")
    assert 'requestJson("/api/session/relogin"' in script
    assert 'monitor_hit_id' in script
    assert 'scrollIntoView' in script
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_home_page.py::test_dashboard_js_wires_primary_actions_and_latest_hit_focus -v
```

Expected: FAIL because the dashboard action handler does not exist yet.

- [ ] **Step 3: Implement dashboard action handling and highlight behavior**

```javascript
// app/static/app.js
const dashboardActionsRoot = document.body;

function focusAndScroll(selector) {
  const element = document.querySelector(selector);
  if (!element) return;
  element.scrollIntoView({ behavior: "smooth", block: "start" });
  const input = element.querySelector("input, button, [tabindex]");
  if (input instanceof HTMLElement) input.focus();
}

async function handleDashboardAction(event) {
  const button = event.target.closest("[data-dashboard-action]");
  if (!button) return;

  const action = button.dataset.dashboardAction;
  if (action === "relogin") {
    searchSummaryElement.textContent = "正在打开携程登录...";
    const payload = await requestJson("/api/session/relogin", { method: "POST" });
    searchSummaryElement.textContent = payload.status === "login_started"
      ? "已打开携程登录窗口，请完成登录后返回这里。"
      : "当前缺少登录页面配置，请先检查环境设置。";
    return;
  }

  if (action === "search") {
    focusAndScroll("#search-form");
    return;
  }

  if (action === "create-monitor") {
    focusAndScroll("#monitor-form");
    return;
  }

  if (action === "view-hit") {
    const monitorTaskId = button.dataset.monitorTaskId;
    const monitorHitId = button.dataset.monitorHitId;
    if (monitorTaskId) {
      await loadMonitorDetail(monitorTaskId, monitorHitId || null);
      focusAndScroll("#monitor-detail");
    }
  }
}

async function loadMonitorDetail(monitorId, highlightedHitId = null) {
  const [task, hits] = await Promise.all([
    requestJson(`/api/monitors/${monitorId}`),
    requestJson(`/api/monitors/${monitorId}/hits`),
  ]);
  renderMonitorDetail(task, hits, highlightedHitId);
}

function renderMonitorDetail(task, hits, highlightedHitId = null) {
  // existing shell rendering
  // when rendering hit cards:
  // article.dataset.monitorHitId = String(hit.id)
  // if (highlightedHitId && String(hit.id) === String(highlightedHitId)) article.classList.add("is-highlighted")
  // article.scrollIntoView(...) after render if highlighted exists
}

dashboardActionsRoot?.addEventListener("click", (event) => {
  handleDashboardAction(event).catch((error) => {
    searchSummaryElement.textContent = `操作失败。${error.message}`;
  });
});
```

```css
/* app/static/app.css */
.guide-panel {
  margin-bottom: 20px;
}

.guide-steps {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 8px;
  color: #33415c;
}

.dashboard-status-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.status-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.monitor-hit-card.is-highlighted {
  border-color: #2667ff;
  box-shadow: 0 0 0 2px rgba(38, 103, 255, 0.15);
}
```

- [ ] **Step 4: Run the dashboard action test and the broader homepage suite**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest tests/test_home_page.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the dashboard interaction layer**

Run:
```bash
git add app/static/app.js app/static/app.css tests/test_home_page.py && git commit -m "feat: add first-use dashboard actions"
```

Expected: a commit containing the homepage action wiring.

---

### Task 4: Run full verification against the polished first-use dashboard

**Files:**
- Modify only if needed for tiny final fixes: `app/main.py`, `app/templates/index.html`, `app/static/app.js`, `app/static/app.css`
- Test: all existing tests

- [ ] **Step 1: Run the full automated test suite**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Start the app for manual verification**

Run:
```bash
cd /mnt/c/my_pycharm/fly_ticket && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

Expected: the app starts at `http://127.0.0.1:8003`.

- [ ] **Step 3: Manually verify the first-use experience**

Manual checklist:
- Open the homepage and verify the first-use guide is visible above the functional sections
- Confirm the login status card clearly shows whether Ctrip is connected
- Confirm the monitor status card clearly shows whether any monitor tasks exist and whether monitoring is running
- If no hits exist, confirm the latest-hit card shows the empty-state message
- Click the dashboard relogin button and confirm the local status message updates appropriately
- Click the dashboard search action and confirm focus/scroll moves to the search form
- Click the dashboard create-monitor action and confirm focus/scroll moves to the monitor form
- If a latest hit exists, click the dashboard latest-hit action and confirm the monitor detail view opens and highlights the specific hit

- [ ] **Step 4: Make only the smallest UI/content fixes needed to satisfy the checklist**

```javascript
// app/static/app.js
// If the dashboard summary message needs to reflect current state after relogin/search-monitor actions,
// make only small text updates inside the existing event handlers rather than rewriting the dashboard model.
```

Expected: only tiny polish changes should be needed at this stage.

- [ ] **Step 5: Commit the verified first-use dashboard polish**

Run:
```bash
git add app/dashboard.py app/history.py app/monitoring.py app/main.py app/templates/index.html app/static/app.js app/static/app.css tests/test_dashboard_view.py tests/test_home_page.py && git commit -m "feat: polish first-use dashboard experience"
```

Expected: a final commit after automated and manual verification succeed.

---

## Self-Review Checklist

### Spec coverage
- First-use guide and “what to do next” hierarchy: covered by Tasks 1 and 2.
- Login/monitor/latest-hit status cards: covered by Tasks 1 and 2.
- Empty-state and plain-language copy: covered by Task 1 and rendered in Task 2.
- Search / create-monitor / relogin / latest-hit actions: covered by Task 3.
- Manual first-use verification: covered by Task 4.

### Placeholder scan
- No TODO/TBD placeholders remain in task steps.
- The only environment-sensitive part is real Ctrip login state, which already exists in the project’s runtime model.

### Type consistency
- `DashboardCard` and `HomeDashboard` are introduced once and reused consistently.
- Dashboard latest-hit routing always uses `monitor_task_id` plus `monitor_hit_id` when available.

### Scope check
- This plan stays within homepage/dashboard polish and does not expand into new product capabilities, new background behavior, or installer packaging work.
