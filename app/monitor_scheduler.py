import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Protocol

from app.ctrip_scraper import SessionExpiredError
from app.history import save_session_state
from app.models import FlightResult, MonitorTask
from app.monitor_runner import evaluate_monitor_result, should_run_task
from app.monitoring import (
    claim_monitor_task_check,
    list_monitor_tasks,
    record_monitor_check,
    record_monitor_hit,
    update_monitor_runtime_state,
)
from app.notifier import send_monitor_hit_alert
from app.settings import Settings


logger = logging.getLogger(__name__)


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
        self._last_auto_relogin_attempt_at: datetime | None = None

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
                logger.exception("Monitor scheduler tick failed")
            await asyncio.sleep(self.poll_seconds)

    async def tick_once(self) -> None:
        now = datetime.now(UTC)
        for task in list_monitor_tasks(self.settings):
            if not should_run_task(task, now):
                continue
            claimed_until = now + _monitor_claim_lease(self.settings)
            if not claim_monitor_task_check(
                self.settings,
                task.id,
                expected_next_check_at=task.next_check_at,
                claimed_until=claimed_until,
            ):
                continue

            try:
                flights = await self.scraper.search(task)
                evaluation = evaluate_monitor_result(
                    task,
                    flights,
                    now=now,
                    cooldown_hours=self.settings.monitor_realert_cooldown_hours,
                    cooldown_enabled=self.settings.monitor_realert_cooldown_enabled,
                )
                should_record_hit = (
                    evaluation.should_notify and evaluation.lowest_price is not None
                )
                is_target_hit = (
                    evaluation.lowest_price is not None
                    and evaluation.lowest_price <= task.target_price
                )

                if should_record_hit:
                    hit = record_monitor_hit(
                        self.settings,
                        task.id,
                        evaluation.lowest_price,
                        evaluation.flights_snapshot,
                    )
                    notification_sent = (
                        send_monitor_hit_alert(
                            base_url=self.settings.app_base_url,
                            monitor_task_id=task.id,
                            monitor_hit_id=hit.id,
                            origin_city=task.origin_city,
                            destination_city=task.destination_city,
                            departure_date=task.departure_date,
                            current_price=evaluation.lowest_price,
                            target_price=task.target_price,
                            alert_sound_enabled=task.alert_sound_enabled,
                            alert_popup_enabled=task.alert_popup_enabled,
                        )
                        is not False
                    )
                else:
                    notification_sent = False

                record_monitor_check(
                    self.settings,
                    task.id,
                    checked_at=now,
                    status="success",
                    lowest_price=evaluation.lowest_price,
                    is_target_hit=is_target_hit,
                    notification_sent=notification_sent,
                    error_message=None,
                    flights_snapshot=evaluation.flights_snapshot,
                )
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
            except Exception as exc:
                now_after_failure = datetime.now(UTC)
                status = "session_expired" if isinstance(exc, SessionExpiredError) else "error"
                record_monitor_check(
                    self.settings,
                    task.id,
                    checked_at=now_after_failure,
                    status=status,
                    lowest_price=None,
                    is_target_hit=False,
                    notification_sent=False,
                    error_message=_public_monitor_error_message(exc),
                    flights_snapshot=[],
                )
                if isinstance(exc, SessionExpiredError):
                    save_session_state(self.settings, "expired")
                    await self._maybe_open_relogin_window()
                logger.exception("Monitor task %s failed", task.id)
                update_monitor_runtime_state(
                    self.settings,
                    task.id,
                    last_checked_at=now_after_failure,
                    next_check_at=now_after_failure
                    + _failure_retry_delay(task, self.settings),
                    last_seen_lowest_price=task.last_seen_lowest_price,
                    last_notified_at=task.last_notified_at,
                    last_notified_price=task.last_notified_price,
                )
                continue

    async def _maybe_open_relogin_window(self) -> None:
        now = datetime.now(UTC)
        cooldown = timedelta(minutes=self.settings.ctrip_auto_relogin_cooldown_minutes)
        if (
            self._last_auto_relogin_attempt_at is not None
            and now - self._last_auto_relogin_attempt_at < cooldown
        ):
            return

        session_manager = getattr(self.scraper, "session_manager", None)
        open_relogin_window = getattr(session_manager, "open_relogin_window", None)
        if open_relogin_window is None:
            return

        self._last_auto_relogin_attempt_at = now
        try:
            await open_relogin_window()
        except Exception:
            logger.exception("Automatic Ctrip relogin window failed")


def _public_monitor_error_message(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if (
        "BrowserType.launch" in message
        and "Executable doesn't exist" in message
        and "ms-playwright" in message
    ):
        return "浏览器运行环境缺失，请在项目目录运行 python -m playwright install chromium 后重试。"
    if "context or browser has been closed" in lowered or "target page" in lowered:
        return "携程浏览器窗口已关闭，系统会自动重建登录浏览器后重试。"
    if "ctrip search navigation timed out" in lowered or (
        "timeout" in lowered and "exceeded" in lowered
    ):
        return "携程页面加载超时，系统会稍后自动重试。"
    if "unable to parse any flights from ctrip search results" in lowered:
        return "携程页面已打开，但暂时没有读取到航班结果，系统会稍后自动重试。"
    return message


def _failure_retry_delay(task: MonitorTask, settings: Settings) -> timedelta:
    retry_minutes = max(
        task.check_interval_minutes,
        settings.monitor_failure_backoff_minutes,
    )
    return timedelta(minutes=retry_minutes)


def _monitor_claim_lease(settings: Settings) -> timedelta:
    return timedelta(minutes=max(2, settings.monitor_failure_backoff_minutes))
