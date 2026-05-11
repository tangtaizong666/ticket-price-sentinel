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

    async def open_relogin_window(self):
        return self.payload


def _read_session_state(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT session_status FROM session_state WHERE id = 1"
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
    assert _read_session_state(settings.app_db_path) == ("login_started",)


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
    assert _read_session_state(settings.app_db_path) == ("missing_session_url",)
