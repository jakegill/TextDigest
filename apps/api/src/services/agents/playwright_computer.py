"""PlaywrightComputer — Computer-use environment backed by a real Chromium.

Async variant. Same action surface as the reference impl at
https://github.com/google-gemini/computer-use-preview/blob/main/computers/playwright/playwright.py
but uses Playwright's async API so it composes with FastAPI's asyncio loop
(the sync API explicitly rejects being called from inside a running loop).
"""

from __future__ import annotations

import abc
import asyncio
import logging
import os
import sys
from typing import Literal

import playwright.async_api
import pydantic
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logger = logging.getLogger("uvicorn.error")


class EnvState(pydantic.BaseModel):
    screenshot: bytes
    url: str


class Computer(abc.ABC):
    @abc.abstractmethod
    def screen_size(self) -> tuple[int, int]: ...
    @abc.abstractmethod
    async def open_web_browser(self) -> EnvState: ...
    @abc.abstractmethod
    async def click_at(self, x: int, y: int) -> EnvState: ...
    @abc.abstractmethod
    async def hover_at(self, x: int, y: int) -> EnvState: ...
    @abc.abstractmethod
    async def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        press_enter: bool,
        clear_before_typing: bool,
    ) -> EnvState: ...
    @abc.abstractmethod
    async def scroll_document(
        self, direction: Literal["up", "down", "left", "right"]
    ) -> EnvState: ...
    @abc.abstractmethod
    async def scroll_at(
        self,
        x: int,
        y: int,
        direction: Literal["up", "down", "left", "right"],
        magnitude: int,
    ) -> EnvState: ...
    @abc.abstractmethod
    async def wait_5_seconds(self) -> EnvState: ...
    @abc.abstractmethod
    async def go_back(self) -> EnvState: ...
    @abc.abstractmethod
    async def go_forward(self) -> EnvState: ...
    @abc.abstractmethod
    async def search(self) -> EnvState: ...
    @abc.abstractmethod
    async def navigate(self, url: str) -> EnvState: ...
    @abc.abstractmethod
    async def key_combination(self, keys: list[str]) -> EnvState: ...
    @abc.abstractmethod
    async def drag_and_drop(
        self, x: int, y: int, destination_x: int, destination_y: int
    ) -> EnvState: ...
    @abc.abstractmethod
    async def current_state(self) -> EnvState: ...


PLAYWRIGHT_KEY_MAP = {
    "backspace": "Backspace",
    "tab": "Tab",
    "return": "Enter",
    "enter": "Enter",
    "shift": "Shift",
    "control": "ControlOrMeta",
    "alt": "Alt",
    "escape": "Escape",
    "space": "Space",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "end": "End",
    "home": "Home",
    "left": "ArrowLeft",
    "up": "ArrowUp",
    "right": "ArrowRight",
    "down": "ArrowDown",
    "insert": "Insert",
    "delete": "Delete",
    "command": "Meta",
}


