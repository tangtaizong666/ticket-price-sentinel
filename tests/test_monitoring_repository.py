from datetime import UTC, date, datetime, timedelta
import sqlite3

import pytest
from pydantic import ValidationError

from app.db import init_db
from app.models import MonitorTaskCreate
from app.monitoring import (
    claim_monitor_task_check,
    create_monitor_task,
    get_monitor_task,
    list_monitor_checks,
    list_monitor_tasks,
    record_monitor_check,
    record_monitor_hit,
)
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
    assert tasks[0].reminder_policy == "interval"
    assert tasks[0].unchanged_reminder_interval_minutes == 360
    assert hit.monitor_task_id == task.id
    assert hit.lowest_price == 380


def test_monitor_task_repository_migrates_legacy_task_columns(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    with sqlite3.connect(settings.app_db_path) as connection:
        connection.execute(
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
            )
            """
        )
        connection.execute(
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
                enabled,
                next_check_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "bjs",
                "sha",
                "2026-05-20",
                400,
                30,
                "[]",
                "[]",
                "[]",
                1,
                "2026-05-10T09:30:00+00:00",
                "2026-05-10T09:00:00+00:00",
                "2026-05-10T09:00:00+00:00",
            ),
        )

    init_db(settings)

    task = list_monitor_tasks(settings)[0]
    assert task.reminder_policy == "interval"
    assert task.unchanged_reminder_interval_minutes == 360


def test_claim_monitor_task_check_allows_only_one_matching_due_task_claim(tmp_path) -> None:
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
    original_next_check_at = task.next_check_at
    claimed_until = original_next_check_at + timedelta(minutes=5)

    first_claim = claim_monitor_task_check(
        settings,
        task.id,
        expected_next_check_at=original_next_check_at,
        claimed_until=claimed_until,
    )
    second_claim = claim_monitor_task_check(
        settings,
        task.id,
        expected_next_check_at=original_next_check_at,
        claimed_until=claimed_until + timedelta(minutes=5),
    )
    updated_task = get_monitor_task(settings, task.id)

    assert first_claim is True
    assert second_claim is False
    assert updated_task is not None
    assert updated_task.next_check_at == claimed_until


def test_monitor_check_results_keep_latest_thirty_per_task(tmp_path) -> None:
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
    start = datetime(2026, 5, 10, 9, 0, tzinfo=UTC)

    for index in range(31):
        record_monitor_check(
            settings,
            task_id=task.id,
            checked_at=start + timedelta(minutes=index),
            status="success",
            lowest_price=500 - index,
            is_target_hit=index >= 20,
            notification_sent=False,
            error_message=None,
            flights_snapshot=[{"flight_no": f"MU{index:04d}"}],
        )

    checks = list_monitor_checks(settings, task.id)

    assert len(checks) == 30
    assert checks[0].checked_at == start + timedelta(minutes=30)
    assert checks[-1].checked_at == start + timedelta(minutes=1)
    assert checks[0].lowest_price == 470
    assert checks[0].search_snapshot_json == [{"flight_no": "MU0030"}]


def test_record_monitor_hit_rejects_unknown_task_id(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    with pytest.raises(sqlite3.IntegrityError):
        record_monitor_hit(
            settings,
            task_id=999,
            lowest_price=380,
            flights_snapshot=[],
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "origin_city": "bjs",
                "destination_city": "bjs",
                "departure_date": date(2026, 5, 20),
                "target_price": 400,
                "check_interval_minutes": 30,
            },
            "origin and destination must be different",
        ),
        (
            {
                "origin_city": "bjs",
                "destination_city": "sha",
                "departure_date": date(2026, 5, 20),
                "target_price": 0,
                "check_interval_minutes": 30,
            },
            "target_price must be positive",
        ),
        (
            {
                "origin_city": "bjs",
                "destination_city": "sha",
                "departure_date": date(2026, 5, 20),
                "target_price": 400,
                "check_interval_minutes": 0,
            },
            "check_interval_minutes must be positive",
        ),
    ],
)
def test_monitor_task_create_validates_payload(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        MonitorTaskCreate(**payload)
