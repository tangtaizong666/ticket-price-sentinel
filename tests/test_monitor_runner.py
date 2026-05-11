from datetime import UTC, date, datetime, timedelta, time
import asyncio

from app.db import init_db
from app.models import FlightResult, MonitorTask, MonitorTaskCreate
from app.monitor_runner import evaluate_monitor_result, should_run_task
from app.monitoring import create_monitor_task, get_monitor_task, list_monitor_hits
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


def test_evaluate_monitor_result_does_not_notify_for_same_price_repeat_hit() -> None:
    task = _build_task(last_notified_price=380)

    evaluation = evaluate_monitor_result(task, _build_flights(380, 420))

    assert evaluation.lowest_price == 380
    assert evaluation.should_notify is False


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



def test_monitor_scheduler_records_first_hit_and_updates_runtime_state(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    task = _build_scheduler_task(settings, next_check_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC))
    flights = _build_flights(380, 420)
    scraper = _StubScraper(flights)
    notifications: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.monitor_scheduler.send_desktop_notification",
        lambda title, message: notifications.append((title, message)),
    )

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    hits = list_monitor_hits(settings, task.id)
    updated_task = get_monitor_task(settings, task.id)

    assert len(scraper.calls) == 1
    assert len(hits) == 1
    assert hits[0].lowest_price == 380
    assert notifications == [("机票监控命中：bjs → sha", "当前最低价 ¥380，已达到你的目标价 ¥400")]
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
    notifications: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.monitor_scheduler.send_desktop_notification",
        lambda title, message: notifications.append((title, message)),
    )

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    due_hits = list_monitor_hits(settings, due_task.id)
    waiting_hits = list_monitor_hits(settings, waiting_task.id)
    updated_due_task = get_monitor_task(settings, due_task.id)
    updated_waiting_task = get_monitor_task(settings, waiting_task.id)

    assert [task.id for task in scraper.calls] == [due_task.id]
    assert due_hits == []
    assert waiting_hits == []
    assert notifications == []
    assert updated_due_task is not None
    assert updated_due_task.last_checked_at is not None
    assert updated_due_task.last_seen_lowest_price == 380
    assert updated_due_task.last_notified_price == 380
    assert updated_waiting_task is not None
    assert updated_waiting_task.last_checked_at is None



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
    notifications: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.monitor_scheduler.send_desktop_notification",
        lambda title, message: notifications.append((title, message)),
    )

    scheduler = MonitorScheduler(settings, scraper)
    asyncio.run(scheduler.tick_once())

    failing_hits = list_monitor_hits(settings, failing_task.id)
    succeeding_hits = list_monitor_hits(settings, succeeding_task.id)
    updated_failing_task = get_monitor_task(settings, failing_task.id)
    updated_succeeding_task = get_monitor_task(settings, succeeding_task.id)

    assert [task.id for task in scraper.calls] == [succeeding_task.id, failing_task.id]
    assert failing_hits == []
    assert len(succeeding_hits) == 1
    assert succeeding_hits[0].lowest_price == 380
    assert notifications == [
        ("机票监控命中：bjs → sha", "当前最低价 ¥380，已达到你的目标价 ¥400")
    ]
    assert updated_failing_task is not None
    assert updated_failing_task.last_checked_at is not None
    assert updated_failing_task.next_check_at > updated_failing_task.last_checked_at
    assert updated_succeeding_task is not None
    assert updated_succeeding_task.last_checked_at is not None
