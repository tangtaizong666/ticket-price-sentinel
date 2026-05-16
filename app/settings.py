from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


load_dotenv(PROJECT_ROOT / ".env")


def _resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_db_path: Path = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("APP_DB_PATH", "data/app.db")
        )
    )
    playwright_profile_dir: Path = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("PLAYWRIGHT_PROFILE_DIR", "data/playwright-profile")
        )
    )
    ctrip_snapshot_dir: Path = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("CTRIP_SNAPSHOT_DIR", "data/debug")
        )
    )
    ctrip_debug_snapshot_dir: Path = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv("CTRIP_DEBUG_SNAPSHOT_DIR", "data/debug")
        )
    )
    ctrip_save_debug_snapshot: bool = field(
        default_factory=lambda: _env_flag("CTRIP_SAVE_DEBUG_SNAPSHOT", "0")
    )
    ctrip_search_url_template: str = os.getenv("CTRIP_SEARCH_URL_TEMPLATE", "")
    ctrip_session_url: str = os.getenv("CTRIP_SESSION_URL", "")
    app_base_url: str = field(
        default_factory=lambda: os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    )
    monitor_realert_cooldown_hours: int = field(
        default_factory=lambda: int(os.getenv("MONITOR_REALERT_COOLDOWN_HOURS", "6"))
    )
    monitor_realert_cooldown_enabled: bool = field(
        default_factory=lambda: _env_flag("MONITOR_REALERT_COOLDOWN_ENABLED", "1")
    )
    monitor_failure_backoff_minutes: int = field(
        default_factory=lambda: int(os.getenv("MONITOR_FAILURE_BACKOFF_MINUTES", "5"))
    )
    ctrip_auto_relogin_cooldown_minutes: int = field(
        default_factory=lambda: int(os.getenv("CTRIP_AUTO_RELOGIN_COOLDOWN_MINUTES", "30"))
    )
