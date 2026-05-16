from datetime import UTC, date, datetime, timedelta, time
import asyncio

from app.db import init_db
from app.ctrip_scraper import SessionExpiredError
from app.history import get_session_state
from app.models import FlightResult, MonitorTask, MonitorTaskCreate
from app.monitor_runner import evaluate_monitor_result, should_run_task
from app.monitoring import (
    claim_monitor_task_check,
    create_monitor_task,
    get_monitor_task,
    list_monitor_checks,
    list_monitor_hits,
    update_monitor_runtime_state,
)
from app.monitor_scheduler import MonitorScheduler
from app.settings import Settings


def _build_task(**updates) -> MonitorTask:
    now = datetime(2026, 5, 10, 9, 0, tzinfo=UTC)
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
        reminder_policy="interval",
        unchanged_reminder_interval_minutes=360,
        enabled=True,
        last_checked_at=None,
        next_check_at=now,
        last_seen_lowest_price=None,
        last_notified_at=None,
        last_notified_price=None,
        created_at=now,
        updated_at=now,
    )
    return task.model_copy(update=updates)


def _build_flights(*prices: int) -> list[FlightResult]:
    flights: list[FlightResult] = []
    for index, price in enumerate(prices, start=1):
        flights.append(
            FlightResult(
                flight_no=f"MU12{index:02d}",
                airline="东航",
                origin_city="bjs",
                destination_city="sha",
                departure_time=time(8 + index, 30),
                arrival_time=time(10 + index, 45),
                is_direct=True,
                stop_info="直飞",
                price=price,
                deeplink_url=f"https://example.com/flight/{index}",
                fallback_search_url="https://example.com/results",
            )
        )
    return flights


def _build_scheduler_task(settings: Settings, **updates) -> MonitorTask:
    init_db(settings)
    task = create_monitor_task(
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
    if updates:
        from app.monitoring import update_monitor_runtime_state

        update_monitor_runtime_state(settings, task.id, **updates)
        task = get_monitor_task(settings, task.id)
        assert task is not None
    return task


def test_evaluate_monitor_result_notifies_on_first_hit_and_serializes_snapshot() -> None:
    task = _build_task()
    flights = _build_flights(380, 420)
    before = datetime.now(UTC)

    evaluation = evaluate_monitor_result(task, flights)

    after = datetime.now(UTC)
    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is True
    assert before + timedelta(minutes=30) <= evaluation.next_check_at <= after + timedelta(minutes=30)
    assert evaluation.flights_snapshot == [flight.model_dump(mode="json") for flight in flights]


def test_evaluate_monitor_result_applies_saved_task_filters_before_lowest_price() -> None:
    task = _build_task(
        target_price=500,
        departure_time_filters=["上午"],
        flight_attribute_filters=["直飞"],
        airline_filters=["东航"],
    )
    filtered_out_low_price = FlightResult(
        flight_no="CA9999",
        airline="国航",
        origin_city="bjs",
        destination_city="sha",
        departure_time=time(19, 30),
        arrival_time=time(21, 45),
        is_direct=False,
        stop_info="经停西安",
        price=100,
        deeplink_url="https://example.com/ca9999",
        fallback_search_url="https://example.com/results",
    )
    matching_flight = FlightResult(
        flight_no="MU1234",
        airline="东航",
        origin_city="bjs",
        destination_city="sha",
        departure_time=time(9, 30),
        arrival_time=time(11, 45),
        is_direct=True,
        stop_info="直飞",
        price=480,
        deeplink_url="https://example.com/mu1234",
        fallback_search_url="https://example.com/results",
    )

    evaluation = evaluate_monitor_result(
        task,
        [filtered_out_low_price, matching_flight],
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    )

    assert evaluation.lowest_price == 480
    assert evaluation.should_notify is True
    assert evaluation.flights_snapshot == [matching_flight.model_dump(mode="json")]


def test_evaluate_monitor_result_does_not_notify_for_same_price_repeat_hit() -> None:
    task = _build_task(last_notified_price=380)

    evaluation = evaluate_monitor_result(task, _build_flights(380, 420))

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is False


def test_evaluate_monitor_result_allows_repeat_alert_after_cooldown() -> None:
    task = _build_task(
        last_notified_at=datetime(2026, 5, 10, 1, 0, tzinfo=UTC),
        last_notified_price=380,
    )

    evaluation = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        cooldown_hours=6,
    )

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is True


