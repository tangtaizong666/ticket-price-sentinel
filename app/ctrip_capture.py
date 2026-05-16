from pathlib import Path

from app.models import SearchRequest
from app.settings import Settings


def save_live_snapshot(
    settings: Settings,
    request: SearchRequest,
    html: str,
    filename: str = "last_live_search.html",
) -> Path:
    settings.ctrip_debug_snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = settings.ctrip_debug_snapshot_dir / filename
    path.write_text(html, encoding="utf-8")
    return path
