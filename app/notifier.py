from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import logging
import os
import time

from plyer import notification


logger = logging.getLogger(__name__)
_notification_sound_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="fly-ticket-alert",
)


def build_monitor_target_url(base_url: str, monitor_task_id: int, monitor_hit_id: int) -> str:
    normalized_base_url = base_url.rstrip("/")
    return f"{normalized_base_url}/?monitor_task_id={monitor_task_id}&monitor_hit_id={monitor_hit_id}"


def build_notification_message(
    origin_city: str,
    destination_city: str,
    current_price: int,
    target_price: int,
    *,
    departure_date: str | date | datetime | None = None,
) -> tuple[str, str]:
    title = f"机票监控命中：{origin_city} → {destination_city}"
    date_prefix = f"{_format_departure_date(departure_date)} · " if departure_date else ""
    message = f"{date_prefix}当前最低价 ¥{current_price}，已达到你的目标价 ¥{target_price}"
    return title, message


def send_desktop_notification(title: str, message: str) -> bool:
    sent = _send_desktop_notification(title, message, timeout=15)
    _play_notification_sound()
    return sent


def send_monitor_hit_alert(
    *,
    base_url: str,
    monitor_task_id: int,
    monitor_hit_id: int,
    origin_city: str,
    destination_city: str,
    departure_date: str | date | datetime,
    current_price: int,
    target_price: int,
    alert_sound_enabled: bool = True,
    alert_popup_enabled: bool = True,
) -> bool:
    target_url = build_monitor_target_url(base_url, monitor_task_id, monitor_hit_id)
    title, message = build_notification_message(
        origin_city,
        destination_city,
        current_price,
        target_price,
        departure_date=departure_date,
    )
    desktop_sent = False
    if alert_popup_enabled:
        desktop_sent = _send_desktop_notification(
            title,
            f"{message}\n打开本地页面查看：{target_url}",
            timeout=20,
        )
    sound_started = _start_monitor_hit_sound_thread() if alert_sound_enabled else False
    return desktop_sent or sound_started


def _send_desktop_notification(title: str, message: str, *, timeout: int) -> bool:
    sent = True
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Fly Ticket",
            timeout=timeout,
        )
    except Exception:
        logger.exception("Desktop notification backend failed")
        sent = False
    return sent


def _format_departure_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _start_monitor_hit_sound_thread() -> bool:
    try:
        _notification_sound_executor.submit(_play_monitor_hit_sound)
    except Exception:
        logger.exception("Notification sound dispatch failed")
        return False
    return True


def _play_monitor_hit_sound() -> None:
    if os.name != "nt":
        return
    try:
        import winsound

        for frequency, duration_ms in ((1046, 180), (1318, 180), (1568, 360)):
            winsound.Beep(frequency, duration_ms)
            time.sleep(0.08)
    except Exception:
        logger.exception("Monitor hit notification sound failed")
        _play_notification_sound()


def _play_notification_sound() -> None:
    if os.name != "nt":
        return
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        logger.exception("Notification sound failed")
