from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.filtering import calculate_lowest_price
from app.models import FlightResult, MonitorTask


@dataclass(slots=True)
class MonitorEvaluation:
    lowest_price: int | None
    should_notify: bool
    next_check_at: datetime
    flights_snapshot: list[dict]


def evaluate_monitor_result(
    task: MonitorTask,
    flights: list[FlightResult],
    *,
    now: datetime | None = None,
    cooldown_hours: int = 6,
) -> MonitorEvaluation:
    if now is None:
        now = datetime.now(UTC)

    lowest_price = calculate_lowest_price(flights)
    should_notify = False

    if lowest_price is not None and lowest_price <= task.target_price:
        should_notify = should_notify_for_price(task, lowest_price, now, cooldown_hours)

    return MonitorEvaluation(
        lowest_price=lowest_price,
        should_notify=should_notify,
        next_check_at=now + timedelta(minutes=task.check_interval_minutes),
        flights_snapshot=[flight.model_dump(mode="json") for flight in flights],
    )


def should_notify_for_price(
    task: MonitorTask,
    lowest_price: int,
    now: datetime,
    cooldown_hours: int,
) -> bool:
    if task.last_notified_price is None:
        return True
    if lowest_price < task.last_notified_price:
        return True
    if task.last_notified_at is None:
        return False

    cooldown = timedelta(hours=cooldown_hours)
    return now - task.last_notified_at >= cooldown


def should_run_task(task: MonitorTask, now: datetime) -> bool:
    return task.enabled and task.next_check_at <= now
