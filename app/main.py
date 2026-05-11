from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.ctrip_scraper import CtripScraper, ScrapeFailedError, SessionExpiredError
from app.ctrip_session import CtripSessionManager
from app.dashboard import load_home_dashboard
from app.db import init_db
from app.history import get_history, list_history, save_session_state, update_history
from app.models import MonitorTaskCreate, MonitorTaskUpdate, SearchRequest, SearchResponse
from app.monitor_scheduler import MonitorScheduler
from app.monitoring import (
    create_monitor_task,
    get_monitor_task,
    list_monitor_hits,
    list_monitor_tasks,
    update_monitor_task,
)
from app.search_service import run_search
from app.settings import Settings


BASE_DIR = Path(__file__).resolve().parent


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


def create_app(
    settings: Settings | None = None, scraper=None, session_manager=None
) -> FastAPI:
    app = FastAPI(lifespan=_lifespan)
    app.state.settings = settings or Settings()
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

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "history": list_history(app.state.settings),
                "monitors": list_monitor_tasks(app.state.settings),
                "dashboard": load_home_dashboard(app.state.settings),
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

    @app.get("/api/monitors")
    async def get_monitor_list():
        return list_monitor_tasks(app.state.settings)

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
        response = await run_search(app.state.settings, app.state.scraper, request)
        save_session_state(
            app.state.settings,
            "ready",
            datetime.now(UTC),
        )
        return response

    @app.post("/api/session/relogin")
    async def relogin():
        payload = await app.state.session_manager.open_relogin_window()
        save_session_state(app.state.settings, payload.get("status", "unknown"))
        return payload

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
        except SessionExpiredError as exc:
            save_session_state(app.state.settings, "expired")
            return _error_response(503, "relogin_required", str(exc))
        except ScrapeFailedError as exc:
            return _error_response(502, "scrape_failed", str(exc))

    return app


app = create_app()
