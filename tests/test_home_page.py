from datetime import date, time
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import create_app
from app.models import FlightResult, MonitorTaskCreate, SearchRequest
from app.monitoring import create_monitor_task, record_monitor_hit
from app.settings import Settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_settings_uses_path_objects_for_task_2_paths() -> None:
    settings = Settings()

    assert isinstance(settings.app_db_path, Path)
    assert isinstance(settings.playwright_profile_dir, Path)
    assert isinstance(settings.ctrip_snapshot_dir, Path)


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


def test_home_page_renders_first_use_dashboard() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    html = response.text
    assert "<title>Fly Ticket</title>" in html
    assert "<h1>Fly Ticket</h1>" in html
    assert 'id="first-use-guide"' in html
    assert 'id="login-status-card"' in html
    assert 'id="monitor-status-card"' in html
    assert 'id="latest-hit-card"' in html
    assert 'data-dashboard-action="relogin"' in html
    assert 'data-dashboard-action="search"' in html
    assert 'data-dashboard-action="create-monitor"' in html
    assert 'id="search-form"' in html
    assert 'method="get"' in html
    assert 'name="origin_city"' in html
    assert 'name="destination_city"' in html
    assert 'name="departure_date"' in html
    assert 'name="max_price"' in html
    assert 'data-filter-toggle="departure_time_filters"' in html
    assert 'data-filter-toggle="flight_attribute_filters"' in html
    assert 'data-filter-toggle="airline_filters"' in html
    assert 'data-filter-group="departure_time_filters"' in html
    assert 'data-filter-group="flight_attribute_filters"' in html
    assert 'data-filter-group="airline_filters"' in html
    assert 'class="filter-options"' in html
    assert 'id="selected-tags"' in html
    assert 'id="clear-filters"' in html
    assert 'id="search-summary"' in html
    assert 'id="results-list"' in html
    assert 'id="history-list"' in html
    assert 'id="monitor-form"' in html
    assert 'id="monitor-list"' in html
    assert 'id="monitor-detail"' in html
    assert 'data-monitor-action="edit"' in html
    assert 'data-monitor-action="toggle"' in html


def test_home_page_renders_view_hit_dashboard_action_when_latest_hit_exists(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)
    monitor = create_monitor_task(
        settings,
        MonitorTaskCreate(
            origin_city="北京",
            destination_city="上海",
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
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-dashboard-action="view-hit"' in html
    assert f'data-monitor-task-id="{monitor.id}"' in html
    assert f'data-monitor-hit-id="{hit.id}"' in html


    script = (PROJECT_ROOT / "app/static/app.js").read_text(encoding="utf-8")

    start = script.index("function setMonitorDetail(record) {")
    end = script.index("function createMonitorRow(record) {")
    set_monitor_detail_source = script[start:end]

    assert "monitorDetailElement.innerHTML" not in set_monitor_detail_source



def test_dashboard_js_wires_primary_actions_and_latest_hit_focus() -> None:
    script = (PROJECT_ROOT / "app/static/app.js").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "app/templates/index.html").read_text(encoding="utf-8")

    assert "handleDashboardAction" in script
    assert 'data-dashboard-action' in template
    assert 'requestJson("/api/session/relogin"' in script
    assert 'monitor_hit_id' in script
    assert 'scrollIntoView' in script


def test_dashboard_js_avoids_inner_html_and_opens_external_links_safely() -> None:
    script = (PROJECT_ROOT / "app/static/app.js").read_text(encoding="utf-8")

    assert ".innerHTML" not in script
    assert 'window.open(targetUrl, "_blank", "noopener,noreferrer")' in script


def test_monitor_detail_js_consumes_monitor_hit_id_for_deep_link_focus() -> None:
    script = (PROJECT_ROOT / "app/static/app.js").read_text(encoding="utf-8")

    assert 'params.get("monitor_hit_id")' in script
    assert 'article.dataset.monitorHitId = String(hit.id)' in script
    assert 'article.className = "monitor-hit-card"' in script
    assert 'querySelector(`[data-monitor-hit-id="${monitorHitId}"]`)' in script
    assert 'scrollIntoView({ behavior: "smooth", block: "center" })' in script


def test_monitor_detail_js_exposes_sound_feedback_for_focused_hit() -> None:
    script = (PROJECT_ROOT / "app/static/app.js").read_text(encoding="utf-8")

    assert "function playMonitorHitTone()" in script
    assert "AudioContext" in script
    assert "data-monitor-hit-tone" in script
    assert "playMonitorHitTone();" in script


def test_view_hit_dashboard_action_preserves_hit_specific_focus_behavior() -> None:
    script = (PROJECT_ROOT / "app/static/app.js").read_text(encoding="utf-8")

    start = script.index('if (action === "view-hit") {')
    end = script.index("    }\n}", start)
    view_hit_source = script[start:end]

    assert 'await loadMonitorDetail(monitorTaskId, monitorHitId || null);' in view_hit_source
    assert 'if (!monitorHitId) {' in view_hit_source
    assert 'focusAndScroll("#monitor-detail")' in view_hit_source


def test_home_page_renders_history_rows_with_stable_identifiers(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    app = create_app(settings=settings, scraper=FakeScraper())
    client = TestClient(app)

    client.post(
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
    )

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-history-id="1"' in html
    assert 'data-history-action="rerun" data-history-id="1"' in html
    assert 'data-history-action="edit" data-history-id="1"' in html
