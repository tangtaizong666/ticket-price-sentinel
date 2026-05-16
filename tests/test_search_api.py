from datetime import date, time

from fastapi.testclient import TestClient

from app.ctrip_scraper import ScrapeFailedError, SessionExpiredError
from app.history import get_session_state
from app.main import create_app
from app.models import FlightResult, SearchRequest
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
            ),
            FlightResult(
                flight_no="CA5678",
                airline="国航",
                origin_city=request.origin_city,
                destination_city=request.destination_city,
                departure_time=time(14, 0),
                arrival_time=time(17, 10),
                is_direct=False,
                stop_info="经停西安",
                price=620,
                deeplink_url="https://example.com/ca5678",
                fallback_search_url="https://example.com/search-ca5678",
            ),
        ]


class ExpiredScraper:
    async def search(self, request: SearchRequest) -> list[FlightResult]:
        raise SessionExpiredError("Ctrip session expired; relogin required")


class BrokenScraper:
    async def search(self, request: SearchRequest) -> list[FlightResult]:
        raise ScrapeFailedError("Unable to parse any flights from Ctrip search results")


class CountingSessionManager:
    def __init__(self) -> None:
        self.relogin_calls = 0

    async def open_relogin_window(self):
        self.relogin_calls += 1
        return {"status": "login_started", "url": "https://example.invalid/session"}

    async def close(self):
        pass


def _auth_headers(app) -> dict[str, str]:
    return {"X-FlyTicket-Token": app.state.local_request_token}


def test_search_api_filters_results_returns_lowest_price_and_saves_history(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    payload = {
        "origin_city": "北京",
        "destination_city": "上海",
        "departure_date": date(2026, 5, 20).isoformat(),
        "max_price": 600,
        "departure_time_filters": ["上午"],
        "flight_attribute_filters": ["直飞"],
        "airline_filters": ["东航"],
    }

    search_response = client.post("/api/search", json=payload, headers=_auth_headers(app))

    assert search_response.status_code == 200
    assert search_response.json()["lowest_price"] == 560
    assert search_response.json()["history_id"] is not None
    assert search_response.json()["flights"] == [
        {
            "flight_no": "MU1234",
            "airline": "东航",
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_time": "08:30:00",
            "arrival_time": "10:45:00",
            "is_direct": True,
            "stop_info": "直飞",
            "price": 560,
            "deeplink_url": "https://example.com/mu1234",
            "fallback_search_url": "https://example.com/search-mu1234",
        }
    ]

    history_response = client.get("/api/history")

    assert history_response.status_code == 200
    assert history_response.json() == [
        {
            "id": search_response.json()["history_id"],
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": "2026-05-20",
            "max_price": 600,
            "departure_time_filters": ["上午"],
            "flight_attribute_filters": ["直飞"],
            "airline_filters": ["东航"],
            "last_searched_at": history_response.json()[0]["last_searched_at"],
            "created_at": history_response.json()[0]["created_at"],
            "updated_at": history_response.json()[0]["updated_at"],
        }
    ]
    session_state = get_session_state(settings)
    assert session_state is not None
    assert session_state.session_status == "ready"
    assert session_state.last_successful_scrape_at is not None


def test_search_api_returns_503_when_scraper_session_expires(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=ExpiredScraper())
    client = TestClient(app)

    response = client.post(
        "/api/search",
        headers=_auth_headers(app),
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "relogin_required",
        "message": "携程登录已失效，请重新登录后再继续",
    }
    session_state = get_session_state(settings)
    assert session_state is not None
    assert session_state.session_status == "expired"


def test_search_api_auto_opens_relogin_once_within_cooldown_when_session_expires(tmp_path) -> None:
    settings = Settings(
        app_db_path=tmp_path / "app.db",
        ctrip_session_url="https://example.invalid/session",
        ctrip_auto_relogin_cooldown_minutes=30,
    )
    session_manager = CountingSessionManager()
    app = create_app(
        settings=settings,
        scraper=ExpiredScraper(),
        session_manager=session_manager,
    )
    client = TestClient(app)
    payload = {
        "origin_city": "北京",
        "destination_city": "上海",
        "departure_date": date(2026, 5, 20).isoformat(),
    }

    first_response = client.post("/api/search", json=payload, headers=_auth_headers(app))
    second_response = client.post("/api/search", json=payload, headers=_auth_headers(app))

    assert first_response.status_code == 503
    assert second_response.status_code == 503
    assert session_manager.relogin_calls == 1


def test_search_api_returns_502_when_scraper_cannot_parse_results(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=BrokenScraper())
    client = TestClient(app)

    response = client.post(
        "/api/search",
        headers=_auth_headers(app),
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": "scrape_failed",
        "message": "这次没有成功读取携程结果，请重试一次",
    }


def test_history_rerun_saves_ready_session_state_after_success(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    search_response = client.post(
        "/api/search",
        headers=_auth_headers(app),
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
        },
    )
    history_id = search_response.json()["history_id"]

    rerun_response = client.post(f"/api/history/{history_id}/rerun", headers=_auth_headers(app))

    assert rerun_response.status_code == 200
    session_state = get_session_state(settings)
    assert session_state is not None
    assert session_state.session_status == "ready"
    assert session_state.last_successful_scrape_at is not None


def test_history_rerun_returns_503_and_saves_expired_when_scraper_session_expires(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    setup_app = create_app(settings=settings, scraper=FakeScraper())
    setup_client = TestClient(setup_app)
    search_response = setup_client.post(
        "/api/search",
        headers=_auth_headers(setup_app),
        json={
            "origin_city": "北京",
            "destination_city": "上海",
            "departure_date": date(2026, 5, 20).isoformat(),
        },
    )
    history_id = search_response.json()["history_id"]

    app = create_app(settings=settings, scraper=ExpiredScraper())
    client = TestClient(app)
    response = client.post(f"/api/history/{history_id}/rerun", headers=_auth_headers(app))

    assert response.status_code == 503
    assert response.json() == {
        "error": "relogin_required",
        "message": "携程登录已失效，请重新登录后再继续",
    }
    session_state = get_session_state(settings)
    assert session_state is not None
    assert session_state.session_status == "expired"
