# 机票监控产品化打磨 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有本地机票工具改造成更适合长期运行的中文监控工作台，支持重复提醒、稳定调度、清爽首页和中文说明。

**Architecture:** 在现有 FastAPI + SQLite + Playwright 单体结构上做局部增强，不拆分成新服务。后端重点补监控提醒策略、失败恢复和状态展示；前端重点做首页清爽化、中文化和声音提醒；文档重点把 README 和普通用户说明改成中文。

**Tech Stack:** Python, FastAPI, SQLite, Jinja2, 原生 JavaScript, CSS, Playwright, `plyer`

---

## 文件结构

### 后端
- `app/monitor_runner.py`：监控命中判断与提醒去重规则
- `app/monitor_scheduler.py`：后台调度、任务失败恢复、提醒触发
- `app/monitoring.py`：监控任务状态字段的读写逻辑
- `app/notifier.py`：桌面通知内容、声音提示、回调链接生成
- `app/dashboard.py`：首页状态卡和中文文案
- `app/main.py`：首页和 API 的中文错误/状态响应
- `app/settings.py`：新增冷却时间或提醒相关配置

### 前端
- `app/templates/index.html`：首页文案和布局结构
- `app/static/app.js`：页面提示、声音提醒、中文交互文案、监控详情交互
- `app/static/app.css`：清爽仪表盘风格和响应式布局

### 文档
- `README.md`：中文化说明与启动路径
- `README_使用说明.txt`：普通用户中文说明

### 测试
- `tests/test_monitor_runner.py`
- `tests/test_monitor_api.py`
- `tests/test_notifier.py`
- `tests/test_home_page.py`
- `tests/test_search_api.py`
- `tests/test_session_api.py`
- `tests/test_history_api.py`
- `tests/test_release_packaging.py`

---

## Task 1: 定义重复提醒和冷却配置

**Files:**
- Modify: `app/settings.py`
- Modify: `app/monitor_runner.py`
- Modify: `tests/test_monitor_runner.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import UTC, datetime, timedelta

from app.monitor_runner import evaluate_monitor_result


def test_monitor_evaluation_allows_repeat_alert_after_cooldown() -> None:
    task = _build_task(
        last_notified_price=380,
        last_notified_at=datetime(2026, 5, 10, 1, 0, tzinfo=UTC),
    )

    evaluation = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        cooldown_hours=6,
    )

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is True
```

Expected: the current code has no cooldown-aware path and still only compares against `last_notified_price`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_monitor_runner.py -v`
Expected: FAIL because the new cooldown-aware test does not pass yet.

- [ ] **Step 3: Write minimal implementation**

Add `monitor_realert_cooldown_hours` to `Settings` and make `evaluate_monitor_result()` accept `now` and `cooldown_hours` so repeated reminders can be decided from real timestamps instead of only the last notified price.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_monitor_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/settings.py app/monitor_runner.py tests/test_monitor_runner.py
git commit -m "feat: add monitor realert cooldown settings"
```

---

## Task 2: 让监控在命中后按冷却时间重复提醒

**Files:**
- Modify: `app/monitor_runner.py`
- Modify: `app/monitor_scheduler.py`
- Modify: `app/monitoring.py`
- Modify: `tests/test_monitor_runner.py`
- Modify: `tests/test_monitor_api.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import UTC, datetime


def test_monitor_scheduler_repeats_hit_after_cooldown(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
        last_notified_at=datetime(2026, 5, 10, 1, 0, tzinfo=UTC),
        last_notified_price=380,
    )
    scraper = _StubScraper(_build_flights(380, 420))
    notifications: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.monitor_scheduler.send_desktop_notification",
        lambda title, message: notifications.append((title, message)),
    )

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    updated_task = get_monitor_task(settings, task.id)

    assert notifications == [
        ("机票监控命中：bjs → sha", "当前最低价 ¥380，已达到你的目标价 ¥400")
    ]
    assert len(hits) == 1
    assert hits[0].lowest_price == 380
    assert updated_task is not None
    assert updated_task.last_notified_price == 380
```

