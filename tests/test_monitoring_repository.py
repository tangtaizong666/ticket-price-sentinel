from datetime import date
import sqlite3

import pytest
from pydantic import ValidationError

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
