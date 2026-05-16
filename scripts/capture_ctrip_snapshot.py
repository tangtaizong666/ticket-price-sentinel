import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.ctrip_urls import build_search_url
from app.settings import Settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT_OUTPUT = Path("data/debug/ctrip_search_results.html")
FIXTURE_DIR = Path("tests/fixtures")


def _normalize_under_project(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (project_root / path).resolve()


def resolve_snapshot_output(
    *,
    project_root: Path,
    explicit_output: Path | None,
    allow_fixture_overwrite: bool,
) -> Path:
    output_path = _normalize_under_project(
        project_root,
        explicit_output or DEFAULT_SNAPSHOT_OUTPUT,
    )
    fixture_dir = (project_root / FIXTURE_DIR).resolve()
    if not allow_fixture_overwrite:
        try:
            output_path.relative_to(fixture_dir)
        except ValueError:
            pass
        else:
            raise ValueError(
                "Refusing to write a live snapshot under tests/fixtures without "
                "--allow-fixture-overwrite. Save to data/debug first, sanitize it, "
                "then overwrite the fixture explicitly."
            )
    return output_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a Ctrip search page snapshot for parser development."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Snapshot output path. Defaults to data/debug/ctrip_search_results.html.",
    )
    parser.add_argument(
        "--allow-fixture-overwrite",
        action="store_true",
        help="Allow writing directly under tests/fixtures after manual sanitization.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
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

    requested_output = args.output
    if requested_output is None:
        requested_output = settings.ctrip_snapshot_dir / "ctrip_search_results.html"

    output_path = resolve_snapshot_output(
        project_root=PROJECT_ROOT,
        explicit_output=requested_output,
        allow_fixture_overwrite=args.allow_fixture_overwrite,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
            print(f"Saved snapshot to {output_path}")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
