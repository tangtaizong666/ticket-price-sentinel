import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from app.ctrip_capture import save_live_snapshot
from app.ctrip_parser import parse_search_results
from app.ctrip_session import CtripSessionManager
from app.ctrip_urls import build_search_url
from app.models import FlightResult, SearchRequest
from app.settings import Settings


class SessionExpiredError(Exception):
    pass


class ScrapeFailedError(Exception):
    pass


_FRESH_CONTEXT_LOCK = asyncio.Lock()
_NAVIGATION_TIMEOUT_MS = 20_000
_NETWORK_IDLE_TIMEOUT_MS = 10_000


class CtripScraper:
    def __init__(
        self, settings: Settings, session_manager: CtripSessionManager | None = None
    ):
        self.settings = settings
        self.session_manager = session_manager or CtripSessionManager(settings)

    async def search(self, request: SearchRequest) -> list[FlightResult]:
        if not self.settings.ctrip_search_url_template:
            raise ScrapeFailedError("CTRIP_SEARCH_URL_TEMPLATE is not configured")

        search_url = build_search_url(
            template=self.settings.ctrip_search_url_template,
            origin=request.origin_city,
            destination=request.destination_city,
            departure_date=request.departure_date.isoformat(),
        )

        if self.session_manager._context is not None:
            html = await self._capture_with_shared_context(search_url)
        else:
            html = await self._capture_with_fresh_context(search_url)

        save_live_snapshot(settings=self.settings, request=request, html=html)

        if _looks_like_session_expired(html):
            raise SessionExpiredError(
                "Ctrip session expired or requires verification; relogin required"
            )

        flights = parse_search_results(html, request, search_url)
        if not flights:
            raise ScrapeFailedError("Unable to parse any flights from Ctrip search results")
        return flights

    async def _capture_with_shared_context(self, search_url: str) -> str:
        context = await self.session_manager.get_context()
        page = await context.new_page()
        try:
            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=_NAVIGATION_TIMEOUT_MS,
                )
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=_NETWORK_IDLE_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError as exc:
                raise ScrapeFailedError(f"Ctrip search navigation timed out: {exc}") from exc
            return await page.content()
        finally:
            await page.close()

    async def _capture_with_fresh_context(self, search_url: str) -> str:
        self.settings.playwright_profile_dir.mkdir(parents=True, exist_ok=True)

        async with _FRESH_CONTEXT_LOCK:
            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.settings.playwright_profile_dir),
                    headless=False,
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    try:
                        await page.goto(
                            search_url,
                            wait_until="domcontentloaded",
                            timeout=_NAVIGATION_TIMEOUT_MS,
                        )
                        await page.wait_for_load_state(
                            "networkidle",
                            timeout=_NETWORK_IDLE_TIMEOUT_MS,
                        )
                    except PlaywrightTimeoutError as exc:
                        raise ScrapeFailedError(
                            f"Ctrip search navigation timed out: {exc}"
                        ) from exc
                    return await page.content()
                finally:
                    await context.close()


def _looks_like_session_expired(html: str) -> bool:
    lowered = html.lower()
    markers = (
        "扫码登录",
        "请完成验证",
        "安全验证",
        "验证码",
        "拖动滑块",
        "验证后继续访问",
        "login.ctrip.com",
        "passport.ctrip.com",
    )
    return any(marker in lowered for marker in markers)
