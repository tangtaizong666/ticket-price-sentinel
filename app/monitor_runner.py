from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.filtering import apply_filters, calculate_lowest_price
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
    cooldown_enabled: bool = True,
) -> MonitorEvaluation:
    if now is None:
        now = datetime.now(UTC)

    filtered_flights = apply_filters(flights, task)
    lowest_price = calculate_lowest_price(filtered_flights)
    should_notify = False

    if lowest_price is not None and lowest_price <= task.target_price:
        should_notify = should_notify_for_price(
            task,
            lowest_price,
            now,
            cooldown_hours,
            cooldown_enabled=cooldown_enabled,
        )

    return MonitorEvaluation(
        lowest_price=lowest_price,
        should_notify=should_notify,
        next_check_at=now + timedelta(minutes=task.check_interval_minutes),
        flights_snapshot=[flight.model_dump(mode="json") for flight in filtered_flights],
    )


def should_notify_for_price(
    task: MonitorTask,
    lowest_price: int,
    now: datetime,
    cooldown_hours: int,
    *,
    cooldown_enabled: bool = True,
) -> bool:
    if not cooldown_enabled:
        return True
    if task.reminder_policy == "every_check":
        return True
    if task.last_notified_price is None:
        return True
    if lowest_price < task.last_notified_price:
        return True
    if task.last_notified_at is None:
        return False
    if task.reminder_policy == "no_repeat":
        return False

    interval_minutes = task.unchanged_reminder_interval_minutes or (cooldown_hours * 60)
    cooldown = timedelta(minutes=interval_minutes)
    return now - task.last_notified_at >= cooldown


def should_run_task(task: MonitorTask, now: datetime) -> bool:
    return task.enabled and task.next_check_at <= now
