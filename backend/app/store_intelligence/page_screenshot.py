from __future__ import annotations

from app.crawler.security import validate_url


async def capture_page_screenshot(url: str, *, mobile: bool = False) -> tuple[bytes, int, int, list[dict]]:
    # Lazy import keeps the core API/test suite usable before the optional
    # browser runtime is installed; only the user-triggered capture needs it.
    from playwright.async_api import async_playwright

    validate_url(url)
    viewport = {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 1000}
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True)
        except Exception:
            browser = await playwright.chromium.launch(headless=True, channel="chrome")
        try:
            context = await browser.new_context(viewport=viewport, locale="ar-SA")
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1200)
            size = await page.evaluate("() => ({width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight})")
            annotations: list[dict] = []
            for key, selector in (("h1", "h1"), ("primary_image", "main img, [role=main] img"), ("faq", "[itemtype*='FAQPage'], details")):
                locator = page.locator(selector).first
                if await locator.count():
                    box = await locator.bounding_box()
                    if box and float(box["width"]) >= 10 and float(box["height"]) >= 10:
                        annotations.append({"key": key, **{name: round(float(box[name]), 1) for name in ("x", "y", "width", "height")}})
            screenshot = await page.screenshot(full_page=True, type="png")
            return screenshot, int(size["width"]), int(size["height"]), annotations
        finally:
            await browser.close()
