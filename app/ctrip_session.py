import asyncio

from playwright.async_api import BrowserContext, Playwright, async_playwright

from app.settings import Settings


class CtripSessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._context_lock = asyncio.Lock()

    async def open_relogin_window(self) -> dict[str, str]:
        if not self.settings.ctrip_session_url:
            return {"status": "missing_session_url", "url": ""}

        context = await self.get_context()
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.settings.ctrip_session_url, wait_until="domcontentloaded")
        return {"status": "login_started", "url": self.settings.ctrip_session_url}

    async def get_context(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        async with self._context_lock:
            if self._context is not None:
                return self._context

            self.settings.playwright_profile_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.playwright_profile_dir),
                headless=False,
            )
            return self._context