def test_evaluate_monitor_result_suppresses_repeat_alert_inside_cooldown() -> None:
    task = _build_task(
        last_notified_at=datetime(2026, 5, 10, 6, 0, tzinfo=UTC),
        last_notified_price=380,
    )

    evaluation = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        cooldown_hours=6,
    )

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is False


def test_evaluate_monitor_result_notifies_every_check_when_cooldown_disabled() -> None:
    task = _build_task(
        last_notified_at=datetime(2026, 5, 10, 6, 0, tzinfo=UTC),
        last_notified_price=380,
    )

    evaluation = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        cooldown_hours=6,
        cooldown_enabled=False,
    )

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is True


def test_evaluate_monitor_result_no_repeat_suppresses_same_price_repeat_hit() -> None:
    task = _build_task(
        reminder_policy="no_repeat",
        last_notified_at=datetime(2026, 5, 10, 1, 0, tzinfo=UTC),
        last_notified_price=380,
    )

    evaluation = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    )

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is False


def test_evaluate_monitor_result_interval_uses_task_minutes_for_same_price_hit() -> None:
    task = _build_task(
        reminder_policy="interval",
        unchanged_reminder_interval_minutes=120,
        last_notified_at=datetime(2026, 5, 10, 7, 31, tzinfo=UTC),
        last_notified_price=380,
    )

    suppressed = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        cooldown_hours=6,
    )
    allowed = evaluate_monitor_result(
        task.model_copy(update={"last_notified_at": datetime(2026, 5, 10, 6, 59, tzinfo=UTC)}),
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        cooldown_hours=6,
    )

    assert suppressed.should_notify is False
    assert allowed.should_notify is True


def test_evaluate_monitor_result_every_check_notifies_same_price_hit() -> None:
    task = _build_task(
        reminder_policy="every_check",
        last_notified_at=datetime(2026, 5, 10, 8, 59, tzinfo=UTC),
        last_notified_price=380,
    )

    evaluation = evaluate_monitor_result(
        task,
        _build_flights(380, 420),
        now=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    )

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is True


def test_evaluate_monitor_result_notifies_when_price_drops_below_last_notification() -> None:
    task = _build_task(last_notified_price=400)

    evaluation = evaluate_monitor_result(task, _build_flights(380, 420))

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is True


def test_should_run_task_requires_enabled_task_and_due_time() -> None:
    now = datetime.now(UTC)
    ready = _build_task(next_check_at=now)
    disabled = _build_task(enabled=False, next_check_at=now)
    waiting = _build_task(next_check_at=now + timedelta(minutes=1))

    assert should_run_task(ready, now) is True
    assert should_run_task(disabled, now) is False
    assert should_run_task(waiting, now) is False


class _StubScraper:
    def __init__(self, flights: list[FlightResult]) -> None:
        self.flights = flights
        self.calls: list[MonitorTask] = []

    async def search(self, task: MonitorTask) -> list[FlightResult]:
        self.calls.append(task)
        return self.flights


class _SelectiveFailureScraper:
    def __init__(self, flights: list[FlightResult], failing_task_ids: set[int]) -> None:
        self.flights = flights
        self.failing_task_ids = failing_task_ids
        self.calls: list[MonitorTask] = []

    async def search(self, task: MonitorTask) -> list[FlightResult]:
        self.calls.append(task)
        if task.id in self.failing_task_ids:
            raise RuntimeError(f"boom for task {task.id}")
        return self.flights


class _AlwaysFailingScraper:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls: list[MonitorTask] = []

    async def search(self, task: MonitorTask) -> list[FlightResult]:
        self.calls.append(task)
        raise self.exc


class _CountingSessionManager:
    def __init__(self) -> None:
        self.relogin_calls = 0

    async def open_relogin_window(self):
        self.relogin_calls += 1
        return {"status": "login_started", "url": "https://example.invalid/session"}


class _ExpiredSessionScraper:
    def __init__(self) -> None:
        self.calls: list[MonitorTask] = []
        self.session_manager = _CountingSessionManager()

    async def search(self, task: MonitorTask) -> list[FlightResult]:
        self.calls.append(task)
        raise SessionExpiredError("expired")