class PlaywrightComputer(Computer):
    def __init__(
        self,
        screen_size: tuple[int, int] = (1280, 800),
        initial_url: str = "https://www.google.com",
        search_engine_url: str = "https://www.google.com",
    ):
        self._initial_url = initial_url
        self._screen_size = screen_size
        self._search_engine_url = search_engine_url
        self._download_urls: list[str] = []
        self._download_bytes: dict[str, bytes] = {}
        self._save_tasks: set[asyncio.Task] = set()

    async def _handle_new_page(self, new_page: playwright.async_api.Page) -> None:
        new_url = new_page.url
        await new_page.close()
        await self._page.goto(new_url)

    def _handle_download(self, download: playwright.async_api.Download) -> None:
        url = download.url
        self._download_urls.append(url)
        logger.info("[browser] download intercepted url=%s", url)
        task = asyncio.create_task(self._save_download(download, url))
        self._save_tasks.add(task)
        task.add_done_callback(self._save_tasks.discard)

    async def wait_for_pending_downloads(self, timeout: float = 30.0) -> None:
        pending = [t for t in self._save_tasks if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    async def _save_download(
        self, download: playwright.async_api.Download, url: str
    ) -> None:
        try:
            path = await download.path()
            if path is None:
                return
            with open(path, "rb") as f:
                self._download_bytes[url] = f.read()
            logger.info(
                "[browser] download saved url=%s bytes=%d",
                url, len(self._download_bytes[url]),
            )
        except Exception as e:
            logger.info(
                "[browser] download save failed url=%s error=%s",
                url, e.__class__.__name__,
            )

    async def __aenter__(self) -> "PlaywrightComputer":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            args=[
                "--disable-extensions",
                "--disable-file-system",
                "--disable-plugins",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--no-sandbox",
            ],
            headless=os.environ.get("PLAYWRIGHT_HEADLESS", "1").lower() in ("1", "true"),
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": self._screen_size[0],
                "height": self._screen_size[1],
            },
            accept_downloads=True,
        )
        await Stealth().apply_stealth_async(self._context)
        self._page = await self._context.new_page()
        self._context.on("page", lambda p: asyncio.create_task(self._handle_new_page(p)))
        self._page.on("download", self._handle_download)
        await self._page.goto(self._initial_url)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            await self._context.close()
        except Exception:
            pass
        try:
            await self._browser.close()
        except Exception:
            pass
        try:
            await self._pw.stop()
        except Exception:
            pass

    def collected_download_urls(self) -> list[str]:
        return list(self._download_urls)

    def get_download_bytes(self, url: str) -> bytes | None:
        return self._download_bytes.get(url)

    def screen_size(self) -> tuple[int, int]:
        viewport_size = self._page.viewport_size
        if viewport_size:
            return viewport_size["width"], viewport_size["height"]
        return self._screen_size

    async def open_web_browser(self) -> EnvState:
        return await self.current_state()

    async def click_at(self, x: int, y: int) -> EnvState:
        await self._page.mouse.click(x, y)
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def hover_at(self, x: int, y: int) -> EnvState:
        await self._page.mouse.move(x, y)
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True,
    ) -> EnvState:
        await self._page.mouse.click(x, y)
        await self._page.wait_for_load_state()
        if clear_before_typing:
            mod = "Meta" if sys.platform == "darwin" else "Control"
            await self.key_combination([mod, "A"])
            await self.key_combination(["Delete"])
        await self._page.keyboard.type(text)
        await self._page.wait_for_load_state()
        if press_enter:
            await self.key_combination(["Enter"])
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def _horizontal_document_scroll(
        self, direction: Literal["left", "right"]
    ) -> EnvState:
        amount = self.screen_size()[0] // 2
        sign = "-" if direction == "left" else ""
        await self._page.evaluate(f"window.scrollBy({sign}{amount}, 0); ")
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def scroll_document(
        self, direction: Literal["up", "down", "left", "right"]
    ) -> EnvState:
        if direction == "down":
            return await self.key_combination(["PageDown"])
        if direction == "up":
            return await self.key_combination(["PageUp"])
        if direction in ("left", "right"):
            return await self._horizontal_document_scroll(direction)
        raise ValueError(f"Unsupported direction: {direction}")

    async def scroll_at(
        self,
        x: int,
        y: int,
        direction: Literal["up", "down", "left", "right"],
        magnitude: int = 800,
    ) -> EnvState:
        await self._page.mouse.move(x, y)
        await self._page.wait_for_load_state()
        dx, dy = 0, 0
        if direction == "up":
            dy = -magnitude
        elif direction == "down":
            dy = magnitude
        elif direction == "left":
            dx = -magnitude
        elif direction == "right":
            dx = magnitude
        else:
            raise ValueError(f"Unsupported direction: {direction}")
        await self._page.mouse.wheel(dx, dy)
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def wait_5_seconds(self) -> EnvState:
        await asyncio.sleep(5)
        return await self.current_state()

    async def go_back(self) -> EnvState:
        await self._page.go_back()
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def go_forward(self) -> EnvState:
        await self._page.go_forward()
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def search(self) -> EnvState:
        return await self.navigate(self._search_engine_url)

    async def navigate(self, url: str) -> EnvState:
        normalized = url if url.startswith(("http://", "https://")) else "https://" + url
        try:
            await self._page.goto(normalized)
        except Exception as e:
            msg = str(e)
            if "Download is starting" in msg or "net::ERR_ABORTED" in msg:
                self._download_urls.append(normalized)
                logger.info("[browser] navigate triggered download url=%s", normalized)
            else:
                raise
        await self._page.wait_for_load_state()
        return await self.current_state()

    async def key_combination(self, keys: list[str]) -> EnvState:
        mapped = [PLAYWRIGHT_KEY_MAP.get(k.lower(), k) for k in keys]
        for key in mapped[:-1]:
            await self._page.keyboard.down(key)
        await self._page.keyboard.press(mapped[-1])
        for key in reversed(mapped[:-1]):
            await self._page.keyboard.up(key)
        return await self.current_state()

    async def drag_and_drop(
        self, x: int, y: int, destination_x: int, destination_y: int
    ) -> EnvState:
        await self._page.mouse.move(x, y)
        await self._page.wait_for_load_state()
        await self._page.mouse.down()
        await self._page.wait_for_load_state()
        await self._page.mouse.move(destination_x, destination_y)
        await self._page.wait_for_load_state()
        await self._page.mouse.up()
        return await self.current_state()

    async def current_state(self) -> EnvState:
        await self._page.wait_for_load_state()
        await asyncio.sleep(0.5)
        screenshot_bytes = await self._page.screenshot(type="png", full_page=False)
        return EnvState(screenshot=screenshot_bytes, url=self._page.url)