The test should seed a monitor task whose `last_notified_at` is older than the cooldown, use a scraper that still returns a matching low price, and assert that the repeat notification path fires again.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_monitor_runner.py tests/test_monitor_api.py -v`
Expected: FAIL because the current implementation suppresses repeat notifications unless the price drops lower.

- [ ] **Step 3: Write minimal implementation**

Implement a helper in `app/monitor_scheduler.py` that compares `now - last_notified_at` with the configured cooldown, then route repeat-hit notification decisions through that helper.

Update the scheduler to:
- notify on first hit
- notify again after cooldown if still at or below target price
- notify immediately if the price drops below the last notified price

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_monitor_runner.py tests/test_monitor_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/monitor_runner.py app/monitor_scheduler.py app/monitoring.py tests/test_monitor_runner.py tests/test_monitor_api.py
git commit -m "feat: repeat monitor alerts after cooldown"
```

---

## Task 3: 给提醒加页面高亮和声音提示

**Files:**
- Modify: `app/notifier.py`
- Modify: `app/monitor_scheduler.py`
- Modify: `app/static/app.js`
- Modify: `tests/test_notifier.py`
- Modify: `tests/test_home_page.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_notification_message_mentions_route_price_and_repeat() -> None:
    title, message = build_notification_message("bjs", "sha", 380, 400)

    assert title == "机票监控命中：bjs → sha"
    assert message == "当前最低价 ¥380，已达到你的目标价 ¥400"


def test_dashboard_js_exposes_monitor_hit_tone_hook() -> None:
    script = Path("app/static/app.js").read_text(encoding="utf-8")

    assert "function playMonitorHitTone()" in script
    assert "monitor-hit-tone" in script
```

Also add a frontend test asserting that the page contains a sound hook for monitor hits and that the monitor-hit focus path still exists.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_notifier.py tests/test_home_page.py -v`
Expected: FAIL because the current code only sends desktop notifications.

- [ ] **Step 3: Write minimal implementation**

Add a small browser-side sound trigger for monitor hits using a safe built-in Web Audio API helper:

```javascript
function playMonitorHitTone() {
    if (!window.AudioContext && !window.webkitAudioContext) {
        return;
    }
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.value = 0.03;
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.18);
}
```

Call it when a monitor hit detail is focused or rendered so the page gives an audible cue alongside the visual highlight.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_notifier.py tests/test_home_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/notifier.py app/monitor_scheduler.py app/static/app.js tests/test_notifier.py tests/test_home_page.py
git commit -m "feat: add monitor alert sound and page feedback"
```

---

## Task 4: 重做首页为中文清爽仪表盘

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/app.css`
- Modify: `app/static/app.js`
- Modify: `app/dashboard.py`
- Modify: `tests/test_home_page.py`

- [ ] **Step 1: Write the failing test**

```python
def test_home_page_uses_chinese_dashboard_copy_and_status_cards() -> None:
    app = create_app()
    client = TestClient(app)

    html = client.get("/").text

    for expected in ["飞票监控", "登录状态", "监控状态", "最近命中", "快速搜索", "创建监控任务"]:
        assert expected in html

    assert "Flight search workspace" not in html
    assert "<h2>Search</h2>" not in html
    assert "<h2>Results</h2>" not in html
```

Include assertions for Chinese labels such as `登录状态`, `监控状态`, `最近命中`, `快速搜索`, and `创建监控任务`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_home_page.py -v`
Expected: FAIL because current content still contains a lot of English labels.

- [ ] **Step 3: Write minimal implementation**

Replace the first-screen copy and section headings with Chinese labels, keep the existing form fields and data attributes, and rework the CSS so the dashboard reads as a clean, lighter-weight operational view.

Restructure the first screen into:
- login card
- monitor status card
- latest hit card
- search area
- create monitor area

