from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import logging
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.ctrip_scraper import CtripScraper, ScrapeFailedError, SessionExpiredError
from app.ctrip_session import CtripSessionManager
from app.dashboard import load_home_dashboard
from app.db import init_db
from app.history import (
    delete_history,
    get_history,
    list_history,
    save_session_state,
    update_history,
)
from app.models import MonitorTaskCreate, MonitorTaskUpdate, SearchRequest, SearchResponse
from app.monitor_scheduler import MonitorScheduler
from app.monitoring import (
    clear_monitor_checks,
    create_monitor_task,
    delete_monitor_hit,
    get_monitor_task,
    list_monitor_alerts_after,
    list_monitor_checks,
    list_monitor_hits,
    list_monitor_tasks,
    update_monitor_task,
)
from app.notifier import build_monitor_target_url, build_notification_message
from app.search_service import run_search
from app.settings import Settings


BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
RELOGIN_FAILED_MESSAGE = (
    "无法打开携程登录窗口，请先关闭其它正在运行的飞票监控或携程登录窗口，然后重试"
)
UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await app.state.monitor_scheduler.start()
    try:
        yield
    finally:
        await app.state.monitor_scheduler.stop()
        close = getattr(app.state.session_manager, "close", None)
        if close is not None:
            await close()


def _error_response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "message": message},
    )


def _user_message_for_error(error: str, fallback: str) -> str:
    messages = {
        "relogin_required": "携程登录已失效，请重新登录后再继续",
        "scrape_failed": "这次没有成功读取携程结果，请重试一次",
    }
    return messages.get(error, fallback)


def _login_card_payload(settings: Settings) -> dict[str, str]:
    card = load_home_dashboard(settings).login_card
    return {
        "status": card.status,
        "detail": card.detail,
        "action_label": card.action_label,
        "action_kind": card.action_kind,
    }


def _serialize_datetime_for_api(raw_value: object) -> str:
    value = datetime.fromisoformat(str(raw_value))
    return value.isoformat().replace("+00:00", "Z")


def _monitor_alert_payload(settings: Settings, row: dict[str, object]) -> dict[str, object]:
    title, message = build_notification_message(
        str(row["origin_city"]),
        str(row["destination_city"]),
        int(row["lowest_price"]),
        int(row["target_price"]),
        departure_date=str(row["departure_date"]),
    )
    return {
        "hit_id": int(row["hit_id"]),
        "monitor_task_id": int(row["monitor_task_id"]),
        "origin_city": row["origin_city"],
        "destination_city": row["destination_city"],
        "departure_date": row["departure_date"],
        "lowest_price": row["lowest_price"],
        "target_price": row["target_price"],
        "hit_at": _serialize_datetime_for_api(row["hit_at"]),
        "title": title,
        "message": message,
        "url": build_monitor_target_url(
            settings.app_base_url,
            int(row["monitor_task_id"]),
            int(row["hit_id"]),
        ),
        "alert_sound_enabled": bool(row["alert_sound_enabled"]),
        "alert_taskbar_enabled": bool(row["alert_taskbar_enabled"]),
        "alert_popup_enabled": bool(row["alert_popup_enabled"]),
    }


async def _maybe_open_relogin_window(app: FastAPI) -> None:
    now = datetime.now(UTC)
    last_attempt_at = getattr(app.state, "last_auto_relogin_attempt_at", None)
    cooldown = timedelta(minutes=app.state.settings.ctrip_auto_relogin_cooldown_minutes)
    if last_attempt_at is not None and now - last_attempt_at < cooldown:
        return

    app.state.last_auto_relogin_attempt_at = now
    try:
        await app.state.session_manager.open_relogin_window()
    except Exception:
        logger.exception("Automatic Ctrip relogin window failed")


