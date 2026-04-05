import logging
import re

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

VACANCY_SELECTORS = [
    # Greenhouse
    ".opening",
    # Lever
    ".posting",
    # Workday
    "[data-automation-id='jobPostingsList'] li",
    # SmartRecruiters
    ".career-opportunity",
    # Generic job boards
    ".job-listing",
    ".job-item",
    ".vacancy-item",
    "[class*='job-card']",
    "[class*='vacancy-card']",
    "[class*='position-item']",
    # Semantic HTML
    "article.job",
    "article.vacancy",
    "article.position",
    "li.job",
    "li.vacancy",
    # Broad fallbacks
    "[class*='job']",
    "[class*='vacancy']",
    "[class*='career']",
]

def auto_detect_selector(html: str) -> str | None:
    """
    Try each selector and return the first one that finds 2+ elements.
    Returns None if nothing matches — page may need SPA fetch.
    """
    soup = BeautifulSoup(html, "lxml")
    for selector in VACANCY_SELECTORS:
        try:
            elements = soup.select(selector)
            if len(elements) >= 2:
                logger.debug(f"Auto-detected selector: {selector} ({len(elements)} elements)")
                return selector
        except Exception:
            continue
    return None

def extract_vacancies(html: str, css_selector: str) -> list[dict]:
    """
    Extract vacancy title and URL from HTML using a CSS selector.
    Returns list of dicts: [{"title": ..., "url": ...}, ...]
    """
    soup = BeautifulSoup(html, "lxml")
    items = soup.select(css_selector)
    vacancies = []

    for item in items:
        title = _extract_title(item)
        if not title or len(title) < 3:
            continue

        url = _extract_url(item)
        vacancies.append({"title": title, "url": url})

    logger.debug(f"Extracted {len(vacancies)} vacancies with selector '{css_selector}'")
    return vacancies

def _extract_title(item: Tag) -> str | None:
    """Extract the most likely title from an element."""
    # Try headings first
    for tag in ["h1", "h2", "h3", "h4"]:
        el = item.select_one(tag)
        if el:
            return el.get_text(strip=True)

    # Try elements with "title" in class or attribute
    el = item.select_one("[class*='title'], [data-title]")
    if el:
        return el.get_text(strip=True)

    # Try the first link
    el = item.select_one("a[href]")
    if el:
        return el.get_text(strip=True)

    # Last resort — full text of the element
    text = item.get_text(strip=True)
    # Take only the first line to avoid grabbing description
    first_line = text.split("\n")[0].strip()
    return first_line if first_line else None

def _extract_url(item: Tag) -> str | None:
    """Extract the vacancy URL from an element."""
    link = item.select_one("a[href]")
    if not link:
        return None

    href = link.get("href", "")
    if not href or href == "#":
        return None

    # Return relative URLs
    return href