class _MissingPlaywrightScraper:
    def __init__(self) -> None:
        self.calls: list[MonitorTask] = []

    async def search(self, task: MonitorTask) -> list[FlightResult]:
        self.calls.append(task)
        raise RuntimeError(
            "BrowserType.launch_persistent_context: Executable doesn't exist at "
            "C:\\Users\\Microsoft\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1161"
            "\\chrome-win\\headless_shell.exe\nLooks like Playwright was just installed or updated."
        )


def _capture_monitor_alerts(monkeypatch, calls: list[dict], result: bool = True) -> None:
    def fake_alert(**kwargs) -> bool:
        calls.append(kwargs)
        return result

    monkeypatch.setattr("app.monitor_scheduler.send_monitor_hit_alert", fake_alert)



def test_monitor_scheduler_records_first_hit_and_updates_runtime_state(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(settings, next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC))
    flights = _build_flights(380, 420)
    scraper = _StubScraper(flights)
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    checks = list_monitor_checks(settings, task.id)
    updated_task = get_monitor_task(settings, task.id)

    assert len(scraper.calls) == 1
    assert len(hits) == 1
    assert len(checks) == 1
    assert hits[0].lowest_price == 380
    assert checks[0].status == "success"
    assert checks[0].lowest_price == 380
    assert checks[0].is_target_hit is True
    assert checks[0].notification_sent is True
    assert alerts == [
        {
            "base_url": "http://127.0.0.1:8000",
            "monitor_task_id": task.id,
            "monitor_hit_id": hits[0].id,
            "origin_city": "bjs",
            "destination_city": "sha",
            "departure_date": task.departure_date,
            "current_price": 380,
            "target_price": 400,
            "alert_sound_enabled": True,
            "alert_popup_enabled": True,
        }
    ]
    assert updated_task is not None
    assert updated_task.last_checked_at is not None
    assert updated_task.last_seen_lowest_price == 380
    assert updated_task.last_notified_price == 380
    assert updated_task.last_notified_at is not None
    assert updated_task.next_check_at > updated_task.last_checked_at


def test_monitor_scheduler_skips_duplicate_hits_and_non_due_tasks(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    due_task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
        last_notified_price=380,
    )
    waiting_task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2099, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _StubScraper(_build_flights(380, 420))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    due_hits = list_monitor_hits(settings, due_task.id)
    due_checks = list_monitor_checks(settings, due_task.id)
    waiting_hits = list_monitor_hits(settings, waiting_task.id)
    waiting_checks = list_monitor_checks(settings, waiting_task.id)
    updated_due_task = get_monitor_task(settings, due_task.id)
    updated_waiting_task = get_monitor_task(settings, waiting_task.id)

    assert [task.id for task in scraper.calls] == [due_task.id]
    assert due_hits == []
    assert len(due_checks) == 1
    assert due_checks[0].status == "success"
    assert due_checks[0].is_target_hit is True
    assert due_checks[0].notification_sent is False
    assert waiting_hits == []
    assert waiting_checks == []
    assert alerts == []
    assert updated_due_task is not None
    assert updated_due_task.last_checked_at is not None
    assert updated_due_task.last_seen_lowest_price == 380
    assert updated_due_task.last_notified_price == 380
    assert updated_waiting_task is not None
    assert updated_waiting_task.last_checked_at is None


def test_monitor_scheduler_skips_task_claimed_by_another_process(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    claimed_until = datetime.now(UTC) + timedelta(minutes=5)
    assert claim_monitor_task_check(
        settings,
        task.id,
        expected_next_check_at=task.next_check_at,
        claimed_until=claimed_until,
    )
    monkeypatch.setattr("app.monitor_scheduler.list_monitor_tasks", lambda settings: [task])
    scraper = _StubScraper(_build_flights(380, 420))

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    assert scraper.calls == []
    assert list_monitor_hits(settings, task.id) == []
    assert list_monitor_checks(settings, task.id) == []


def test_monitor_scheduler_repeats_hit_after_cooldown(tmp_path, monkeypatch) -> None:
    settings = Settings(
        app_db_path=tmp_path / "app.db",
        monitor_realert_cooldown_hours=6,
    )
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
        last_notified_at=datetime(2026, 5, 10, 1, 0, tzinfo=UTC),
        last_notified_price=380,
    )
    scraper = _StubScraper(_build_flights(380, 420))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    updated_task = get_monitor_task(settings, task.id)

    assert len(scraper.calls) == 1
    assert len(hits) == 1
    assert hits[0].lowest_price == 380
    assert len(alerts) == 1
    assert alerts[0]["monitor_hit_id"] == hits[0].id
    assert alerts[0]["current_price"] == 380
    assert updated_task is not None
    assert updated_task.last_notified_price == 380


