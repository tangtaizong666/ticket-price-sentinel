from datetime import date, time
import asyncio
import unittest
from unittest.mock import patch

from app.ctrip_scraper import CtripScraper, ScrapeFailedError, _looks_like_session_expired
from app.ctrip_session import CtripSessionManager
from app.models import FlightResult, SearchRequest
from app.settings import Settings


class FakePage:
    def __init__(self, html: str = "<html></html>", goto_error: Exception | None = None):
        self.html = html
        self.goto_error = goto_error
        self.goto_calls: list[tuple[str, str, int]] = []
        self.wait_calls: list[tuple[str, int]] = []

    async def goto(self, url: str, wait_until: str, timeout: int | None = None) -> None:
        self.goto_calls.append((url, wait_until, timeout))
        if self.goto_error is not None:
            raise self.goto_error

    async def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.wait_calls.append((state, timeout))

    async def content(self) -> str:
        return self.html


class FakeContext:
    def __init__(self, page: FakePage):
        self.pages = [page]
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.pages[0]

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self, context):
        self.chromium = self
        self._context = context

    async def launch_persistent_context(self, user_data_dir: str, headless: bool):
        return self._context


class FakeAsyncPlaywrightContext:
    def __init__(self, playwright):
        self._playwright = playwright

    async def __aenter__(self):
        return self._playwright

    async def __aexit__(self, exc_type, exc, tb):
        return False


class CtripScraperTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_bounded_navigation_timeouts_and_wraps_navigation_timeout(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        page = FakePage(goto_error=TimeoutError("timed out"))
        context = FakeContext(page)
        playwright = FakePlaywright(context)
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=[]),
        ):
            with self.assertRaises(ScrapeFailedError) as exc_info:
                await scraper.search(request)

        self.assertIn("timed out", str(exc_info.exception))
        self.assertEqual(page.goto_calls[0][1], "domcontentloaded")
        self.assertIsInstance(page.goto_calls[0][2], int)
        self.assertGreater(page.goto_calls[0][2], 0)
        self.assertTrue(context.closed)

    async def test_search_serializes_access_to_shared_persistent_profile(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        flights = [
            FlightResult(
                flight_no="MU1234",
                airline="东航",
                origin_city="北京",
                destination_city="上海",
                departure_time=time(8, 0),
                arrival_time=time(10, 0),
                is_direct=True,
                stop_info="直飞",
                price=500,
                deeplink_url="https://example.com/flight",
                fallback_search_url="https://example.com/search",
            )
        ]
        active_launches = 0
        max_active_launches = 0
        release_first_launch = asyncio.Event()
        first_launch_started = asyncio.Event()

        class SerializingPlaywright(FakePlaywright):
            async def launch_persistent_context(self, user_data_dir: str, headless: bool):
                nonlocal active_launches, max_active_launches
                active_launches += 1
                max_active_launches = max(max_active_launches, active_launches)
                if not first_launch_started.is_set():
                    first_launch_started.set()
                    await release_first_launch.wait()
                active_launches -= 1
                return self._context

        playwright = SerializingPlaywright(FakeContext(FakePage()))
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            first_task = asyncio.create_task(scraper.search(request))
            await first_launch_started.wait()
            second_task = asyncio.create_task(scraper.search(request))
            await asyncio.sleep(0)
            release_first_launch.set()
            await asyncio.gather(first_task, second_task)

        self.assertEqual(max_active_launches, 1)




class FakeStartedPlaywright:
    def __init__(self, context):
        self.chromium = self
        self._context = context
        self.launch_calls: list[tuple[str, bool]] = []

    async def launch_persistent_context(self, user_data_dir: str, headless: bool):
        self.launch_calls.append((user_data_dir, headless))
        return self._context


class SessionManagerContextReuseTests(unittest.IsolatedAsyncioTestCase):
    async def test_relogin_reuses_existing_context_and_does_not_launch_again(self) -> None:
        settings = Settings(ctrip_session_url="https://example.com/session")
        shared_context = FakeContext(FakePage())
        started_playwright = FakeStartedPlaywright(shared_context)
        manager = CtripSessionManager(settings)
        manager._playwright = started_playwright
        manager._context = shared_context

        payload = await manager.open_relogin_window()

        self.assertEqual(payload, {"status": "login_started", "url": "https://example.com/session"})
        self.assertEqual(started_playwright.launch_calls, [])
        self.assertEqual(shared_context.pages[0].goto_calls[0][0], "https://example.com/session")

    async def test_relogin_after_search_reuses_shared_context_factory(self) -> None:
        settings = Settings(ctrip_session_url="https://example.com/session")
        shared_context = FakeContext(FakePage())
        started_playwright = FakeStartedPlaywright(shared_context)
        manager = CtripSessionManager(settings)

        with patch(
            "app.ctrip_session.async_playwright",
            return_value=type(
                "FakePlaywrightStarter",
                (),
                {"start": staticmethod(lambda: asyncio.sleep(0, result=started_playwright))},
            )(),
        ):
            first = await manager.open_relogin_window()
            second = await manager.open_relogin_window()

        self.assertEqual(first["status"], "login_started")
        self.assertEqual(second["status"], "login_started")
        self.assertEqual(len(started_playwright.launch_calls), 1)

    def test_session_expiry_detection_ignores_generic_login_text(self) -> None:
        html = "<html><body><div>login to view promotions and verify baggage rules</div></body></html>"

        assert _looks_like_session_expired(html) is False

    def test_session_expiry_detection_ignores_non_auth_identity_verification_snippet(self) -> None:
        html = (
            "<html><body><div>"
            "服务说明：旅客凭预订机票时的有效登机证件到乘车地点进行身份验证，"
            "经巴士柜台工作人员验证后乘车。"
            "</div></body></html>"
        )

        assert _looks_like_session_expired(html) is False

    def test_session_expiry_detection_matches_specific_ctrip_verification_signals(self) -> None:
        html = "<html><body><div>请完成验证后继续访问</div><div>验证码</div></body></html>"

        assert _looks_like_session_expired(html) is True
