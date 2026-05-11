from app.notifier import (
    build_monitor_target_url,
    build_notification_message,
    send_desktop_notification,
)


class ExplodingNotificationBackend:
    @staticmethod
    def notify(**_: object) -> None:
        raise RuntimeError("backend unavailable")


def test_build_monitor_target_url_normalizes_base_url_and_points_back_to_local_hit_view() -> None:
    url = build_monitor_target_url(
        base_url="http://127.0.0.1:8000/",
        monitor_task_id=3,
        monitor_hit_id=9,
    )

    assert url == "http://127.0.0.1:8000/?monitor_task_id=3&monitor_hit_id=9"


def test_build_notification_message_contains_route_and_price() -> None:
    title, message = build_notification_message("bjs", "sha", 380, 400)

    assert title == "机票监控命中：bjs → sha"
    assert message == "当前最低价 ¥380，已达到你的目标价 ¥400"


def test_send_desktop_notification_swallows_backend_exceptions(monkeypatch) -> None:
    monkeypatch.setattr("app.notifier.notification", ExplodingNotificationBackend)

    send_desktop_notification("title", "message")
