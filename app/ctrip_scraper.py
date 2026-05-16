import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from app.ctrip_capture import save_live_snapshot
from app.ctrip_parser import parse_search_results
from app.ctrip_session import CtripSessionManager, _is_closed_context_error
from app.ctrip_urls import build_search_url
from app.models import FlightResult, SearchRequest
from app.settings import Settings


class SessionExpiredError(Exception):
    pass


class ScrapeFailedError(Exception):
    pass


_FRESH_CONTEXT_LOCK = asyncio.Lock()
_NAVIGATION_TIMEOUT_MS = 20_000
_SEARCH_RESULT_TIMEOUT_MS = 30_000
_SEARCH_RESULT_SELECTORS = (
    "div.flight-item.domestic",
    "div[class*='flight-item']",
    "[data-testid*='flight']",
)
_EMPTY_RESULT_MARKERS = (
    "暂无符合条件的航班",
    "暂无符合要求的航班",
    "暂无航班",
    "未找到符合条件",
    "没有找到符合条件",
    "无符合条件航班",
    "无可售航班",
    "没有航班",
)
_SESSION_EXPIRED_MARKERS = (
    "扫码登录",
    "请完成验证",
    "安全验证",
    "验证码",
    "拖动滑块",
    "验证后继续访问",
    "login.ctrip.com",
    "passport.ctrip.com",
)
_SEARCH_READY_SCRIPT = """
([flightSelectors, emptyMarkers, sessionMarkers]) => {
    const bodyText = document.body ? document.body.innerText : "";
    const lowerBodyText = bodyText.toLowerCase();
    const currentUrl = window.location.href.toLowerCase();
    const pricePattern = /[¥￥]\\s*\\d+/;
    const timePattern = /\\b\\d{2}:\\d{2}\\b/g;
    const hasParseableFlightCard = (node) => {
        const text = node && node.innerText ? node.innerText : "";
        return pricePattern.test(text) && (text.match(timePattern) || []).length >= 2;
    };

    if (
        flightSelectors.some((selector) => {
            return Array.from(document.querySelectorAll(selector)).some(hasParseableFlightCard);
        })
    ) {
        return "flights";
    }
    if (emptyMarkers.some((marker) => lowerBodyText.includes(marker.toLowerCase()))) {
        return "empty";
    }
    if (
        sessionMarkers.some((marker) => {
            const loweredMarker = marker.toLowerCase();
            return lowerBodyText.includes(loweredMarker) || currentUrl.includes(loweredMarker);
        })
    ) {
        return "session";
    }
    return false;
}
"""


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

        html = await self._capture_search_html(search_url)

        if self.settings.ctrip_save_debug_snapshot:
            save_live_snapshot(settings=self.settings, request=request, html=html)

        if _looks_like_session_expired(html):
            raise SessionExpiredError(
                "Ctrip session expired or requires verification; relogin required"
            )

        flights = parse_search_results(html, request, search_url)
        if not flights:
            if _looks_like_empty_result(html):
                return []
            raise ScrapeFailedError("Unable to parse any flights from Ctrip search results")
        return flights

    async def _capture_search_html(self, search_url: str) -> str:
        if getattr(self.session_manager, "_context", None) is not None:
            try:
                return await self._capture_with_shared_context(search_url)
            except Exception as exc:
                if not _is_closed_context_error(exc):
                    raise
                await self.session_manager.close()
                return await self._capture_with_shared_context(search_url)

        return await self._capture_with_fresh_context(search_url)

    async def _capture_with_shared_context(self, search_url: str) -> str:
        context = await self.session_manager.get_context()
        page = await context.new_page()
        try:
            return await self._navigate_and_capture(page, search_url)
        finally:
            await page.close()

    async def _capture_with_fresh_context(self, search_url: str) -> str:
        self.settings.playwright_profile_dir.mkdir(parents=True, exist_ok=True)

        async with _FRESH_CONTEXT_LOCK:
            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.settings.playwright_profile_dir),
                    headless=True,
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    return await self._navigate_and_capture(page, search_url)
                finally:
                    await context.close()

    async def _navigate_and_capture(self, page, search_url: str) -> str:
        try:
            await page.goto(
                search_url,
                wait_until="commit",
                timeout=_NAVIGATION_TIMEOUT_MS,
            )
            await page.wait_for_function(
                _SEARCH_READY_SCRIPT,
                arg=[
                    list(_SEARCH_RESULT_SELECTORS),
                    list(_EMPTY_RESULT_MARKERS),
                    list(_SESSION_EXPIRED_MARKERS),
                ],
                timeout=_SEARCH_RESULT_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            raise ScrapeFailedError(f"Ctrip search navigation timed out: {exc}") from exc
        return await page.content()


def _looks_like_session_expired(html: str) -> bool:
    return _contains_marker(html, _SESSION_EXPIRED_MARKERS)


def _looks_like_empty_result(html: str) -> bool:
    return _contains_marker(html, _EMPTY_RESULT_MARKERS)


def _contains_marker(html: str, markers: tuple[str, ...]) -> bool:
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in markers)
