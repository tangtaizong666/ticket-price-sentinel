from datetime import UTC, date, datetime

from app.dashboard import load_home_dashboard
from app.db import init_db
from app.history import save_session_state
from app.models import MonitorTaskCreate
from app.monitoring import create_monitor_task, record_monitor_hit
from app.settings import Settings


def test_home_dashboard_guides_first_use_when_no_session_or_monitors(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    dashboard = load_home_dashboard(settings)

    assert dashboard.guide_title == "只要 3 步就能开始"
    assert dashboard.login_card.status == "未登录"
    assert dashboard.login_card.action_label == "去登录"
    assert dashboard.monitor_card.status == "还没有监控任务"
    assert dashboard.latest_hit_card.status == "还没有命中记录"



def test_home_dashboard_shows_intermediate_status_when_login_has_only_started(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)
    save_session_state(settings, "login_started")

    dashboard = load_home_dashboard(settings)

    assert dashboard.login_card.status == "登录进行中"
    assert dashboard.login_card.detail == "已打开登录窗口，请在携程完成登录"
    assert dashboard.login_card.action_label == "继续登录"


def test_home_dashboard_shows_ready_and_expired_session_states(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)
    save_session_state(settings, "ready", datetime(2026, 5, 10, 9, 0, tzinfo=UTC))

    ready_dashboard = load_home_dashboard(settings)

    assert ready_dashboard.login_card.status == "已登录"
    assert ready_dashboard.login_card.detail == "携程登录可用"
    assert ready_dashboard.login_card.action_label == "重新登录"

    save_session_state(settings, "expired")

    expired_dashboard = load_home_dashboard(settings)

    assert expired_dashboard.login_card.status == "登录已失效"
    assert expired_dashboard.login_card.detail == "请重新登录携程后再继续"
    assert expired_dashboard.login_card.action_label == "重新登录"



def test_home_dashboard_surfaces_login_monitor_and_latest_hit_state(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    init_db(settings)

    save_session_state(settings, "login_started")
    monitor = create_monitor_task(
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

    dashboard = load_home_dashboard(settings)

    assert dashboard.login_card.status == "登录进行中"
    assert dashboard.monitor_card.status == "1 个任务正在运行"
    assert dashboard.latest_hit_card.status == "bjs → sha"
    assert dashboard.latest_hit_card.detail == "最低价 ¥380"
    assert dashboard.latest_hit_card.monitor_task_id == monitor.id
    assert dashboard.latest_hit_card.monitor_hit_id == hit.id