def create_app(
    settings: Settings | None = None, scraper=None, session_manager=None
) -> FastAPI:
    app = FastAPI(lifespan=_lifespan)
    app.state.settings = settings or Settings()
    app.state.local_request_token = secrets.token_urlsafe(32)
    app.state.last_auto_relogin_attempt_at = None
    app.state.session_manager = session_manager or CtripSessionManager(app.state.settings)
    app.state.scraper = scraper or CtripScraper(
        app.state.settings,
        session_manager=app.state.session_manager,
    )
    app.state.monitor_scheduler = MonitorScheduler(
        app.state.settings,
        app.state.scraper,
    )
    init_db(app.state.settings)
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.middleware("http")
    async def require_local_request_token(request: Request, call_next):
        if request.method.upper() in UNSAFE_HTTP_METHODS:
            token = request.headers.get("X-FlyTicket-Token")
            if token != app.state.local_request_token:
                return _error_response(
                    403,
                    "forbidden",
                    "本地请求校验失败，请刷新页面后重试",
                )
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "history": list_history(app.state.settings),
                "monitors": list_monitor_tasks(app.state.settings),
                "dashboard": load_home_dashboard(app.state.settings),
                "local_request_token": app.state.local_request_token,
            },
        )

    @app.get("/api/history")
    async def get_history_list():
        return list_history(app.state.settings)

    @app.get("/api/history/{history_id}")
    async def get_history_detail(history_id: int):
        history_record = get_history(app.state.settings, history_id)
        if history_record is None:
            raise HTTPException(status_code=404, detail="History record not found")
        return history_record

    @app.put("/api/history/{history_id}")
    async def update_history_detail(history_id: int, request: SearchRequest):
        history_record = get_history(app.state.settings, history_id)
        if history_record is None:
            raise HTTPException(status_code=404, detail="History record not found")
        return update_history(app.state.settings, history_id, request)

    @app.delete("/api/history/{history_id}")
    async def delete_history_detail(history_id: int):
        deleted = delete_history(app.state.settings, history_id)
        if deleted == 0:
            raise HTTPException(status_code=404, detail="History record not found")
        return {"deleted": deleted}

    @app.get("/api/monitors")
    async def get_monitor_list():
        return list_monitor_tasks(app.state.settings)

    @app.get("/api/monitor-alerts")
    async def get_monitor_alerts(after_id: int = 0):
        rows = list_monitor_alerts_after(app.state.settings, max(after_id, 0))
        return {
            "alerts": [
                _monitor_alert_payload(app.state.settings, row)
                for row in rows
            ]
        }

    @app.post("/api/monitors")
    async def create_monitor(payload: MonitorTaskCreate):
        return create_monitor_task(app.state.settings, payload)

    @app.get("/api/monitors/{monitor_id}")
    async def get_monitor_detail(monitor_id: int):
        monitor_task = get_monitor_task(app.state.settings, monitor_id)
        if monitor_task is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return monitor_task

    @app.put("/api/monitors/{monitor_id}")
    async def update_monitor_detail(monitor_id: int, payload: MonitorTaskUpdate):
        existing_monitor = get_monitor_task(app.state.settings, monitor_id)
        if existing_monitor is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return update_monitor_task(app.state.settings, monitor_id, payload, existing_monitor=existing_monitor)

    @app.get("/api/monitors/{monitor_id}/hits")
    async def get_monitor_hit_list(monitor_id: int):
        monitor_task = get_monitor_task(app.state.settings, monitor_id)
        if monitor_task is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return list_monitor_hits(app.state.settings, monitor_id)

    @app.delete("/api/monitors/{monitor_id}/hits/{monitor_hit_id}")
    async def delete_monitor_hit_detail(monitor_id: int, monitor_hit_id: int):
        monitor_task = get_monitor_task(app.state.settings, monitor_id)
        if monitor_task is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        deleted = delete_monitor_hit(app.state.settings, monitor_id, monitor_hit_id)
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Monitor hit not found")
        return {"deleted": deleted}

    @app.get("/api/monitors/{monitor_id}/checks")
    async def get_monitor_check_list(monitor_id: int):
        monitor_task = get_monitor_task(app.state.settings, monitor_id)
        if monitor_task is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        return list_monitor_checks(app.state.settings, monitor_id)

    @app.delete("/api/monitors/{monitor_id}/checks")
    async def clear_monitor_check_list(monitor_id: int):
        monitor_task = get_monitor_task(app.state.settings, monitor_id)
        if monitor_task is None:
            raise HTTPException(status_code=404, detail="Monitor task not found")
        deleted = clear_monitor_checks(app.state.settings, monitor_id)
        return {"deleted": deleted}

    @app.post("/api/history/{history_id}/rerun", response_model=SearchResponse)
    async def rerun_history_search(history_id: int):
        history_record = get_history(app.state.settings, history_id)
        if history_record is None:
            raise HTTPException(status_code=404, detail="History record not found")

        request = SearchRequest(
            origin_city=history_record.origin_city,
            destination_city=history_record.destination_city,
            departure_date=history_record.departure_date,
            max_price=history_record.max_price,
            departure_time_filters=history_record.departure_time_filters,
            flight_attribute_filters=history_record.flight_attribute_filters,
            airline_filters=history_record.airline_filters,
        )
        try:
            response = await run_search(app.state.settings, app.state.scraper, request)
            save_session_state(
                app.state.settings,
                "ready",
                datetime.now(UTC),
            )
            return response
        except SessionExpiredError:
            save_session_state(app.state.settings, "expired")
            await _maybe_open_relogin_window(app)
            return _error_response(
                503,
                "relogin_required",
                _user_message_for_error("relogin_required", "携程登录已失效，请重新登录后再继续"),
            )

    @app.post("/api/session/relogin")
    async def relogin():
        try:
            payload = await app.state.session_manager.open_relogin_window()
            save_session_state(app.state.settings, payload.get("status", "unknown"))
            return payload
        except Exception:
            save_session_state(app.state.settings, "relogin_failed")
            return _error_response(503, "relogin_failed", RELOGIN_FAILED_MESSAGE)

    @app.post("/api/session/confirm")
    async def confirm_login():
        close_login_window = getattr(app.state.session_manager, "close_login_window", None)
        if close_login_window is not None:
            await close_login_window()
        save_session_state(
            app.state.settings,
            "ready",
            datetime.now(UTC),
        )
        return {
            "status": "ready",
            "message": "已确认携程登录状态",
            "login_card": _login_card_payload(app.state.settings),
        }

    @app.post("/api/search", response_model=SearchResponse)
    async def search(request: SearchRequest):
        try:
            response = await run_search(app.state.settings, app.state.scraper, request)
            save_session_state(
                app.state.settings,
                "ready",
                datetime.now(UTC),
            )
            return response
        except SessionExpiredError:
            save_session_state(app.state.settings, "expired")
            await _maybe_open_relogin_window(app)
            return _error_response(
                503,
                "relogin_required",
                _user_message_for_error("relogin_required", "携程登录已失效，请重新登录后再继续"),
            )
        except ScrapeFailedError:
            return _error_response(
                502,
                "scrape_failed",
                _user_message_for_error("scrape_failed", "这次没有成功读取携程结果，请重试一次"),
            )

    return app


app = create_app()
