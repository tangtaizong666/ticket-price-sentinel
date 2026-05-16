from datetime import UTC, date, datetime
import sqlite3

from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app
from app.models import MonitorTaskCreate
from app.monitoring import create_monitor_task, record_monitor_check
from app.settings import Settings


def _seed_monitor_hit(
    settings: Settings,
    monitor_id: int,
    *,
    lowest_price: int = 380,
    hit_at: datetime | None = None,
    snapshot_json: str = "[]",
) -> int:
    timestamp = (hit_at or datetime(2026, 5, 10, 9, 0, tzinfo=UTC)).isoformat()
    with connect(settings) as connection:
        cursor = connection.execute(
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
        return int(cursor.lastrowid)


def _seed_monitor_check(
    settings: Settings,
    monitor_id: int,
    *,
    checked_at: datetime,
    status: str = "success",
    lowest_price: int | None = 380,
    is_target_hit: bool = True,
    notification_sent: bool = False,
    error_message: str | None = None,
) -> None:
    record_monitor_check(
        settings,
        task_id=monitor_id,
        checked_at=checked_at,
        status=status,
        lowest_price=lowest_price,
        is_target_hit=is_target_hit,
        notification_sent=notification_sent,
        error_message=error_message,
        flights_snapshot=[{"flight_no": "MU1234", "price": lowest_price}],
    )


def _auth_headers(app) -> dict[str, str]:
    return {"X-FlyTicket-Token": app.state.local_request_token}


def test_monitor_api_creates_lists_gets_and_updates_tasks(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    create_response = client.post(
        "/api/monitors",
        headers=_auth_headers(app),
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
    assert created_monitor["reminder_policy"] == "interval"
    assert created_monitor["unchanged_reminder_interval_minutes"] == 360
    assert created_monitor["alert_sound_enabled"] is True
    assert created_monitor["alert_taskbar_enabled"] is True
    assert created_monitor["alert_popup_enabled"] is True
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
            "reminder_policy": "interval",
            "unchanged_reminder_interval_minutes": 360,
            "alert_sound_enabled": True,
            "alert_taskbar_enabled": True,
            "alert_popup_enabled": True,
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
        "reminder_policy": "interval",
        "unchanged_reminder_interval_minutes": 360,
        "alert_sound_enabled": True,
        "alert_taskbar_enabled": True,
        "alert_popup_enabled": True,
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
        headers=_auth_headers(app),
        json={
            "origin_city": "bjs",
            "destination_city": "can",
            "departure_date": "2026-05-22",
            "target_price": 380,
            "check_interval_minutes": 60,
            "departure_time_filters": [],
            "flight_attribute_filters": [],
            "airline_filters": [],
            "reminder_policy": "every_check",
            "unchanged_reminder_interval_minutes": 45,
            "alert_sound_enabled": False,
            "alert_taskbar_enabled": False,
            "alert_popup_enabled": False,
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
        "reminder_policy": "every_check",
        "unchanged_reminder_interval_minutes": 45,
        "alert_sound_enabled": False,
        "alert_taskbar_enabled": False,
        "alert_popup_enabled": False,
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
    assert updated_detail_response.json()["reminder_policy"] == "every_check"
    assert updated_detail_response.json()["unchanged_reminder_interval_minutes"] == 45
    assert updated_detail_response.json()["alert_sound_enabled"] is False
    assert updated_detail_response.json()["alert_taskbar_enabled"] is False
    assert updated_detail_response.json()["alert_popup_enabled"] is False
    assert updated_detail_response.json()["enabled"] is False




def test_monitor_api_lists_hits_for_task_in_reverse_chronological_order(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

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


def test_monitor_api_can_delete_hit_for_task(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    created_monitor = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
        ),
    )
    hit_id = _seed_monitor_hit(
        settings,
        created_monitor.id,
        lowest_price=390,
        hit_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    )

    delete_response = client.delete(
        f"/api/monitors/{created_monitor.id}/hits/{hit_id}",
        headers=_auth_headers(app),
    )
    list_response = client.get(f"/api/monitors/{created_monitor.id}/hits")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": 1}
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_monitor_api_delete_hit_returns_404_for_missing_hit(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    created_monitor = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
        ),
    )

    response = client.delete(
        f"/api/monitors/{created_monitor.id}/hits/999",
        headers=_auth_headers(app),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Monitor hit not found"}


def test_monitor_alerts_api_returns_empty_list_when_there_are_no_new_hits(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/api/monitor-alerts?after_id=0")

    assert response.status_code == 200
    assert response.json() == {"alerts": []}


def test_monitor_alerts_api_lists_new_hits_in_id_order_and_filters_seen_hits(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

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
    first_hit_id = _seed_monitor_hit(
        settings,
        created_monitor.id,
        lowest_price=390,
        hit_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
    )
    second_hit_id = _seed_monitor_hit(
        settings,
        created_monitor.id,
        lowest_price=360,
        hit_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )

    response = client.get("/api/monitor-alerts?after_id=0")
    filtered_response = client.get(f"/api/monitor-alerts?after_id={first_hit_id}")

    assert response.status_code == 200
    assert response.json() == {
        "alerts": [
            {
                "hit_id": first_hit_id,
                "monitor_task_id": created_monitor.id,
                "origin_city": "bjs",
                "destination_city": "sha",
                "departure_date": "2026-05-20",
                "lowest_price": 390,
                "target_price": 400,
                "hit_at": "2026-05-10T09:00:00Z",
                "title": "机票监控命中：bjs → sha",
                "message": "2026-05-20 · 当前最低价 ¥390，已达到你的目标价 ¥400",
                "url": f"http://127.0.0.1:8000/?monitor_task_id={created_monitor.id}&monitor_hit_id={first_hit_id}",
                "alert_sound_enabled": True,
                "alert_taskbar_enabled": True,
                "alert_popup_enabled": True,
            },
            {
                "hit_id": second_hit_id,
                "monitor_task_id": created_monitor.id,
                "origin_city": "bjs",
                "destination_city": "sha",
                "departure_date": "2026-05-20",
                "lowest_price": 360,
                "target_price": 400,
                "hit_at": "2026-05-10T10:00:00Z",
                "title": "机票监控命中：bjs → sha",
                "message": "2026-05-20 · 当前最低价 ¥360，已达到你的目标价 ¥400",
                "url": f"http://127.0.0.1:8000/?monitor_task_id={created_monitor.id}&monitor_hit_id={second_hit_id}",
                "alert_sound_enabled": True,
                "alert_taskbar_enabled": True,
                "alert_popup_enabled": True,
            },
        ]
    }
    assert filtered_response.status_code == 200
    assert filtered_response.json() == {"alerts": [response.json()["alerts"][1]]}


def test_monitor_alerts_api_ignores_orphan_hits_without_raising_500(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)
    timestamp = datetime(2026, 5, 10, 9, 0, tzinfo=UTC).isoformat()

    with sqlite3.connect(settings.app_db_path) as connection:
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
            (999, 380, timestamp, "[]", 380, timestamp),
        )

    response = client.get("/api/monitor-alerts?after_id=0")

    assert response.status_code == 200
    assert response.json() == {"alerts": []}


def test_monitor_api_returns_404_for_hits_of_missing_record(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/api/monitors/999/hits")

    assert response.status_code == 404
    assert response.json() == {"detail": "Monitor task not found"}


def test_monitor_api_lists_checks_for_task_in_reverse_chronological_order(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    created_monitor = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
        ),
    )
    _seed_monitor_check(
        settings,
        created_monitor.id,
        checked_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        lowest_price=420,
        is_target_hit=False,
    )
    _seed_monitor_check(
        settings,
        created_monitor.id,
        checked_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
        status="error",
        lowest_price=None,
        is_target_hit=False,
        error_message="boom",
    )

    response = client.get(f"/api/monitors/{created_monitor.id}/checks")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": response.json()[0]["id"],
            "monitor_task_id": created_monitor.id,
            "checked_at": "2026-05-10T10:00:00Z",
            "status": "error",
            "lowest_price": None,
            "is_target_hit": False,
            "notification_sent": False,
            "error_message": "boom",
            "search_snapshot_json": [{"flight_no": "MU1234", "price": None}],
            "created_at": "2026-05-10T10:00:00Z",
        },
        {
            "id": response.json()[1]["id"],
            "monitor_task_id": created_monitor.id,
            "checked_at": "2026-05-10T09:00:00Z",
            "status": "success",
            "lowest_price": 420,
            "is_target_hit": False,
            "notification_sent": False,
            "error_message": None,
            "search_snapshot_json": [{"flight_no": "MU1234", "price": 420}],
            "created_at": "2026-05-10T09:00:00Z",
        },
    ]


def test_monitor_api_can_clear_checks_for_task(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    created_monitor = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="bjs",
            destination_city="sha",
            departure_date=date(2026, 5, 20),
            target_price=400,
            check_interval_minutes=30,
        ),
    )
    _seed_monitor_check(
        settings,
        created_monitor.id,
        checked_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        lowest_price=420,
        is_target_hit=False,
    )

    delete_response = client.delete(
        f"/api/monitors/{created_monitor.id}/checks",
        headers=_auth_headers(app),
    )
    list_response = client.get(f"/api/monitors/{created_monitor.id}/checks")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": 1}
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_monitor_api_returns_404_for_checks_of_missing_record(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/api/monitors/999/checks")

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
