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
    task: MonitorTask, flights: list[FlightResult]
) -> MonitorEvaluation:
    lowest_price = calculate_lowest_price(flights)
    should_notify = False

    if lowest_price is not None and lowest_price <= task.target_price:
        should_notify = (
            task.last_notified_price is None
            or lowest_price < task.last_notified_price
        )

    return MonitorEvaluation(
        lowest_price=lowest_price,
        should_notify=should_notify,
        next_check_at=datetime.now(UTC)
        + timedelta(minutes=task.check_interval_minutes),
        flights_snapshot=[flight.model_dump(mode="json") for flight in flights],
    )


def should_run_task(task: MonitorTask, now: datetime) -> bool:
    return task.enabled and task.next_check_at <= now