Update CSS to a cleaner dashboard look with softer cards, stronger hierarchy, and better spacing.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_home_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/app.css app/static/app.js app/dashboard.py tests/test_home_page.py
git commit -m "feat: polish chinese dashboard layout"
```

---

## Task 5: 中文化 README 和普通用户说明

**Files:**
- Modify: `README.md`
- Modify: `README_使用说明.txt`
- Modify: `tests/test_release_packaging.py`

- [ ] **Step 1: Write the failing test**

```python
def test_readme_highlights_chinese_user_and_developer_paths() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "机票监控工作台" in content
    assert "普通用户路径" in content
    assert "开发者路径" in content
    assert "问题排查" in content
```

Check that the introduction, startup steps, and common usage sections are Chinese-first and still mention the release zip and `启动机票监控.bat`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_release_packaging.py -v`
Expected: FAIL until the docs are rewritten.

- [ ] **Step 3: Write minimal implementation**

Rewrite the README so it clearly separates:
- ordinary user path
- developer path
- common problems

Rewrite `README_使用说明.txt` into a short, plain Chinese launch guide.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_release_packaging.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md README_使用说明.txt tests/test_release_packaging.py
git commit -m "docs: rewrite user-facing docs in Chinese"
```

---

## Task 6: 统一中文错误、空状态和监控详情文案

**Files:**
- Modify: `app/main.py`
- Modify: `app/dashboard.py`
- Modify: `app/static/app.js`
- Modify: `tests/test_search_api.py`
- Modify: `tests/test_session_api.py`
- Modify: `tests/test_history_api.py`

- [ ] **Step 1: Write the failing test**

def test_search_api_returns_chinese_messages_for_session_and_parse_failures(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")

    expired_client = TestClient(create_app(settings=settings, scraper=ExpiredScraper()))
    expired_response = expired_client.post(
        "/api/search",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
        },
    )

    assert expired_response.status_code == 503
    assert expired_response.json() == {
        "error": "relogin_required",
        "message": "携程登录已失效，请重新登录后再继续",
    }

    broken_client = TestClient(create_app(settings=settings, scraper=BrokenScraper()))
    broken_response = broken_client.post(
        "/api/search",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
        },
    )

    assert broken_response.status_code == 502
    assert broken_response.json() == {
        "error": "scrape_failed",
        "message": "这次没有成功读取携程结果，请重试一次",
    }
```

Add assertions for Chinese error messages on `/api/search` and `/api/history/{id}/rerun`, while keeping the error keys stable.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_search_api.py tests/test_session_api.py tests/test_history_api.py -v`
Expected: FAIL where the expected Chinese strings are not yet present.

- [ ] **Step 3: Write minimal implementation**

Replace user-visible English error text with Chinese wording while keeping API error keys stable.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_search_api.py tests/test_session_api.py tests/test_history_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/dashboard.py app/static/app.js tests/test_search_api.py tests/test_session_api.py tests/test_history_api.py
git commit -m "feat: localize user facing messages"
```

---

## Task 7: 终检和发布前验证

**Files:**
- Modify if needed: the files above

- [ ] **Step 1: Run the full test suite**

Run: `./.venv/bin/python -m pytest`
Expected: all tests pass.

- [ ] **Step 2: Rebuild Windows portable package if packaging files changed**

Run: `powershell -ExecutionPolicy Bypass -File scripts/build_windows_portable.ps1`
Expected: build succeeds and release archive is created.

- [ ] **Step 3: Smoke test the built package**

Start the generated launcher and confirm:
- homepage loads
- login/status cards render
- monitor detail opens
- hit notification path works

- [ ] **Step 4: Commit final cleanup**

```bash
git add .
git commit -m "feat: polish flight monitor product experience"
```

---

## Self-review checklist

Before implementation starts, verify:

1. The plan covers long-running monitoring, repeated alerts, frontend polish, and Chinese docs.
2. Each task has a concrete test-first step.
3. No task depends on a function or file that does not exist.
4. The repeat-notification cooldown is controlled by settings, not a hard-coded magic number in the scheduler.
5. The frontend sound hook is implemented safely without unsafe HTML injection.
6. Documentation tasks keep user-facing text in Chinese first.
