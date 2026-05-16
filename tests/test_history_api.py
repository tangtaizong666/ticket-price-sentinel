from datetime import date, time

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import FlightResult, HistoryRecord, SearchRequest
from app.settings import Settings


class FakeScraper:
    async def search(self, request: SearchRequest) -> list[FlightResult]:
        return [
            FlightResult(
                flight_no="MU1234",
                airline="东航",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_time=time(8, 30),
                arrival_time=time(10, 45),
                is_direct=True,
                stop_info="直飞",
                price=560,
                deeplink_url="https://example.com/mu1234",
                fallback_search_url="https://example.com/search-mu1234",
            )
        ]


def _auth_headers(app) -> dict[str, str]:
    return {"X-FlyTicket-Token": app.state.local_request_token}


def test_history_detail_update_and_rerun_endpoints_work_end_to_end(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    create_payload = {
        "origin_city": "北京",
        "destination_city": "上海",
        "departure_date": date(2026, 5, 20).isoformat(),
        "max_price": 600,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
    }

    create_response = client.post("/api/search", json=create_payload, headers=_auth_headers(app))

    assert create_response.status_code == 200
    history_id = create_response.json()["history_id"]

    detail_response = client.get(f"/api/history/{history_id}")

    assert detail_response.status_code == 200
    assert detail_response.json() == {
        "id": history_id,
        "origin_city": "北京",
        "destination_city": "上海",
        "departure_date": "2026-05-20",
        "max_price": 600,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
        "last_searched_at": detail_response.json()["last_searched_at"],
        "created_at": detail_response.json()["created_at"],
        "updated_at": detail_response.json()["updated_at"],
    }

    update_payload = {
        "origin_city": "北京",
        "destination_city": "广州",
        "departure_date": date(2026, 5, 22).isoformat(),
        "max_price": 700,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
    }

    update_response = client.put(
        f"/api/history/{history_id}",
        json=update_payload,
        headers=_auth_headers(app),
    )

    assert update_response.status_code == 200
    assert update_response.json() == {
        "id": history_id,
        "origin_city": "北京",
        "destination_city": "广州",
        "departure_date": "2026-05-22",
        "max_price": 700,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
        "last_searched_at": update_response.json()["last_searched_at"],
        "created_at": update_response.json()["created_at"],
        "updated_at": update_response.json()["updated_at"],
    }

    rerun_response = client.post(
        f"/api/history/{history_id}/rerun",
        headers=_auth_headers(app),
    )

    assert rerun_response.status_code == 200
    assert rerun_response.json()["lowest_price"] == 560
    assert rerun_response.json()["history_id"] != history_id
    assert rerun_response.json()["flights"] == [
        {
            "flight_no": "MU1234",
            "airline": "东航",
            "origin_city": "北京",
            "destination_city": "广州",
            "departure_time": "08:30:00",
            "arrival_time": "10:45:00",
            "is_direct": True,
            "stop_info": "直飞",
            "price": 560,
            "deeplink_url": "https://example.com/mu1234",
            "fallback_search_url": "https://example.com/search-mu1234",
        }
    ]


def test_update_history_endpoint_returns_404_for_missing_record(tmp_path, monkeypatch) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    update_payload = {
        "origin_city": "北京",
        "destination_city": "广州",
        "departure_date": date(2026, 5, 22).isoformat(),
        "max_price": 700,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
    }

    def fail_update_history(*args, **kwargs) -> HistoryRecord:
        raise AssertionError("update_history should not be called when record is missing")

    monkeypatch.setattr("app.main.update_history", fail_update_history)

    response = client.put(
        "/api/history/999",
        json=update_payload,
        headers=_auth_headers(app),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "History record not found"}


def test_delete_history_endpoint_removes_existing_record(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    create_response = client.post(
        "/api/search",
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
            "max_price": 600,
            "departure_time_filters": ["上午"],
            "flight_attribute_filters": ["直飞"],
            "airline_filters": ["东航"],
        },
        headers=_auth_headers(app),
    )
    history_id = create_response.json()["history_id"]

    delete_response = client.delete(
        f"/api/history/{history_id}",
        headers=_auth_headers(app),
    )
    detail_response = client.get(f"/api/history/{history_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": 1}
    assert detail_response.status_code == 404


def test_delete_history_endpoint_returns_404_for_missing_record(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    response = client.delete("/api/history/999", headers=_auth_headers(app))

    assert response.status_code == 404
    assert response.json() == {"detail": "History record not found"}
