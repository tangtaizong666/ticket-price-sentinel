import asyncio
from datetime import UTC, datetime
from typing import Protocol

from app.models import FlightResult, MonitorTask
from app.monitor_runner import evaluate_monitor_result, should_run_task
from app.monitoring import list_monitor_tasks, record_monitor_hit, update_monitor_runtime_state
from app.notifier import build_notification_message, send_desktop_notification
from app.settings import Settings


class MonitorScraper(Protocol):
    async def search(self, task: MonitorTask) -> list[FlightResult]: ...


class MonitorScheduler:
    def __init__(
        self, settings: Settings, scraper: MonitorScraper, poll_seconds: int = 30
    ) -> None:
        self.settings = settings
        self.scraper = scraper
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.tick_once()
            except Exception:
                pass
            await asyncio.sleep(self.poll_seconds)

    async def tick_once(self) -> None:
        now = datetime.now(UTC)
        for task in list_monitor_tasks(self.settings):
            if not should_run_task(task, now):
                continue

            try:
                flights = await self.scraper.search(task)
                evaluation = evaluate_monitor_result(task, flights)
                should_record_hit = (
                    evaluation.should_notify and evaluation.lowest_price is not None
                )

                if should_record_hit:
                    record_monitor_hit(
                        self.settings,
                        task.id,
                        evaluation.lowest_price,
                        evaluation.flights_snapshot,
                    )
                    title, message = build_notification_message(
                        task.origin_city,
                        task.destination_city,
                        evaluation.lowest_price,
                        task.target_price,
                    )
                    send_desktop_notification(title, message)

                update_monitor_runtime_state(
                    self.settings,
                    task.id,
                    last_checked_at=now,
                    next_check_at=evaluation.next_check_at,
                    last_seen_lowest_price=evaluation.lowest_price,
                    last_notified_at=now if should_record_hit else task.last_notified_at,
                    last_notified_price=(
                        evaluation.lowest_price
                        if should_record_hit
                        else task.last_notified_price
                    ),
                )
            except Exception:
                continue