def test_monitor_scheduler_respects_task_reminder_interval(tmp_path, monkeypatch) -> None:
    now = datetime.now(UTC)
    settings = Settings(
        app_db_path=tmp_path / "app.db",
    )
    task = _build_scheduler_task(
        settings,
        next_check_at=now - timedelta(minutes=1),
        last_notified_at=now - timedelta(hours=1),
        last_notified_price=380,
    )
    scraper = _StubScraper(_build_flights(380, 420))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    updated_task = get_monitor_task(settings, task.id)

    assert len(scraper.calls) == 1
    assert hits == []
    assert updated_task is not None
    assert updated_task.last_checked_at is not None
    assert updated_task.last_seen_lowest_price == 380
    assert updated_task.last_notified_price == 380
    assert alerts == []


def test_monitor_scheduler_records_successful_non_hit_check(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _StubScraper(_build_flights(500, 520))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    checks = list_monitor_checks(settings, task.id)

    assert hits == []
    assert alerts == []
    assert len(checks) == 1
    assert checks[0].status == "success"
    assert checks[0].lowest_price == 500
    assert checks[0].is_target_hit is False
    assert checks[0].notification_sent is False
    assert checks[0].search_snapshot_json == [flight.model_dump(mode="json") for flight in scraper.flights]


def test_monitor_scheduler_records_empty_ctrip_result_as_successful_non_hit(
    tmp_path,
    monkeypatch,
) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _StubScraper([])
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    checks = list_monitor_checks(settings, task.id)

    assert hits == []
    assert alerts == []
    assert len(checks) == 1
    assert checks[0].status == "success"
    assert checks[0].lowest_price is None
    assert checks[0].is_target_hit is False
    assert checks[0].notification_sent is False
    assert checks[0].search_snapshot_json == []


def test_monitor_scheduler_backs_off_after_technical_failure(tmp_path) -> None:
    settings = Settings(
        app_db_path=tmp_path / "app.db",
        monitor_failure_backoff_minutes=5,
    )
    init_db(settings)
    task = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=1,
            departure_time_filters=[],
            flight_attribute_filters=[],
            airline_filters=[],
        ),
    )
    update_monitor_runtime_state(
        settings,
        task.id,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _AlwaysFailingScraper(
        RuntimeError("Ctrip search navigation timed out: Timeout 10000ms exceeded.")
    )

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    updated_task = get_monitor_task(settings, task.id)
    checks = list_monitor_checks(settings, task.id)

    assert updated_task is not None
    assert updated_task.last_checked_at is not None
    assert updated_task.next_check_at - updated_task.last_checked_at == timedelta(minutes=5)
    assert len(checks) == 1
    assert checks[0].status == "error"
    assert checks[0].error_message == "携程页面加载超时，系统会稍后自动重试。"


def test_monitor_scheduler_marks_notification_unsent_when_backend_fails(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _StubScraper(_build_flights(380, 420))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts, result=False)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    checks = list_monitor_checks(settings, task.id)

    assert len(hits) == 1
    assert len(checks) == 1
    assert checks[0].is_target_hit is True
    assert checks[0].notification_sent is False
    assert len(alerts) == 1


def test_monitor_scheduler_passes_task_alert_channel_preferences_to_notifier(
    tmp_path,
    monkeypatch,
) -> None:
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
            departure_time_filters=[],
            flight_attribute_filters=[],
            airline_filters=[],
            alert_sound_enabled=False,
            alert_taskbar_enabled=True,
            alert_popup_enabled=False,
        ),
    )
    update_monitor_runtime_state(
        settings,
        task.id,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _StubScraper(_build_flights(380, 420))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts, result=False)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    checks = list_monitor_checks(settings, task.id)

    assert len(hits) == 1
    assert len(checks) == 1
    assert checks[0].is_target_hit is True
    assert checks[0].notification_sent is False
    assert alerts == [
        {
            "base_url": "http://127.0.0.1:8000",
            "monitor_task_id": task.id,
            "monitor_hit_id": hits[0].id,
            "origin_city": "bjs",
            "destination_city": "sha",
            "departure_date": task.departure_date,
            "current_price": 380,
            "target_price": 400,
            "alert_sound_enabled": False,
            "alert_popup_enabled": False,
        }
    ]


