from pathlib import Path

from playwright.sync_api import sync_playwright

from app.ctrip_urls import build_search_url
from app.settings import Settings


def main() -> int:
    settings = Settings()
    template = settings.ctrip_search_url_template
    if not template:
        raise RuntimeError("CTRIP_SEARCH_URL_TEMPLATE is required")

    url = build_search_url(
        template=template,
        origin="北京",
        destination="上海",
        departure_date="2026-05-20",
    )

    snapshot_dir = settings.ctrip_snapshot_dir
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    output_path = snapshot_dir / "ctrip_search_results.html"

    with sync_playwright() as playwright:
        settings.playwright_profile_dir.mkdir(parents=True, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.playwright_profile_dir),
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            input("Press Enter after the page is ready to save the snapshot...")
            output_path.write_text(page.content(), encoding="utf-8")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
