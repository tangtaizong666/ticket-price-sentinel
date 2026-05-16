from app.notifier import (
    build_monitor_target_url,
    build_notification_message,
    send_monitor_hit_alert,
    send_desktop_notification,
)


class ExplodingNotificationBackend:
    @staticmethod
    def notify(**_: object) -> None:
        raise RuntimeError("backend unavailable")


class RecordingNotificationBackend:
    calls: list[dict[str, object]] = []

    @classmethod
    def notify(cls, **kwargs: object) -> None:
        cls.calls.append(kwargs)


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


def test_build_notification_message_can_include_departure_date() -> None:
    title, message = build_notification_message(
        "北京",
        "上海",
        380,
        400,
        departure_date="2026-05-20",
    )

    assert title == "机票监控命中：北京 → 上海"
    assert message == "2026-05-20 · 当前最低价 ¥380，已达到你的目标价 ¥400"


def test_send_desktop_notification_returns_true_and_plays_sound(monkeypatch) -> None:
    RecordingNotificationBackend.calls = []
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", RecordingNotificationBackend)
    monkeypatch.setattr("app.notifier._play_notification_sound", lambda: sound_calls.append(True))

    result = send_desktop_notification("title", "message")

    assert result is True
    assert RecordingNotificationBackend.calls == [
        {
            "title": "title",
            "message": "message",
            "app_name": "Fly Ticket",
            "timeout": 15,
        }
    ]
    assert sound_calls == [True]


def test_send_desktop_notification_returns_false_but_still_plays_sound_on_backend_exception(
    monkeypatch,
) -> None:
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", ExplodingNotificationBackend)
    monkeypatch.setattr("app.notifier._play_notification_sound", lambda: sound_calls.append(True))

    result = send_desktop_notification("title", "message")

    assert result is False
    assert sound_calls == [True]


def test_send_monitor_hit_alert_includes_date_price_and_target_url(monkeypatch) -> None:
    RecordingNotificationBackend.calls = []
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", RecordingNotificationBackend)
    monkeypatch.setattr(
        "app.notifier._start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000/",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert result is True
    assert sound_calls == [True]
    assert RecordingNotificationBackend.calls == [
        {
            "title": "机票监控命中：北京 → 上海",
            "message": "2026-05-20 · 当前最低价 ¥380，已达到你的目标价 ¥400\n"
            "打开本地页面查看：http://127.0.0.1:8000/?monitor_task_id=3&monitor_hit_id=9",
            "app_name": "Fly Ticket",
            "timeout": 20,
        }
    ]


def test_send_monitor_hit_alert_returns_true_when_notification_backend_fails_but_sound_starts(
    monkeypatch,
) -> None:
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", ExplodingNotificationBackend)
    monkeypatch.setattr(
        "app.notifier._start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert result is True
    assert sound_calls == [True]


def test_monitor_hit_sound_is_submitted_to_background_executor(monkeypatch) -> None:
    submitted: list[object] = []

    class RecordingExecutor:
        def submit(self, callback):
            submitted.append(callback)
            return object()

    monkeypatch.setattr("app.notifier._notification_sound_executor", RecordingExecutor())

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
    )

    assert result is True
    assert len(submitted) == 1
    assert getattr(submitted[0], "__name__", "") == "_play_monitor_hit_sound"


def test_send_monitor_hit_alert_can_skip_popup_and_keep_sound(monkeypatch) -> None:
    RecordingNotificationBackend.calls = []
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", RecordingNotificationBackend)
    monkeypatch.setattr(
        "app.notifier._start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
        alert_popup_enabled=False,
        alert_sound_enabled=True,
    )

    assert result is True
    assert RecordingNotificationBackend.calls == []
    assert sound_calls == [True]


def test_send_monitor_hit_alert_can_skip_all_native_alerts(monkeypatch) -> None:
    RecordingNotificationBackend.calls = []
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", RecordingNotificationBackend)
    monkeypatch.setattr(
        "app.notifier._start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
        alert_popup_enabled=False,
        alert_sound_enabled=False,
    )

    assert result is False
    assert RecordingNotificationBackend.calls == []
    assert sound_calls == []


def test_send_monitor_hit_alert_sends_popup_when_sound_is_disabled(
    monkeypatch,
) -> None:
    RecordingNotificationBackend.calls = []
    sound_calls: list[bool] = []
    monkeypatch.setattr("app.notifier.notification", RecordingNotificationBackend)
    monkeypatch.setattr(
        "app.notifier._start_monitor_hit_sound_thread",
        lambda: sound_calls.append(True) or True,
    )

    result = send_monitor_hit_alert(
        base_url="http://127.0.0.1:8000",
        monitor_task_id=3,
        monitor_hit_id=9,
        origin_city="北京",
        destination_city="上海",
        departure_date="2026-05-20",
        current_price=380,
        target_price=400,
        alert_popup_enabled=True,
        alert_sound_enabled=False,
    )

    assert result is True
    assert RecordingNotificationBackend.calls == [
        {
            "title": "机票监控命中：北京 → 上海",
            "message": "2026-05-20 · 当前最低价 ¥380，已达到你的目标价 ¥400\n"
            "打开本地页面查看：http://127.0.0.1:8000/?monitor_task_id=3&monitor_hit_id=9",
            "app_name": "Fly Ticket",
            "timeout": 20,
        }
    ]
    assert sound_calls == []
