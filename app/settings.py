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
            os.getenv("CTRIP_SNAPSHOT_DIR", "tests/fixtures")
        )
    )
    ctrip_search_url_template: str = os.getenv("CTRIP_SEARCH_URL_TEMPLATE", "")
    ctrip_session_url: str = os.getenv("CTRIP_SESSION_URL", "")
