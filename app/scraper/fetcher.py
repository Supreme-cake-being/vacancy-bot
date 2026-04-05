import asyncio
import logging
import random

import httpx
from playwright.async_api import async_playwright

from app.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

async def fetch_html(url: str) -> str | None:
    """
    Fetch page HTML using httpx.
    Handles retries and rate limiting automatically.
    """
    delay = random.uniform(settings.REQUEST_DELAY_MIN, settings.REQUEST_DELAY_MAX)
    await asyncio.sleep(delay)

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers=HEADERS,
    ) as client:
        for attempt in range(settings.MAX_RETRIES):
            try:
                response = await client.get(url)
                response.raise_for_status()
                logger.debug(f"Fetched {url} — status {response.status_code}")
                return response.text

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                logger.warning(f"HTTP {status} for {url} (attempt {attempt + 1})")

                if status == 429:
                    # Rate limited — wait longer each retry
                    wait = 60 * (attempt + 1)
                    logger.info(f"Rate limited. Waiting {wait}s...")
                    await asyncio.sleep(wait)
                elif status in (403, 503):
                    # Possibly bot protection — wait and retry
                    await asyncio.sleep(30 * (attempt + 1))
                elif status == 404:
                    logger.error(f"Page not found: {url}")
                    return None
                else:
                    return None

            except httpx.TimeoutException:
                logger.warning(f"Timeout for {url} (attempt {attempt + 1})")
                await asyncio.sleep(10)

            except httpx.RequestError as e:
                logger.error(f"Request error for {url}: {e}")
                await asyncio.sleep(10)

    logger.error(f"All {settings.MAX_RETRIES} attempts failed for {url}")
    return None

async def fetch_spa_html(url: str) -> str | None:
    """
    Fetch page HTML using Playwright (for JavaScript-rendered pages).
    Use only when fetch_html returns empty or broken content.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080},
                # Pretend to be a real browser
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )

            page = await context.new_page()

            # Hide webdriver flag — basic anti-detection
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for common job listing selectors to appear
            for selector in [".job", ".vacancy", ".position", "article", "li"]:
                try:
                    await page.wait_for_selector(selector, timeout=3000)
                    break
                except Exception:
                    continue

            html = await page.content()
            await browser.close()

            logger.debug(f"SPA fetch successful for {url}")
            return html

    except Exception as e:
        logger.error(f"Playwright error for {url}: {e}")
        return None

async def smart_fetch(url: str, parse_type: str = "http") -> str | None:
    """
    Main entry point — chooses fetch strategy based on site parse_type.
    parse_type: 'http' | 'spa'
    """
    if parse_type == "spa":
        return await fetch_spa_html(url)
    return await fetch_html(url)