from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app
from app.models import MonitorTaskCreate
from app.monitoring import create_monitor_task
from app.settings import Settings


def _seed_monitor_hit(
    settings: Settings,
    monitor_id: int,
    *,
    lowest_price: int = 380,
    hit_at: datetime | None = None,
    snapshot_json: str = "[]",
) -> None:
    timestamp = (hit_at or datetime(2026, 5, 10, 9, 0, tzinfo=UTC)).isoformat()
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO monitor_hits (
                monitor_task_id,
                hit_price,
                hit_at,
                search_snapshot_json,
                lowest_price,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                monitor_id,
                lowest_price,
                timestamp,
                snapshot_json,
                lowest_price,
                timestamp,
            ),
        )


def test_monitor_api_creates_lists_gets_and_updates_tasks(tmp_path) -> None:
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
    created_monitor = create_response.json()
    monitor_id = created_monitor["id"]
    assert created_monitor["target_price"] == 400
    assert created_monitor["check_interval_minutes"] == 30
    assert created_monitor["enabled"] is True

    list_response = client.get("/api/monitors")

    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            "id": monitor_id,
            "origin_city": "bjs",
            "destination_city": "sha",
            "departure_date": "2026-05-20",
            "target_price": 400,
            "check_interval_minutes": 30,
            "departure_time_filters": ["上午"],
            "flight_attribute_filters": ["直飞"],
            "airline_filters": ["东航"],
            "enabled": True,
            "last_checked_at": None,
            "next_check_at": list_response.json()[0]["next_check_at"],
            "last_seen_lowest_price": None,
            "last_notified_at": None,
            "last_notified_price": None,
            "created_at": list_response.json()[0]["created_at"],
            "updated_at": list_response.json()[0]["updated_at"],
        }
    ]

    detail_response = client.get(f"/api/monitors/{monitor_id}")

    assert detail_response.status_code == 200
    assert detail_response.json() == {
        "id": monitor_id,
        "origin_city": "bjs",
        "destination_city": "sha",
        "departure_date": "2026-05-20",
        "target_price": 400,
        "check_interval_minutes": 30,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
        "enabled": True,
        "last_checked_at": None,
        "next_check_at": detail_response.json()["next_check_at"],
        "last_seen_lowest_price": None,
        "last_notified_at": None,
        "last_notified_price": None,
        "created_at": detail_response.json()["created_at"],
        "updated_at": detail_response.json()["updated_at"],
    }

    update_response = client.put(
        f"/api/monitors/{monitor_id}",
        json={
            "origin_city": "bjs",
            "destination_city": "can",
            "departure_date": "2026-05-22",
            "target_price": 380,
            "check_interval_minutes": 60,
            "departure_time_filters": [],
            "flight_attribute_filters": [],
            "airline_filters": [],
            "enabled": False,
        },
    )

    assert update_response.status_code == 200
    assert update_response.json() == {
        "id": monitor_id,
        "origin_city": "bjs",
        "destination_city": "can",
        "departure_date": "2026-05-22",
        "target_price": 380,
        "check_interval_minutes": 60,
        "departure_time_filters": [],
        "flight_attribute_filters": [],
        "airline_filters": [],
        "enabled": False,
        "last_checked_at": None,
        "next_check_at": update_response.json()["next_check_at"],
        "last_seen_lowest_price": None,
        "last_notified_at": None,
        "last_notified_price": None,
        "created_at": update_response.json()["created_at"],
        "updated_at": update_response.json()["updated_at"],
    }

    updated_detail_response = client.get(f"/api/monitors/{monitor_id}")

    assert updated_detail_response.status_code == 200
    assert updated_detail_response.json()["destination_city"] == "can"
    assert updated_detail_response.json()["target_price"] == 380
    assert updated_detail_response.json()["check_interval_minutes"] == 60
    assert updated_detail_response.json()["enabled"] is False




def test_monitor_api_lists_hits_for_task_in_reverse_chronological_order(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings))

    created_monitor = create_monitor_task(
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
    _seed_monitor_hit(
        settings,
        created_monitor.id,
        lowest_price=390,
        hit_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    )
    _seed_monitor_hit(
        settings,
        created_monitor.id,
        lowest_price=360,
        hit_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
        snapshot_json='[{"flight_no":"MU1234","airline":"东航","price":360,"deeplink_url":"https://example.com/flight","fallback_search_url":"https://example.com/results"}]',
    )

    response = client.get(f"/api/monitors/{created_monitor.id}/hits")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": response.json()[0]["id"],
            "monitor_task_id": created_monitor.id,
            "hit_price": 360,
            "hit_at": "2026-05-10T10:00:00Z",
            "search_snapshot_json": [
                {
                    "flight_no": "MU1234",
                    "airline": "东航",
                    "price": 360,
                    "deeplink_url": "https://example.com/flight",
                    "fallback_search_url": "https://example.com/results",
                }
            ],
            "lowest_price": 360,
            "created_at": "2026-05-10T10:00:00Z",
        },
        {
            "id": response.json()[1]["id"],
            "monitor_task_id": created_monitor.id,
            "hit_price": 390,
            "hit_at": "2026-05-10T09:00:00Z",
            "search_snapshot_json": [],
            "lowest_price": 390,
            "created_at": "2026-05-10T09:00:00Z",
        },
    ]


def test_monitor_api_returns_404_for_hits_of_missing_record(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(create_app(settings=settings))

    response = client.get("/api/monitors/999/hits")

    assert response.status_code == 404
    assert response.json() == {"detail": "Monitor task not found"}


def test_app_lifecycle_starts_and_stops_monitor_scheduler(tmp_path, monkeypatch) -> None:
    events: list[str] = []

    class _StubMonitorScheduler:
        def __init__(self, settings, scraper) -> None:
            self.settings = settings
            self.scraper = scraper

        async def start(self) -> None:
            events.append("start")

        async def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr("app.main.MonitorScheduler", _StubMonitorScheduler)

    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)

    assert events == []
    with TestClient(app):
        assert events == ["start"]
    assert events == ["start", "stop"]
