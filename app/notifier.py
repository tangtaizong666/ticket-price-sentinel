from plyer import notification


def build_monitor_target_url(base_url: str, monitor_task_id: int, monitor_hit_id: int) -> str:
    normalized_base_url = base_url.rstrip("/")
    return f"{normalized_base_url}/?monitor_task_id={monitor_task_id}&monitor_hit_id={monitor_hit_id}"


def build_notification_message(
    origin_city: str,
    destination_city: str,
    current_price: int,
    target_price: int,
) -> tuple[str, str]:
    title = f"机票监控命中：{origin_city} → {destination_city}"
    message = f"当前最低价 ¥{current_price}，已达到你的目标价 ¥{target_price}"
    return title, message


def send_desktop_notification(title: str, message: str) -> None:
    try:
        notification.notify(title=title, message=message, app_name="Fly Ticket")
    except Exception:
        return
