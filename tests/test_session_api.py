import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_settings_resolve_relative_runtime_paths_from_project_root() -> None:
    settings = Settings()

    assert settings.app_db_path == PROJECT_ROOT / "data/app.db"
    assert settings.playwright_profile_dir == PROJECT_ROOT / "data/playwright-profile"
    assert settings.ctrip_snapshot_dir == PROJECT_ROOT / "tests/fixtures"


def test_create_app_shares_one_session_manager_between_relogin_and_scraper(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")

    app = create_app(settings=settings)

    assert app.state.scraper.session_manager is app.state.session_manager


class StubSessionManager:
    def __init__(self, payload: dict[str, str]):
        self.payload = payload
        self.closed = False

    async def open_relogin_window(self):
        return self.payload

    async def close(self):
        self.closed = True


class BrokenSessionManager:
    async def open_relogin_window(self):
        raise RuntimeError("Browser profile is already in use")

    async def close(self):
        pass


def _read_session_state(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT session_status, last_successful_scrape_at FROM session_state WHERE id = 1"
        ).fetchone()


def test_relogin_endpoint_returns_and_persists_login_started(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(
        create_app(
            settings=settings,
            session_manager=StubSessionManager(
                {
                    "status": "login_started",
                    "url": "https://example.invalid/session",
                }
            ),
        )
    )

    response = client.post("/api/session/relogin")

    assert response.status_code == 200
    assert response.json() == {
        "status": "login_started",
        "url": "https://example.invalid/session",
    }
    row = _read_session_state(settings.app_db_path)
    assert row[0] == "login_started"
    assert row[1] is None


def test_relogin_endpoint_returns_and_persists_missing_session_url(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(
        create_app(
            settings=settings,
            session_manager=StubSessionManager(
                {"status": "missing_session_url", "url": ""}
            ),
        )
    )

    response = client.post("/api/session/relogin")

    assert response.status_code == 200
    assert response.json() == {"status": "missing_session_url", "url": ""}
    row = _read_session_state(settings.app_db_path)
    assert row[0] == "missing_session_url"
    assert row[1] is None


def test_relogin_endpoint_returns_chinese_json_when_browser_profile_is_busy(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    client = TestClient(
        create_app(
            settings=settings,
            session_manager=BrokenSessionManager(),
        )
    )

    response = client.post("/api/session/relogin")

    assert response.status_code == 503
    assert response.json() == {
        "error": "relogin_failed",
        "message": "无法打开携程登录窗口，请先关闭其它正在运行的飞票监控或携程登录窗口，然后重试",
    }
    row = _read_session_state(settings.app_db_path)
    assert row[0] == "relogin_failed"
    assert row[1] is None


def test_app_lifecycle_closes_session_manager(tmp_path) -> None:
    settings = Settings(app_db_path=tmp_path / "app.db")
    session_manager = StubSessionManager({"status": "login_started", "url": "https://example.invalid/session"})
    app = create_app(settings=settings, session_manager=session_manager)

    with TestClient(app):
        assert session_manager.closed is False

    assert session_manager.closed is True
