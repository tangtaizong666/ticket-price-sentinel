from datetime import date, time
import asyncio
import unittest
from unittest.mock import patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.ctrip_scraper import (
    CtripScraper,
    ScrapeFailedError,
    SessionExpiredError,
    _SEARCH_READY_SCRIPT,
    _SEARCH_RESULT_SELECTORS,
    _looks_like_session_expired,
)
from app.ctrip_session import CtripSessionManager
from app.models import FlightResult, SearchRequest
from app.settings import Settings


class FakePage:
    def __init__(
        self,
        html: str = "<html></html>",
        goto_error: Exception | None = None,
        wait_error: Exception | None = None,
        wait_for_function_error: Exception | None = None,
    ):
        self.html = html
        self.goto_error = goto_error
        self.wait_error = wait_error
        self.wait_for_function_error = wait_for_function_error
        self.goto_calls: list[tuple[str, str, int]] = []
        self.wait_calls: list[tuple[str, int]] = []
        self.wait_for_function_calls: list[tuple[str, object, int | None]] = []
        self.closed = False

    async def goto(self, url: str, wait_until: str, timeout: int | None = None) -> None:
        self.goto_calls.append((url, wait_until, timeout))
        if self.goto_error is not None:
            raise self.goto_error

    async def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.wait_calls.append((state, timeout))
        if self.wait_error is not None:
            raise self.wait_error

    async def wait_for_function(
        self, expression: str, arg: object = None, timeout: int | None = None
    ) -> None:
        self.wait_for_function_calls.append((expression, arg, timeout))
        if self.wait_for_function_error is not None:
            raise self.wait_for_function_error

    async def content(self) -> str:
        return self.html

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, page: FakePage):
        self.pages = [page]
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.pages[0]

    async def close(self) -> None:
        self.closed = True


class NewPageContext:
    def __init__(self, existing_page: FakePage, new_page: FakePage):
        self.pages = [existing_page]
        self.new_pages = [new_page]
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.new_pages.pop(0)

    async def close(self) -> None:
        self.closed = True


class RecoveringSessionManager:
    def __init__(self, closed_context, replacement_context: NewPageContext):
        self._context = closed_context
        self.closed_context = closed_context
        self.replacement_context = replacement_context
        self.close_calls = 0

    async def get_context(self):
        return self._context

    async def close(self):
        self.close_calls += 1
        await self._context.close()
        self._context = self.replacement_context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = self
        self._context = context

    async def launch_persistent_context(self, user_data_dir: str, headless: bool):
        self.headless = headless
        return self._context


class FakeAsyncPlaywrightContext:
    def __init__(self, playwright):
        self._playwright = playwright

    async def __aenter__(self):
        return self._playwright

    async def __aexit__(self, exc_type, exc, tb):
        return False


class CtripScraperTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_waits_for_result_condition_instead_of_network_idle(self) -> None:
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
        page = FakePage()
        context = FakeContext(page)
        playwright = FakePlaywright(context)
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            result = await scraper.search(request)

        self.assertEqual(result, flights)
        self.assertEqual(page.goto_calls[0][1], "commit")
        self.assertEqual(page.wait_calls, [])
        self.assertEqual(len(page.wait_for_function_calls), 1)
        self.assertTrue(context.closed)

    async def test_search_wait_uses_specific_parseable_flight_result_selectors(self) -> None:
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
        page = FakePage()
        context = FakeContext(page)
        playwright = FakePlaywright(context)
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            await scraper.search(request)

        selectors = page.wait_for_function_calls[0][1][0]
        self.assertEqual(list(_SEARCH_RESULT_SELECTORS), selectors)
        self.assertNotIn("div[class*='flight']", selectors)
        self.assertNotIn("article", selectors)
        self.assertIn("flight-item", " ".join(selectors))
        self.assertIn("pricePattern", _SEARCH_READY_SCRIPT)
        self.assertIn("timePattern", _SEARCH_READY_SCRIPT)

    async def test_search_uses_bounded_navigation_timeouts_and_wraps_navigation_timeout(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        page = FakePage(goto_error=PlaywrightTimeoutError("timed out"))
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
        self.assertEqual(page.goto_calls[0][1], "commit")
        self.assertIsInstance(page.goto_calls[0][2], int)
        self.assertGreater(page.goto_calls[0][2], 0)
        self.assertTrue(playwright.headless)
        self.assertTrue(context.closed)

    async def test_search_returns_empty_list_when_ctrip_reports_no_flights(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        page = FakePage(html="<html><body><div>暂无符合条件的航班</div></body></html>")
        context = FakeContext(page)
        playwright = FakePlaywright(context)
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=[]),
        ):
            result = await scraper.search(request)

        self.assertEqual(result, [])
        self.assertEqual(page.wait_calls, [])
        self.assertEqual(len(page.wait_for_function_calls), 1)

    async def test_search_still_requires_relogin_when_condition_wait_reaches_auth_page(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        page = FakePage(html="<html><body><div>请完成验证后继续访问</div></body></html>")
        context = FakeContext(page)
        playwright = FakePlaywright(context)
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=[]),
        ):
            with self.assertRaises(SessionExpiredError):
                await scraper.search(request)

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

    async def test_search_does_not_save_live_snapshot_by_default(self) -> None:
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
        page = FakePage()
        playwright = FakePlaywright(FakeContext(page))
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot") as save_snapshot,
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            await scraper.search(request)

        save_snapshot.assert_not_called()

    async def test_search_saves_live_snapshot_when_debug_snapshot_is_enabled(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
            ctrip_save_debug_snapshot=True,
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
        page = FakePage()
        playwright = FakePlaywright(FakeContext(page))
        scraper = CtripScraper(settings)

        with (
            patch("app.ctrip_scraper.async_playwright", return_value=FakeAsyncPlaywrightContext(playwright)),
            patch("app.ctrip_scraper.save_live_snapshot") as save_snapshot,
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            await scraper.search(request)

        save_snapshot.assert_called_once()




class FakeStartedPlaywright:
    def __init__(self, context):
        self.chromium = self
        self._contexts = context if isinstance(context, list) else [context]
        self.launch_calls: list[tuple[str, bool]] = []
        self.stopped = False

    async def launch_persistent_context(self, user_data_dir: str, headless: bool):
        self.launch_calls.append((user_data_dir, headless))
        return self._contexts.pop(0)

    async def stop(self):
        self.stopped = True


class ClosedContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    async def new_page(self):
        raise RuntimeError("Target page, context or browser has been closed")

    async def close(self):
        self.closed = True


class SessionManagerContextReuseTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_context_search_uses_isolated_page_and_closes_it(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        existing_relogin_page = FakePage()
        search_page = FakePage()
        shared_context = NewPageContext(existing_relogin_page, search_page)
        manager = CtripSessionManager(settings)
        manager._context = shared_context
        scraper = CtripScraper(settings, session_manager=manager)
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

        with (
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            result = await scraper.search(request)

        self.assertEqual(result, flights)
        self.assertEqual(existing_relogin_page.goto_calls, [])
        self.assertEqual(len(search_page.goto_calls), 1)
        self.assertTrue(search_page.closed)

    async def test_shared_context_search_closes_isolated_page_when_navigation_fails(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        existing_relogin_page = FakePage()
        search_page = FakePage(
            wait_for_function_error=PlaywrightTimeoutError("search result condition timed out")
        )
        shared_context = NewPageContext(existing_relogin_page, search_page)
        manager = CtripSessionManager(settings)
        manager._context = shared_context
        scraper = CtripScraper(settings, session_manager=manager)

        with self.assertRaises(ScrapeFailedError) as exc_info:
            await scraper.search(request)

        self.assertIn("search result condition timed out", str(exc_info.exception))
        self.assertEqual(existing_relogin_page.goto_calls, [])
        self.assertEqual(len(search_page.goto_calls), 1)
        self.assertTrue(search_page.closed)

    async def test_shared_context_search_rebuilds_closed_context_and_retries_once(self) -> None:
        request = SearchRequest(
            origin_city="北京",
            destination_city="上海",
            departure_date=date(2026, 5, 20),
        )
        settings = Settings(
            ctrip_search_url_template="https://example.com/search?from={origin}&to={destination}&date={departure_date}",
        )
        closed_context = ClosedContext()
        existing_relogin_page = FakePage()
        search_page = FakePage()
        replacement_context = NewPageContext(existing_relogin_page, search_page)
        manager = RecoveringSessionManager(closed_context, replacement_context)
        scraper = CtripScraper(settings, session_manager=manager)
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

        with (
            patch("app.ctrip_scraper.save_live_snapshot"),
            patch("app.ctrip_scraper.parse_search_results", return_value=flights),
        ):
            result = await scraper.search(request)

        self.assertEqual(result, flights)
        self.assertEqual(manager.close_calls, 1)
        self.assertTrue(closed_context.closed)
        self.assertEqual(len(search_page.goto_calls), 1)
        self.assertTrue(search_page.closed)

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

    async def test_relogin_rebuilds_context_after_cached_context_is_closed(self) -> None:
        settings = Settings(ctrip_session_url="https://example.com/session")
        closed_context = ClosedContext()
        replacement_context = FakeContext(FakePage())
        old_playwright = FakeStartedPlaywright([])
        new_playwright = FakeStartedPlaywright(replacement_context)
        manager = CtripSessionManager(settings)
        manager._playwright = old_playwright
        manager._context = closed_context

        with patch(
            "app.ctrip_session.async_playwright",
            return_value=type(
                "FakePlaywrightStarter",
                (),
                {"start": staticmethod(lambda: asyncio.sleep(0, result=new_playwright))},
            )(),
        ):
            payload = await manager.open_relogin_window()

        self.assertEqual(payload, {"status": "login_started", "url": "https://example.com/session"})
        self.assertTrue(closed_context.closed)
        self.assertTrue(old_playwright.stopped)
        self.assertEqual(len(new_playwright.launch_calls), 1)
        self.assertEqual(replacement_context.pages[0].goto_calls[0][0], "https://example.com/session")

    async def test_close_releases_persistent_context_and_playwright(self) -> None:
        settings = Settings(ctrip_session_url="https://example.com/session")
        shared_context = FakeContext(FakePage())
        started_playwright = FakeStartedPlaywright(shared_context)
        manager = CtripSessionManager(settings)
        manager._playwright = started_playwright
        manager._context = shared_context

        await manager.close()
        await manager.close()

        self.assertTrue(shared_context.closed)
        self.assertTrue(started_playwright.stopped)
        self.assertIsNone(manager._context)
        self.assertIsNone(manager._playwright)

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