def test_monitor_scheduler_repeats_hit_every_check_when_realert_cooldown_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    settings = Settings(
        app_db_path=tmp_path / "app.db",
        monitor_realert_cooldown_enabled=False,
        monitor_realert_cooldown_hours=48,
    )
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
        last_notified_at=datetime(2026, 5, 10, 8, 45, tzinfo=UTC),
        last_notified_price=380,
    )
    scraper = _StubScraper(_build_flights(380, 420))
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    updated_task = get_monitor_task(settings, task.id)

    assert len(scraper.calls) == 1
    assert len(hits) == 1
    assert hits[0].lowest_price == 380
    assert len(alerts) == 1
    assert alerts[0]["monitor_hit_id"] == hits[0].id
    assert updated_task is not None
    assert updated_task.last_notified_price == 380



def test_monitor_scheduler_continues_after_task_failure(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    failing_task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    succeeding_task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _SelectiveFailureScraper(_build_flights(380, 420), {failing_task.id})
    alerts: list[dict] = []

    _capture_monitor_alerts(monkeypatch, alerts)

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    failing_hits = list_monitor_hits(settings, failing_task.id)
    failing_checks = list_monitor_checks(settings, failing_task.id)
    succeeding_hits = list_monitor_hits(settings, succeeding_task.id)
    succeeding_checks = list_monitor_checks(settings, succeeding_task.id)
    updated_failing_task = get_monitor_task(settings, failing_task.id)
    updated_succeeding_task = get_monitor_task(settings, succeeding_task.id)

    assert [task.id for task in scraper.calls] == [succeeding_task.id, failing_task.id]
    assert failing_hits == []
    assert len(failing_checks) == 1
    assert failing_checks[0].status == "error"
    assert failing_checks[0].notification_sent is False
    assert "boom for task" in (failing_checks[0].error_message or "")
    assert len(succeeding_hits) == 1
    assert len(succeeding_checks) == 1
    assert succeeding_checks[0].status == "success"
    assert succeeding_hits[0].lowest_price == 380
    assert len(alerts) == 1
    assert alerts[0]["monitor_hit_id"] == succeeding_hits[0].id
    assert updated_failing_task is not None
    assert updated_failing_task.last_checked_at is not None
    assert updated_failing_task.next_check_at > updated_failing_task.last_checked_at
    assert updated_succeeding_task is not None
    assert updated_succeeding_task.last_checked_at is not None


def test_monitor_scheduler_stores_actionable_message_for_missing_playwright_browser(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _MissingPlaywrightScraper()

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    checks = list_monitor_checks(settings, task.id)

    assert len(checks) == 1
    assert checks[0].status == "error"
    assert checks[0].error_message == "浏览器运行环境缺失，请在项目目录运行 python -m playwright install chromium 后重试。"


def test_monitor_scheduler_auto_opens_relogin_once_when_session_expires(tmp_path) -> None:
    settings = Settings(
        app_db_path=tmp_path / "app.db",
        ctrip_auto_relogin_cooldown_minutes=30,
    )
    first_task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    second_task = _build_scheduler_task(
        settings,
        next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
    )
    scraper = _ExpiredSessionScraper()
    scheduler = MonitorScheduler(settings, scraper)

    asyncio.run(scheduler.tick_once())

    assert [task.id for task in scraper.calls] == [second_task.id, first_task.id]
    assert scraper.session_manager.relogin_calls == 1
    first_checks = list_monitor_checks(settings, first_task.id)
    second_checks = list_monitor_checks(settings, second_task.id)
    assert [check.status for check in first_checks + second_checks] == [
        "session_expired",
        "session_expired",
    ]
    assert all(check.notification_sent is False for check in first_checks + second_checks)
    session_state = get_session_state(settings)
    assert session_state is not None
    assert session_state.session_status == "expired"
